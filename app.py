import streamlit as st
import streamlit.components.v1 as components

from db import (
    db_count,
    db_count_all,
    ensure_guidelines_schema,
    ensure_notes_schema,
    ensure_schema,
    guidelines_count,
)
from pages_shared import (
    _clean_pmid,
    _clear_query_params,
    _get_query_params,
    _qp_first,
    clear_public_study_overlay,
    is_public_mode,
)
from ui_pages.page_about import render as render_about
from ui_pages.page_dashboard import render as render_dashboard
from ui_pages.page_db_browse import render as render_db_browse
from ui_pages.page_db_search import render as render_db_search
from ui_pages.page_delete import render as render_delete
from ui_pages.page_guidelines import render as render_guidelines
from ui_pages.page_notes import render as render_notes
from ui_pages.page_pmid_abstract import render as render_pmid_abstract
from ui_pages.page_search_pubmed import render as render_search_pubmed
from ui_pages.page_suggest import render as render_suggest

st.set_page_config(page_title="Hospital Medicine Shelf", page_icon="🩺", layout="wide")
ensure_schema()
ensure_guidelines_schema()
ensure_notes_schema()

# name → renderer. Dict order is the sidebar order.
_PAGES = {
    "Upload Abstract": render_pmid_abstract,
    "Upload Guideline": render_guidelines,
    "Browse studies": render_db_browse,
    "Single-study view": render_db_search,
    "Search PubMed": render_search_pubmed,
    "Manage": render_delete,
    "Dashboard": render_dashboard,
    "Notes": render_notes,
    "Suggest an article": render_suggest,
    "About": render_about,
}

# In public mode (ABEV_MODE=public — set on the hosted .com instance), only
# these pages are exposed; everything else, plus all edit/upload affordances
# inside the surviving pages, is hidden.
#
# "Single-study view" is intentionally NOT a public sidebar item: a visitor
# reaches it by clicking a study on Browse and returns via its "Back to studies"
# button. Keeping it out of the sidebar avoids a confusing nav entry that does
# nothing useful when clicked with no study selected.
_PUBLIC_SIDEBAR_PAGES = {"Browse studies", "About", "Suggest an article", "Notes"}

_IS_PUBLIC = is_public_mode()
_SIDEBAR_PAGES = [p for p in _PAGES if not _IS_PUBLIC or p in _PUBLIC_SIDEBAR_PAGES]


def _scroll_main_to_top(token: str) -> None:
    """Reset the main content scroll position to the top. Streamlit keeps the
    browser scroll offset across reruns/page swaps, so navigating from a long
    page (e.g. Single-study view) to another long page leaves you mid-scroll.
    The `token` makes the injected iframe unique per view so the script re-runs."""
    components.html(
        f"""
        <script>
        /* view: {token} */
        (function () {{
          function toTop() {{
            var doc = window.parent.document;
            var sels = [
              'section.main',
              '[data-testid="stMain"]',
              '[data-testid="stAppViewContainer"]',
              '.block-container'
            ];
            sels.forEach(function (s) {{
              var el = doc.querySelector(s);
              if (el) {{ el.scrollTop = 0; }}
            }});
            if (doc.scrollingElement) {{ doc.scrollingElement.scrollTop = 0; }}
            if (doc.documentElement) {{ doc.documentElement.scrollTop = 0; }}
            if (doc.body) {{ doc.body.scrollTop = 0; }}
            try {{ window.parent.scrollTo(0, 0); }} catch (e) {{}}
          }}
          toTop();
          setTimeout(toTop, 30);
        }})();
        </script>
        """,
        height=0,
    )


_qp = _get_query_params()
_open_pmid = _clean_pmid(_qp_first(_qp, "pmid"))
_open_gid = (_qp_first(_qp, "gid") or "").strip()
_open_delrec = (_qp_first(_qp, "delrec") or "").strip()
_open_abs_pmid = _clean_pmid(_qp_first(_qp, "open_abs_pmid"))
_manage_pmid = _clean_pmid(_qp_first(_qp, "manage_pmid"))
_manage_gid = (_qp_first(_qp, "manage_gid") or "").strip()

if _open_abs_pmid and not _IS_PUBLIC:
    st.session_state["nav_page"] = "Upload Abstract"
    st.session_state["pmid_input"] = _open_abs_pmid
    # Deep-link from Search → auto-run the fetch on arrival (consumed once).
    st.session_state["auto_fetch_abstract"] = True
    _clear_query_params()
elif _manage_pmid and not _IS_PUBLIC:
    # Deep-link from Browse → Manage with this abstract pre-filtered/selected.
    st.session_state["nav_page"] = "Manage"
    st.session_state["delete_paper_filter"] = _manage_pmid
    st.session_state.pop("delete_paper_select_idx", None)
    _clear_query_params()
elif _manage_gid and not _IS_PUBLIC:
    # Deep-link from Browse → Manage with this guideline pre-selected. The
    # guideline search doesn't match on guideline_id, so leave the filter blank
    # (the recent-guidelines list supplies the options) and select by id.
    st.session_state["nav_page"] = "Manage"
    st.session_state.pop("delete_guideline_filter", None)
    st.session_state["delete_guideline_selected_gid"] = _manage_gid
    _clear_query_params()
elif _open_pmid or _open_gid:
    st.session_state["db_search_any"] = ""
    if _IS_PUBLIC:
        # Single-study view isn't in the public sidebar; show it as an overlay.
        st.session_state["public_study_overlay"] = True
    else:
        st.session_state["nav_page"] = "Single-study view"

    if _open_pmid:
        st.session_state["db_search_open_pmid"] = _open_pmid
        st.session_state.pop("db_search_open_gid", None)
    if _open_gid:
        st.session_state["db_search_open_gid"] = _open_gid
        st.session_state.pop("db_search_open_pmid", None)

    if _open_delrec and not _IS_PUBLIC:
        st.session_state["db_search_delete_rec"] = _open_delrec
        if _open_gid:
            st.session_state[f"dbs_guideline_edit_{_open_gid}"] = True

    _clear_query_params()

_default_index = _SIDEBAR_PAGES.index("Browse studies") if _IS_PUBLIC else 0

st.sidebar.title("🩺 Hospital Medicine Shelf")

nav_page = st.sidebar.radio(
    "Go to",
    _SIDEBAR_PAGES,
    index=_default_index,
    key="nav_page",
    on_change=clear_public_study_overlay if _IS_PUBLIC else None,
)

# Keep the running count for the owner's own reference, but don't greet public
# visitors with a big "N papers" number — it reads as a database dump rather
# than a useful tool.
if not _IS_PUBLIC:
    st.sidebar.caption(
        f"Saved: **{db_count_all()}**  "
        f"({db_count()} abstracts, {guidelines_count()} guidelines)"
    )

# Scroll back to the top whenever the effective view changes (sidebar page,
# public study overlay, or which study is open). Gated on the view key so it
# does NOT fire on ordinary reruns like typing in a search box.
_overlay_now = "1" if (_IS_PUBLIC and st.session_state.get("public_study_overlay")) else "0"
_view_key = "|".join([
    str(nav_page),
    _overlay_now,
    (st.session_state.get("db_search_open_pmid") or "").strip(),
    (st.session_state.get("db_search_open_gid") or "").strip(),
    str(st.session_state.get("browse_scroll_token") or ""),
])
if st.session_state.get("_last_view_key") != _view_key:
    st.session_state["_last_view_key"] = _view_key
    _scroll_main_to_top(_view_key)

if _IS_PUBLIC and st.session_state.get("public_study_overlay"):
    render_db_search()
else:
    _PAGES[nav_page]()
