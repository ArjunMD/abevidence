import html
from typing import Dict, List

import streamlit as st

from db import list_browse_guideline_items, list_browse_items, search_guidelines, search_records
from pages_shared import (
    BROWSE_MAX_ROWS,
    _browse_search_link,
    _split_specialties,
    _year_sort_key,
)


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


def _render_browse_item(it: Dict[str, str]) -> None:
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
    by_specialty = st.toggle(
        "Browse by specialty",
        value=False,
        key="browse_by_specialty",
    )
    guidelines_only = st.toggle(
        "Guidelines only",
        value=False,
        key="browse_guidelines_only",
    )
    browse_q = st.text_input(
        "Search",
        placeholder='Filter this browse view by any field. Supports AND, OR, and "exact phrase"…',
        key="db_browse_any",
    )
    st.caption('Example: `heart AND "reduced ejection fraction"` or `sepsis OR septic shock`')

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
    _render_browse_body()
