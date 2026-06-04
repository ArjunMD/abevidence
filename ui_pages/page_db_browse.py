import html
from datetime import datetime, timedelta
from typing import Dict, List

import streamlit as st

from db import (
    delete_guideline,
    delete_record,
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


def _format_added_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "Unknown"
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return "Unknown"
    return dt.strftime("%B %-d, %Y")


def _added_day_key(item: Dict[str, str]) -> str:
    return (item.get("uploaded_at") or "")[:10]


def _added_week_start_key(item: Dict[str, str]) -> str:
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


def _month_sort_value(item: Dict[str, str]) -> int:
    if (item.get("type") or "").strip().lower() == "guideline":
        return 0
    raw = (item.get("pub_month") or "").strip()
    if raw.isdigit():
        n = int(raw)
        if 1 <= n <= 12:
            return n
    return 0


def _browse_item_sort_key(item: Dict[str, str]) -> tuple:
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


def _quick_delete_control(it: Dict[str, str], key_ns: str) -> None:
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
    it: Dict[str, str],
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
    it: Dict[str, str], show_pub_date: bool = False, allow_manage: bool = False
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


@st.fragment
def _render_browse_body() -> None:
    can_delete = not is_public_mode()
    col_spec, col_guide, col_sort = st.columns(3)
    with col_sort:
        sort_by_date_added = st.toggle(
            "Sort by date added",
            value=False,
            key="browse_sort_date_added",
        )
    with col_spec:
        by_specialty = st.toggle(
            "Browse by specialty",
            value=False,
            key="browse_by_specialty",
            disabled=sort_by_date_added,
        )
    with col_guide:
        guidelines_only = st.toggle(
            "Guidelines only",
            value=False,
            key="browse_guidelines_only",
        )
    if sort_by_date_added:
        by_specialty = False
    browse_q = st.text_input(
        "Search",
        placeholder="Search by drug, condition, or journal…",
        key="db_browse_any",
        help='Combine words with AND / OR, or wrap a phrase in "quotes" for an exact match.',
    )

    items: List[Dict[str, str]] = []
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
        by_week: Dict[str, List[Dict[str, str]]] = {}
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

    if by_specialty:
        grouped: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        for it in items:
            year = (it.get("year") or "").strip() or "Unknown"
            for spec in _split_specialties(it.get("specialty") or ""):
                grouped.setdefault(spec, {}).setdefault(year, []).append(it)

        specialties = sorted(grouped.keys(), key=lambda s: (s == "Unspecified", s.lower()))

        for spec in specialties:
            years_map = grouped.get(spec, {})
            years = sorted(years_map.keys(), key=_year_sort_key)
            years = list(reversed(years))

            with st.expander(spec, expanded=bool(q)):
                for y in years:
                    st.markdown(f"**{y}**")
                    rows = sorted(years_map.get(y, []), key=_browse_item_sort_key)
                    for it in rows:
                        _render_browse_item(it, allow_delete=can_delete, key_ns=f"spec_{spec}_{y}")

                    st.markdown("")
    else:
        by_year: Dict[str, List[Dict[str, str]]] = {}
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
                by_month: Dict[int, List[Dict[str, str]]] = {}
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
        "also browse by specialty, sort by date added, or search using the bar below. Click the "
        "🔎 on any study to open its summary, or see About to learn more. Thank you for visiting!"
    )
    _render_browse_body()
