import html
from datetime import datetime
from typing import Dict, List

import streamlit as st

from db import list_browse_guideline_items, list_browse_items, search_guidelines, search_records
from pages_shared import (
    BROWSE_MAX_ROWS,
    _browse_search_link,
    _split_specialties,
    _year_sort_key,
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


def _render_browse_item(it: Dict[str, str], show_pub_date: bool = False) -> None:
    if (it.get("type") or "") == "guideline":
        title = (it.get("title") or "").strip() or "(no name)"
        gid = (it.get("guideline_id") or "").strip()
        society = (it.get("society") or "").strip()
        safe_title = html.escape(title)
        soc_part = f" <i style='opacity:0.55;'>({html.escape(society)})</i>" if society else ""
        if gid:
            st.markdown(
                f"- {safe_title}{soc_part}{_browse_search_link(gid=gid)}",
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
    safe_pmid = html.escape(pmid)

    j = (it.get("journal") or "").strip()
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

    st.markdown(
        f"- <a href='{pub_url}' target='_blank'>{safe_title}</a> — <code>{safe_pmid}</code>"
        f"{_browse_search_link(pmid=pmid)}",
        unsafe_allow_html=True,
    )
    if concl:
        st.caption(f"{concl}{f' ({meta})' if meta else ''}")
    elif meta:
        st.caption(f"({meta})")


@st.fragment
def _render_browse_body() -> None:
    col_sort, col_spec, col_guide = st.columns(3)
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
        placeholder="Search by drug, condition, author, journal…",
        key="db_browse_any",
    )
    st.caption('Tip: combine words with AND / OR, or wrap a phrase in "quotes" for an exact match.')

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
        by_day: Dict[str, List[Dict[str, str]]] = {}
        for it in items:
            by_day.setdefault(_added_day_key(it), []).append(it)

        days = sorted(by_day.keys(), reverse=True)
        days = [d for d in days if d] + [d for d in days if not d]

        for idx, day in enumerate(days):
            if idx > 0:
                st.markdown("---")
            st.markdown(f"### {_format_added_date(day)}")

            rows = sorted(by_day.get(day, []), key=lambda it: (it.get("title") or "").lower())
            rows.sort(key=lambda it: (it.get("uploaded_at") or ""), reverse=True)
            for it in rows:
                _render_browse_item(it, show_pub_date=True)
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

            with st.expander(spec, expanded=False):
                for y in years:
                    st.markdown(f"**{y}**")
                    rows = sorted(years_map.get(y, []), key=_browse_item_sort_key)
                    for it in rows:
                        _render_browse_item(it)

                    st.markdown("")
    else:
        by_year: Dict[str, List[Dict[str, str]]] = {}
        for it in items:
            year = (it.get("year") or "").strip() or "Unknown"
            by_year.setdefault(year, []).append(it)

        years = sorted(by_year.keys(), key=_year_sort_key)
        years = list(reversed(years))

        for idx, y in enumerate(years):
            if idx > 0:
                st.markdown("---")
            st.markdown(f"### {y}")

            rows = by_year.get(y, [])
            rows = sorted(rows, key=_browse_item_sort_key)

            for it in rows:
                _render_browse_item(it)


def render() -> None:
    st.title("🗂️ Browse studies")
    st.markdown(
        "Browse our library of clinical studies and guidelines. Each entry is summarized "
        "into **PICO** — **P**atients, **I**ntervention / **C**omparison, and **O**utcomes. "
        "Click 🔎 to open the full structured summary, or a title to view it on PubMed."
    )
    _render_browse_body()
