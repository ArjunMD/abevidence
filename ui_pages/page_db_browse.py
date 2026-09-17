import html
import re
from collections import Counter
from datetime import datetime, timedelta

import streamlit as st

from db import (
    delete_guideline,
    delete_record,
    get_category_specialties,
    list_browse_guideline_items,
    list_browse_items,
    search_guidelines,
    search_records,
)
from pages_shared import (
    BROWSE_MAX_ROWS,
    _browse_manage_link,
    _browse_search_link,
    _split_specialties,
    _year_sort_key,
    display_journal,
    is_public_mode,
)


def _added_week_start_key(item: dict[str, str]) -> str:
    """ISO date (YYYY-MM-DD) of the Monday of the week an item was added, or ''
    if the added date is missing/invalid. The date-added view buckets by week
    (not by exact day) so it surfaces "what's new" without exposing precise
    per-day curation activity."""
    s = (item.get("uploaded_at") or "")[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return ""
    return (d - timedelta(days=d.weekday())).isoformat()


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format_week_range(monday_iso: str) -> str:
    """Render a Monday-anchored week as a date range, e.g.
    'June 1st - June 7th, 2026' (or spanning months/years as needed)."""
    try:
        start = datetime.strptime(monday_iso, "%Y-%m-%d").date()
    except ValueError:
        return "Unknown"
    end = start + timedelta(days=6)
    start_str = f"{start.strftime('%B')} {_ordinal(start.day)}"
    end_str = f"{end.strftime('%B')} {_ordinal(end.day)}"
    if start.year != end.year:
        return f"{start_str}, {start.year} - {end_str}, {end.year}"
    return f"{start_str} - {end_str}, {end.year}"


_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _month_label(m: int) -> str:
    return _MONTH_NAMES[m] if 1 <= int(m) <= 12 else "Guidelines"


def _month_sort_value(item: dict[str, str]) -> int:
    if (item.get("type") or "").strip().lower() == "guideline":
        return 0
    raw = (item.get("pub_month") or "").strip()
    if raw.isdigit():
        n = int(raw)
        if 1 <= n <= 12:
            return n
    return 0


def _split_categories(raw: str) -> list[str]:
    """Split a comma-separated category field into tags; items without any
    category land in an 'Uncategorized' bucket at the end of the list."""
    return ["Uncategorized" if c == "Unspecified" else c for c in _split_specialties(raw)]


def _anchor_slugs(names: list[str], prefix: str = "") -> dict[str, str]:
    """URL-safe, unique anchor ids for headers / TOC links. A prefix keeps the
    specialty and category anchor namespaces from colliding."""
    slugs: dict[str, str] = {}
    used: set[str] = set()
    for c in names:
        s = prefix + (re.sub(r"[^a-z0-9]+", "-", c.lower()).strip("-") or "section")
        base, n = s, 2
        while s in used:
            s = f"{base}-{n}"
            n += 1
        used.add(s)
        slugs[c] = s
    return slugs


def _group_categories_by_specialty(
    grouped: dict[str, list[dict[str, str]]]
) -> list[tuple[str, list[str]]]:
    """Assign each category to ONE specialty. Primary source is the stored
    category_specialty table (each category NAME is GPT-classified once, with
    'General' reserved for systems-of-care topics). A category not classified yet
    falls back to a majority vote over its items' specialty tags — winner needs
    at least half the items, else 'General'. Returns [(specialty, [categories])]
    with specialties alphabetized ('General' last) and categories alphabetized
    within each specialty ('Uncategorized' last)."""
    stored = get_category_specialties()
    cat_spec: dict[str, str] = {}
    for cat, its in grouped.items():
        winner = stored.get(cat.lower(), "")
        if not winner:
            votes: Counter = Counter()
            for it in its:
                for sp in _split_specialties(it.get("specialty") or ""):
                    if sp != "Unspecified":
                        votes[sp] += 1
            if votes:
                top, top_votes = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0].lower()))[0]
                if top_votes / max(1, len(its)) >= 0.5:
                    winner = top
        cat_spec[cat] = winner or "General"

    groups: dict[str, list[str]] = {}
    for cat, sp in cat_spec.items():
        groups.setdefault(sp, []).append(cat)

    return [
        (sp, sorted(groups[sp], key=lambda c: (c == "Uncategorized", c.lower())))
        for sp in sorted(groups, key=lambda s: (s == "General", s.lower()))
    ]


