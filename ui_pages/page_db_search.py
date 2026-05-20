import re
import html
from typing import Dict, List, Optional

import requests
import streamlit as st

from db import (
    get_guideline_meta,
    get_guideline_recommendations_display,
    get_record,
    search_guidelines,
    search_records,
    update_guideline_recommendations_display,
)
from extract import get_s2_similar_papers, get_top_neighbors
from pages_shared import (
    SEARCH_MAX_DEFAULT,
    _delete_recs_from_guideline_md,
    _fmt_search_item,
    _guideline_md_with_delete_links,
    _parse_rec_nums,
    _render_bullets,
    _render_plain_text,
    _tags_to_md,
    is_public_mode,
)


_GUIDELINE_ATTR_SEGMENT_RE = re.compile(
    r"(?P<label>\b(?:Strength|Evidence)\b\s*:\s*)(?P<value>[^;\)\n]+)",
    flags=re.IGNORECASE,
)
_GUIDELINE_PSEUDO_ATTR_VALUE_RE = re.compile(
    r"(?i)^\s*(?:we\s+)?(?:recommend|suggest|consider|avoid|do\s+not|don't|should)\b"
)
# Matches parenthetical text containing clinical grading keywords (inline grading)
_GUIDELINE_INLINE_GRADE_RE = re.compile(
    r"\(("
    r"[^)]*"
    r"\b(?:"
    r"(?:strong|weak|conditional)\s+recommendation"
    r"|good\s+practice\s+statement"
    r"|class\s*(?:[ivx]+|\d+[a-z]?)"
    r"|grade\s*(?:[a-d]|\d+[a-z]?)"
    r"|level\s*(?:of\s+evidence\s*)?[a-d](?:-[a-z]+)?"
    r"|(?:very\s+low|low|moderate|high)\s+(?:certainty|quality)"
    r")\b"
    r"[^)]*"
    r")\)",
    flags=re.IGNORECASE,
)
_GUIDELINE_ATTR_BLUE_HEX = "#2F8CFF"


def _clean_guideline_display(md: str) -> str:
    """Display-time cleanup for stored guideline markdown (idempotent)."""
    s = (md or "").strip()
    if not s:
        return ""
    # Remove redundant ## Recommendations heading
    s = re.sub(r"^##\s+Recommendations\s*\n+", "", s)
    # Fix PDF line-break hyphens: "comprehen- sive" → "comprehensive"
    s = re.sub(r"(\w)- (\w)", r"\1\2", s)
    # Strip inline citation numbers after periods: "PE.1,2" → "PE."
    s = re.sub(r"(?<=[a-zA-Z])\.(\d+(?:[,\-–]\s*\d+)*)", ".", s)
    # Strip parenthetical citation numbers: "(42, 47, 48)" → ""
    s = re.sub(r"\s*\(\d+(?:[,\s\-–]+\d+)*\)", "", s)
    # Strip footnote markers: "algorithm*" → "algorithm"
    s = re.sub(r"(?<=[a-zA-Z])[*†‡§]+(?=[\s,;.\)]|$)", "", s)
    # Strip leading transitional words from each recommendation line
    def _strip_transition(m: re.Match) -> str:
        prefix = m.group(1)  # e.g. "- **3.** "
        body = re.sub(
            r"^(Thus|However|Therefore|Accordingly|Furthermore|Moreover|Hence|Consequently|In addition|Additionally),?\s*",
            "", m.group(2), flags=re.IGNORECASE,
        )
        if body:
            body = body[0].upper() + body[1:]
        return prefix + body
    s = re.sub(r"(^\s*(?:-\s+)?\*\*(?:Rec\s+)?\d+\.\*\*\s*)(.*)", _strip_transition, s, flags=re.MULTILINE)
    return s.strip()


