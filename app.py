import streamlit as st

from db import (
    db_count,
    db_count_all,
    ensure_guidelines_schema,
    ensure_schema,
    guidelines_count,
)
from pages_shared import (
    _clean_pmid,
    _clear_query_params,
    _get_query_params,
    _qp_first,
    is_public_mode,
)
from ui_pages.page_about import render as render_about
from ui_pages.page_dashboard import render as render_dashboard
from ui_pages.page_db_browse import render as render_db_browse
from ui_pages.page_db_search import render as render_db_search
from ui_pages.page_delete import render as render_delete
from ui_pages.page_guidelines import render as render_guidelines
from ui_pages.page_history import render as render_history
from ui_pages.page_pmid_abstract import render as render_pmid_abstract
from ui_pages.page_search_pubmed import render as render_search_pubmed

st.set_page_config(page_title="PMID → Abstract", page_icon="📄", layout="wide")
ensure_schema()
ensure_guidelines_schema()

# name → renderer. Dict order is the sidebar order.
_PAGES = {
    "PMID → Abstract": render_pmid_abstract,
    "Upload Guideline": render_guidelines,
    "Browse studies": render_db_browse,
    "Single-study view": render_db_search,
    "Search PubMed": render_search_pubmed,
    "Manage": render_delete,
    "Dashboard": render_dashboard,
    "About": render_about,
    "History": render_history,
}

# In public mode (ABEV_MODE=public — set on the hosted .com instance), only
# these pages are exposed; everything else, plus all edit/upload affordances
# inside the surviving pages, is hidden.
_PUBLIC_PAGES = {"Browse studies", "Single-study view", "History"}

_IS_PUBLIC = is_public_mode()
_VISIBLE_PAGES = [p for p in _PAGES if not _IS_PUBLIC or p in _PUBLIC_PAGES]

_qp = _get_query_params()
_open_pmid = _clean_pmid(_qp_first(_qp, "pmid"))
_open_gid = (_qp_first(_qp, "gid") or "").strip()
_open_delrec = (_qp_first(_qp, "delrec") or "").strip()
_open_abs_pmid = _clean_pmid(_qp_first(_qp, "open_abs_pmid"))

if _open_abs_pmid and not _IS_PUBLIC:
    st.session_state["nav_page"] = "PMID → Abstract"
    st.session_state["pmid_input"] = _open_abs_pmid
    _clear_query_params()
elif _open_pmid or _open_gid:
    st.session_state["nav_page"] = "Single-study view"
    st.session_state["db_search_any"] = ""

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

_default_index = _VISIBLE_PAGES.index("Browse studies") if _IS_PUBLIC else 0

nav_page = st.sidebar.radio(
    "Research",
    _VISIBLE_PAGES,
    index=_default_index,
    key="nav_page",
)

st.sidebar.caption(
    f"Saved: **{db_count_all()}**  "
    f"({db_count()} abstracts, {guidelines_count()} guidelines)"
)

_PAGES[nav_page]()