def _heading_with_top_link(text: str, slug: str, level: int) -> str:
    """A category/specialty heading with its anchor id and a subtle 'back to top'
    arrow on the same line, returning to the Contents block."""
    return (
        f"<h{level} id='{slug}'>{html.escape(text)} "
        f"<a href='#contents' title='Back to contents' "
        f"style='text-decoration:none; opacity:0.35; font-size:0.6em; vertical-align:middle;'>↑</a>"
        f"</h{level}>"
    )


def _category_item_sort_key(item: dict[str, str]) -> tuple:
    """Newest first within a category (year, then pub month), then title."""
    y = (item.get("year") or "").strip()
    year_num = int(y) if y.isdigit() else -1
    return (-year_num, -_month_sort_value(item), (item.get("title") or "").lower())


def _browse_item_sort_key(item: dict[str, str]) -> tuple:
    item_type = (item.get("type") or "").lower()
    title = (item.get("title") or "").lower()
    pmid = (item.get("pmid") or "").lower()
    gid = (item.get("guideline_id") or "").lower()
    return (item_type, -_month_sort_value(item), title, pmid, gid)


def _format_pub_year_month(year: str, pub_month: str) -> str:
    y = (year or "").strip()
    m = (pub_month or "").strip()
    if not y:
        return ""
    if m.isdigit() and 1 <= int(m) <= 12:
        return f"{y}-{int(m):02d}"
    return y


def _quick_delete_control(it: dict[str, str], key_ns: str) -> None:
    """Backend-only popover to delete an abstract or guideline straight from the
    browse list. Two clicks (open popover → Confirm) to avoid accidental loss."""
    is_guideline = (it.get("type") or "").strip() == "guideline"
    ident = ((it.get("guideline_id") if is_guideline else it.get("pmid")) or "").strip()
    if not ident:
        return

    label = "guideline" if is_guideline else "abstract"
    with st.popover("🗑️", help=f"Delete this {label} from the library"):
        st.caption(f"Permanently delete this {label}?")
        if st.button(
            "Confirm delete",
            key=f"browse_qdel_{'g' if is_guideline else 'p'}_{key_ns}_{ident}",
            type="primary",
            width="stretch",
        ):
            try:
                if is_guideline:
                    delete_guideline(ident)
                else:
                    delete_record(ident)
                st.toast(f"Deleted {label} from the library.")
                # Bump the scroll token so app.py's view-change gate fires and
                # scrolls back to the top after the delete (otherwise the full
                # rerun leaves you mid-page where the removed item used to be).
                st.session_state["browse_scroll_token"] = (
                    int(st.session_state.get("browse_scroll_token") or 0) + 1
                )
                st.rerun()
            except Exception as e:
                st.error(str(e))


def _render_browse_item(
    it: dict[str, str],
    show_pub_date: bool = False,
    allow_delete: bool = False,
    key_ns: str = "",
) -> None:
    if not allow_delete:
        _render_browse_item_body(it, show_pub_date, allow_manage=False)
        return

    col_main, col_del = st.columns([0.95, 0.05], gap="small")
    with col_main:
        _render_browse_item_body(it, show_pub_date, allow_manage=True)
    with col_del:
        _quick_delete_control(it, key_ns)