def _highlight_guideline_strength_evidence(md: str) -> str:
    s = md or ""
    if not s:
        return ""

    def _norm_alnum(raw: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (raw or "").lower())

    def _repl(m: re.Match) -> str:
        label = (m.group("label") or "").strip()
        value = (m.group("value") or "").strip()
        if _GUIDELINE_PSEUDO_ATTR_VALUE_RE.search(value):
            return m.group(0)

        line_start = s.rfind("\n", 0, m.start()) + 1
        prefix = s[line_start : m.start()]
        value_norm = _norm_alnum(value)
        if len(value_norm) >= 4 and value_norm in _norm_alnum(prefix):
            return m.group(0)

        txt = f"{label} {value}".strip()
        return f"<span style='color: {_GUIDELINE_ATTR_BLUE_HEX};'>{html.escape(txt)}</span>"

    result = _GUIDELINE_ATTR_SEGMENT_RE.sub(_repl, s)

    # Second pass: highlight inline grading inside parentheses
    # e.g. "(conditional recommendation, moderate certainty of evidence)"
    def _inline_repl(m: re.Match) -> str:
        content = m.group(1)
        if "<span" in content:
            return m.group(0)
        return f"(<span style='color: {_GUIDELINE_ATTR_BLUE_HEX};'>{html.escape(content)}</span>)"

    return _GUIDELINE_INLINE_GRADE_RE.sub(_inline_repl, result)