def _render_browse_item_body(
    it: dict[str, str], show_pub_date: bool = False, allow_manage: bool = False
) -> None:
    if (it.get("type") or "") == "guideline":
        title = (it.get("title") or "").strip() or "(no name)"
        gid = (it.get("guideline_id") or "").strip()
        society = (it.get("society") or "").strip()
        safe_title = html.escape(title)
        soc_part = f" <i style='opacity:0.55;'>({html.escape(society)})</i>" if society else ""
        if gid:
            manage = _browse_manage_link(gid=gid) if allow_manage else ""
            st.markdown(
                f"- {safe_title}{soc_part}{_browse_search_link(gid=gid)}{manage}",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"- {safe_title}{soc_part}", unsafe_allow_html=True)
        return

    pmid = (it.get("pmid") or "").strip()
    title = (it.get("title") or "").strip() or "(no title)"
    concl = (it.get("authors_conclusions") or "").strip()

    pub_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    safe_title = html.escape(title)

    j = display_journal(it.get("journal") or "")
    pn = (it.get("patient_n") or "").strip()

    meta_bits = []
    if pn:
        meta_bits.append(f"N={pn}")
    if j:
        meta_bits.append(j)
    if show_pub_date:
        ym = _format_pub_year_month(it.get("year") or "", it.get("pub_month") or "")
        if ym:
            meta_bits.append(ym)
    meta = ", ".join(meta_bits)

    manage = _browse_manage_link(pmid=pmid) if allow_manage else ""
    st.markdown(
        f"- <a href='{pub_url}' target='_blank'>{safe_title}</a>"
        f"{_browse_search_link(pmid=pmid)}{manage}",
        unsafe_allow_html=True,
    )
    if concl:
        st.caption(f"{concl}{f' ({meta})' if meta else ''}")
    elif meta:
        st.caption(f"({meta})")


# Browse controls whose state must survive the single-study overlay round-trip.
# Streamlit drops widget-keyed state for widgets that aren't rendered on a run, and
# in public mode the overlay replaces this whole page — so without shadowing, the
# toggles and search box reset to defaults when the visitor clicks "Back to studies".
_BROWSE_PERSIST_KEYS = (
    "browse_sort_date_added",
    "browse_by_category",
    "browse_guidelines_only",
    "db_browse_any",
)


def _restore_browse_controls() -> None:
    """Copy shadowed values back into the widget keys before the widgets render."""
    for k in _BROWSE_PERSIST_KEYS:
        shadow = f"_keep_{k}"
        if k not in st.session_state and shadow in st.session_state:
            st.session_state[k] = st.session_state[shadow]


def _shadow_browse_controls() -> None:
    """Mirror the current widget values into non-widget keys that Streamlit won't
    garbage-collect while this page is unmounted."""
    for k in _BROWSE_PERSIST_KEYS:
        if k in st.session_state:
            st.session_state[f"_keep_{k}"] = st.session_state[k]