def render() -> None:
    st.title("📚 Single-study view")

    forced_selected: Optional[Dict[str, str]] = None
    open_pmid = (st.session_state.get("db_search_open_pmid") or "").strip()
    open_gid = (st.session_state.get("db_search_open_gid") or "").strip()

    if open_pmid:
        forced_selected = {"type": "paper", "pmid": open_pmid}
    elif open_gid:
        forced_selected = {"type": "guideline", "guideline_id": open_gid}

    q = st.text_input(
        "Search",
        placeholder='Search anything. Supports AND, OR, and "exact phrase"…',
        key="db_search_any",
    )
    st.caption('Example: `heart AND "reduced ejection fraction"` or `sepsis OR septic shock`')

    if (q or "").strip():
        st.session_state.pop("db_search_open_pmid", None)
        st.session_state.pop("db_search_open_gid", None)
        forced_selected = None

    rows: List[Dict[str, str]] = []
    selected: Optional[Dict[str, str]] = None

    if (q or "").strip():
        paper_rows = search_records(limit=SEARCH_MAX_DEFAULT, q=q)
        guideline_rows = search_guidelines(limit=SEARCH_MAX_DEFAULT, q=q)

        rows.extend(guideline_rows)
        rows.extend(paper_rows)

        if not rows:
            st.warning("No matches.")
            st.stop()

        selected = st.selectbox("Results", options=rows, format_func=_fmt_search_item, index=0)
    elif forced_selected:
        selected = forced_selected
    else:
        st.info("Type to search.")
        st.stop()

    if (selected.get("type") or "") != "guideline":
        selected_pmid = selected["pmid"]
        rec = get_record(selected_pmid)
        if not rec:
            st.error("Could not load that record.")
            st.stop()

        st.markdown(f"[Open in PubMed](https://pubmed.ncbi.nlm.nih.gov/{selected_pmid}/) — `{selected_pmid}`")

        title = (rec.get("title") or "").strip()
        if title:
            st.subheader(title)

        meta_bits = []
        if rec.get("journal"):
            meta_bits.append(rec["journal"])
        if rec.get("year"):
            year_str = rec["year"]
            pub_month = (rec.get("pub_month") or "").strip()
            if pub_month:
                year_str = f"{year_str}-{pub_month}"
            meta_bits.append(year_str)
        if meta_bits:
            st.caption(" • ".join(meta_bits))

        c1, c2, c3 = st.columns([1, 1, 2], gap="large")
        with c1:
            st.metric("Patients (N)", rec.get("patient_n") or "—")
        with c2:
            st.metric("Specialty", rec.get("specialty") or "—")
        with c3:
            tags_md = _tags_to_md(rec.get("study_design") or "")
            st.markdown(tags_md if tags_md else " ")

        st.divider()

        st.markdown("### P — Population")
        _render_bullets(rec.get("patient_details") or "", empty_hint="—")

        st.markdown("### I/C — Intervention / Comparison")
        _render_bullets(rec.get("intervention_comparison") or "", empty_hint="—")

        st.markdown("### O — Outcomes / Results")
        _render_bullets(rec.get("results") or "", empty_hint="—")

        concl = (rec.get("authors_conclusions") or "").strip()
        if concl:
            st.markdown("### Authors’ conclusion")
            st.markdown(concl)

        abstract = (rec.get("abstract") or "").strip()
        if abstract:
            with st.expander("Original abstract"):
                _render_plain_text(abstract)

        with st.expander("PubMed Related articles (top 5)"):
            try:
                neighbors = get_top_neighbors(selected_pmid, top_n=5)
                if not neighbors:
                    st.info("No related articles returned.")
                else:
                    for n in neighbors:
                        st.markdown(
                            f"- [{n['title'] or n['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{n['pmid']}/) — `{n['pmid']}`"
                        )
            except requests.HTTPError as e:
                st.error(f"Neighbors lookup failed: {e}")
            except Exception as e:
                st.error(f"Neighbors lookup error: {e}")

        with st.expander("Semantic Scholar similar papers (top 5)"):
            try:
                s2_papers = get_s2_similar_papers(selected_pmid, top_n=5)
                if not s2_papers:
                    st.info("No Semantic Scholar recommendations returned.")
                else:
                    for p in s2_papers:
                        title = (p.get("title") or "").strip() or (
                            p.get("pmid") or p.get("paperId") or "(no title)"
                        )
                        url = (p.get("url") or "").strip()
                        tag = ""
                        if (p.get("pmid") or "").strip():
                            tag = f" — `{p['pmid']}`"
                        elif (p.get("paperId") or "").strip():
                            tag = f" — `{p['paperId']}`"
                        if url:
                            st.markdown(f"- [{title}]({url}){tag}")
                        else:
                            st.markdown(f"- {title}{tag}")
            except ValueError as e:
                st.warning(str(e))
            except requests.HTTPError as e:
                st.error(f"Semantic Scholar lookup failed: {e}")
            except Exception as e:
                st.error(f"Semantic Scholar lookup error: {e}")

    else:
        gid = (selected.get("guideline_id") or "").strip()
        meta = get_guideline_meta(gid) or {}
        title = (meta.get("guideline_name") or "").strip() or (meta.get("filename") or "").strip() or (
            selected.get("title") or ""
        )
        st.subheader(f"📘 {title}")

        bits = []
        soc = (meta.get("society") or "").strip()
        y = (meta.get("pub_year") or "").strip()
        s = (meta.get("specialty") or "").strip()
        if soc:
            bits.append(soc)
        if y:
            bits.append(y)
        if s:
            bits.append(s)
        if bits:
            st.caption(" • ".join(bits))

        st.divider()

        public = is_public_mode()

        if not public:
            pending_del = (st.session_state.pop("db_search_delete_rec", "") or "").strip()
            if pending_del:
                nums = _parse_rec_nums(pending_del)
                if nums:
                    cur = (get_guideline_recommendations_display(gid) or "").strip()
                    new_md, removed = _delete_recs_from_guideline_md(cur, nums)
                    if removed:
                        update_guideline_recommendations_display(gid, new_md)
                        st.session_state[f"dbs_guideline_edit_{gid}"] = True
                        st.success(f"Deleted: {', '.join([f'#{n}' for n in removed])}")
                    else:
                        st.info("No matching recommendation numbers found.")

        disp = (get_guideline_recommendations_display(gid) or "").strip()
        disp = _clean_guideline_display(disp)
        disp_colored = _highlight_guideline_strength_evidence(disp)

        if public:
            edit_mode = False
        else:
            c_l, c_r = st.columns([6, 1], gap="small")
            with c_r:
                edit_mode = st.toggle(
                    "Quick Delete",
                    value=False,
                    key=f"dbs_guideline_edit_{gid}",
                )
            with c_l:
                if edit_mode:
                    st.caption(
                        "Click 🗑️ to delete a recommendation permanently. Recommendations can also be edited in the Guidelines page."
                    )

        if disp:
            if edit_mode:
                st.markdown(_guideline_md_with_delete_links(disp_colored, gid), unsafe_allow_html=True)
            else:
                st.markdown(disp_colored, unsafe_allow_html=True)
        else:
            st.info("No clinician-friendly recommendations display saved for this guideline yet.")