@st.fragment
def _render_browse_body() -> None:
    _restore_browse_controls()
    can_delete = not is_public_mode()
    col_spec, col_guide, col_sort = st.columns(3)
    with col_sort:
        # No `value=` here (and below): the default lives in session_state via the
        # restore/shadow pair, and passing both would warn about a double-set default.
        sort_by_date_added = st.toggle(
            "Sort by date added",
            key="browse_sort_date_added",
        )
    with col_spec:
        by_category = st.toggle(
            "Browse by category",
            key="browse_by_category",
            disabled=sort_by_date_added,
        )
    with col_guide:
        guidelines_only = st.toggle(
            "Guidelines only",
            key="browse_guidelines_only",
        )
    if sort_by_date_added:
        by_category = False
    browse_q = st.text_input(
        "Search",
        placeholder="Search by drug, condition, or journal…",
        key="db_browse_any",
        help='Combine words with AND / OR, or wrap a phrase in "quotes" for an exact match.',
    )
    # Shadow immediately after the controls render, before any early st.stop() below,
    # so the latest values are captured even when the list is empty / has no matches.
    _shadow_browse_controls()

    items: list[dict[str, str]] = []
    if guidelines_only:
        items.extend(list_browse_guideline_items(limit=BROWSE_MAX_ROWS))
    else:
        items.extend(list_browse_items(limit=BROWSE_MAX_ROWS))
        items.extend(list_browse_guideline_items(limit=BROWSE_MAX_ROWS))

    if not items:
        if guidelines_only:
            st.info("No saved guidelines yet.")
        else:
            st.info("No saved items yet.")
        st.stop()

    q = (browse_q or "").strip()
    if q:
        if guidelines_only:
            matched_guideline_rows = search_guidelines(limit=BROWSE_MAX_ROWS, q=q)
            matched_gids = {
                (r.get("guideline_id") or "").strip()
                for r in (matched_guideline_rows or [])
                if (r.get("guideline_id") or "").strip()
            }
            items = [
                it
                for it in items
                if (it.get("type") or "").strip() == "guideline"
                and (it.get("guideline_id") or "").strip() in matched_gids
            ]
        else:
            matched_paper_rows = search_records(limit=BROWSE_MAX_ROWS, q=q)
            matched_guideline_rows = search_guidelines(limit=BROWSE_MAX_ROWS, q=q)
            matched_pmids = {
                (r.get("pmid") or "").strip()
                for r in (matched_paper_rows or [])
                if (r.get("pmid") or "").strip()
            }
            matched_gids = {
                (r.get("guideline_id") or "").strip()
                for r in (matched_guideline_rows or [])
                if (r.get("guideline_id") or "").strip()
            }
            items = [
                it
                for it in items
                if (
                    ((it.get("type") or "").strip() == "guideline" and (it.get("guideline_id") or "").strip() in matched_gids)
                    or ((it.get("type") or "").strip() != "guideline" and (it.get("pmid") or "").strip() in matched_pmids)
                )
            ]

        if not items:
            st.info("No matches in current browse view.")
            st.stop()

    if sort_by_date_added:
        # Bucket by the week an item was added (Monday-anchored), newest week
        # first, each week in an expander like the by-year / by-specialty views.
        # Week-level granularity keeps the "what's new" signal without exposing
        # exact per-day activity.
        by_week: dict[str, list[dict[str, str]]] = {}
        for it in items:
            by_week.setdefault(_added_week_start_key(it), []).append(it)

        weeks = sorted([w for w in by_week if w], reverse=True)
        weeks += [w for w in by_week if not w]  # undated bucket, if any, goes last

        for wk in weeks:
            label = _format_week_range(wk) if wk else "Date added unknown"
            rows = sorted(by_week.get(wk, []), key=lambda it: (it.get("title") or "").lower())
            rows.sort(key=lambda it: (it.get("uploaded_at") or ""), reverse=True)
            with st.expander(label, expanded=bool(q)):
                for it in rows:
                    _render_browse_item(
                        it, show_pub_date=True, allow_delete=can_delete, key_ns=f"week_{wk or 'na'}"
                    )
        return

    if by_category:
        # Categories grouped under specialty headings: each specialty is a top-level
        # header, each category under it a subheader, papers listed beneath. A paper
        # tagged with several categories appears in each of them. Sections are flat
        # headers (not expanders) because the table of contents jumps via anchors.
        grouped: dict[str, list[dict[str, str]]] = {}
        for it in items:
            for cat in _split_categories(it.get("category") or ""):
                grouped.setdefault(cat, []).append(it)

        spec_groups = _group_categories_by_specialty(grouped)
        slugs = _anchor_slugs(list(grouped.keys()))
        spec_slugs = _anchor_slugs([sp for sp, _ in spec_groups], prefix="sp-")

        # TOC mirrors the hierarchy: bold specialty, its categories bulleted under
        # it. 'Parent - Subtopic' categories render as an indented subtopic under a
        # parent line instead of their full name (the body headings keep the full
        # name). Alphabetical order keeps a parent and its subtopics contiguous.
        # Specialty blocks are kept intact and distributed over three columns,
        # balanced by line count so the columns come out roughly even.
        toc_blocks = []
        for sp, cats in spec_groups:
            lines = [f"**[{sp}](#{spec_slugs[sp]})**"]
            last_parent = None
            for c in cats:
                if " - " in c:
                    parent, sub = c.split(" - ", 1)
                    if last_parent != parent.lower():
                        # Parent has no section of its own — label it, linking to
                        # its first subtopic so the click still lands usefully.
                        lines.append(f"- [{parent}](#{slugs[c]})")
                        last_parent = parent.lower()
                    lines.append(f"    - [{sub}](#{slugs[c]}) ({len(grouped[c])})")
                else:
                    lines.append(f"- [{c}](#{slugs[c]}) ({len(grouped[c])})")
                    last_parent = c.lower()
            toc_blocks.append("\n".join(lines))
        total_lines = sum(b.count("\n") + 2 for b in toc_blocks)
        per_col = total_lines / 3
        st.markdown("<h4 id='contents'>Contents</h4>", unsafe_allow_html=True)
        toc_cols = st.columns(3, gap="large")
        col_idx, col_lines = 0, 0
        col_content: list[list[str]] = [[], [], []]
        for b in toc_blocks:
            col_content[col_idx].append(b)
            col_lines += b.count("\n") + 2
            if col_lines >= per_col and col_idx < 2:
                col_idx += 1
                col_lines = 0
        for i, col in enumerate(toc_cols):
            if col_content[i]:
                with col:
                    st.markdown("\n\n".join(col_content[i]))
        st.divider()

        for sp, cats in spec_groups:
            st.markdown(_heading_with_top_link(sp, spec_slugs[sp], 2), unsafe_allow_html=True)
            for c in cats:
                st.markdown(_heading_with_top_link(c, slugs[c], 3), unsafe_allow_html=True)
                rows = sorted(grouped[c], key=_category_item_sort_key)
                for it in rows:
                    _render_browse_item(
                        it, show_pub_date=True, allow_delete=can_delete, key_ns=f"cat_{slugs[c]}"
                    )
    else:
        by_year: dict[str, list[dict[str, str]]] = {}
        for it in items:
            year = (it.get("year") or "").strip() or "Unknown"
            by_year.setdefault(year, []).append(it)

        years = sorted(by_year.keys(), key=_year_sort_key)
        years = list(reversed(years))

        # Collapse each year into an expander so the first screen is a short,
        # scannable list of years instead of an endless scroll of titles. The
        # most recent year opens by default; a search opens every year so all
        # matches are visible.
        for idx, y in enumerate(years):
            year_items = by_year.get(y, [])
            with st.expander(str(y), expanded=bool(q) or idx == 0):
                # Subdivide each year by publication month (newest first;
                # guidelines and undated papers fall into "Guidelines" at the
                # bottom).
                by_month: dict[int, list[dict[str, str]]] = {}
                for it in year_items:
                    by_month.setdefault(_month_sort_value(it), []).append(it)

                for m in sorted(by_month.keys(), reverse=True):
                    st.markdown(f"**{_month_label(m)}**")
                    rows = sorted(by_month.get(m, []), key=_browse_item_sort_key)
                    for it in rows:
                        _render_browse_item(it, allow_delete=can_delete, key_ns=f"year_{y}_m{m}")


def render() -> None:
    st.title("🗂️ Browse studies")
    st.markdown(
        "Welcome! Hospital Medicine Shelf is a library of clinical trials, meta-analyses, "
        "systematic reviews, and guidelines relevant to hospital medicine. Articles are listed "
        "most-recent-first by default (guidelines are grouped at the end of each year). You can "
        "also browse by category, sort by date added, or search using the bar below. Click the "
        "🔎 on any study to open its summary, or see About to learn more. Thank you for visiting!"
    )
    _render_browse_body()
