import html
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import quote_plus

import streamlit as st

from db import (
    get_hidden_pubmed_pmids,
    get_saved_pmids,
)

SEARCH_MAX_DEFAULT = 1500
BROWSE_MAX_ROWS = 30000
GUIDELINES_MAX_LIST = 30000


def is_public_mode() -> bool:
    """Whether the app is running in read-only public mode (the hosted .com
    site sets ABEV_MODE=public). Personal/local mode is the default."""
    return os.environ.get("ABEV_MODE", "personal").strip().lower() == "public"


# Matches a trailing place/edition qualifier, e.g. " (London, England)" or
# " (Clinical research ed.)".
_JOURNAL_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def display_journal(name: str) -> str:
    """Clean a stored NLM journal name for display only (the DB value is left
    untouched). Drops the ': official journal of …' subtitle and a trailing
    place/edition qualifier, preserving the source casing so acronyms like BMJ
    or JAMA stay intact. Examples:
      'Clinical infectious diseases : an official publication…' -> 'Clinical infectious diseases'
      'Critical care (London, England)'                          -> 'Critical care'
    """
    s = (name or "").strip()
    if not s:
        return ""
    # NLM appends the issuing society after a colon; drop it.
    if ":" in s:
        s = s.split(":", 1)[0].strip()
    # Drop a trailing parenthetical qualifier.
    s = _JOURNAL_PAREN_SUFFIX_RE.sub("", s).strip()
    return s


_REC_LINE_RE = re.compile(r"^\s*(?:-\s+)?\*\*(?:Rec\s+)?(\d+)\.\*\*\s*(.*)$")


def _clean_pmid(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    m = re.search(r"(\d{1,10})", s)
    return m.group(1) if m else ""


def _split_specialties(raw: str) -> List[str]:
    s = (raw or "").strip()
    if not s:
        return ["Unspecified"]
    toks = re.split(r"[,\n;|]+", s)
    out: List[str] = []
    seen = set()
    for t in toks:
        t = (t or "").strip().strip("-•").strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out or ["Unspecified"]


def _fmt_article(r: Dict[str, str]) -> str:
    title = (r.get("title") or "").strip() or "(no title)"
    journal = display_journal(r.get("journal") or "")
    year = (r.get("year") or "").strip()

    bits: List[str] = []
    if journal:
        bits.append(journal)
    if year:
        bits.append(year)

    meta = " • ".join(bits)
    return f"{title}{f' — {meta}' if meta else ''}"


def _fmt_search_item(it: Dict[str, str]) -> str:
    if (it.get("type") or "") == "guideline":
        title = (it.get("title") or "").strip() or "(no name)"
        year = (it.get("year") or "").strip()
        meta = year
        return f"{title}{f' — {meta}' if meta else ''}"
    return _fmt_article(it)


def _tags_to_md(tags_csv: str) -> str:
    s = (tags_csv or "").strip()
    if not s:
        return ""
    toks = [t.strip() for t in s.split(",") if t.strip()]
    if not toks:
        return ""
    return " ".join([f"`{t}`" for t in toks])


def _render_bullets(text: str, empty_hint: str = "—") -> None:
    s = (text or "").strip()
    if not s:
        st.markdown(empty_hint)
        return
    if not s.startswith("- "):
        s = "\n".join([("- " + ln.strip()) for ln in s.splitlines() if ln.strip()])
    st.markdown(s)


def _render_plain_text(text: str, empty_hint: str = "—") -> None:
    s = (text or "").strip()
    if not s:
        st.markdown(empty_hint)
        return

    safe = html.escape(s).replace("\n", "<br>")
    st.markdown(f"<div style='white-space: pre-wrap;'>{safe}</div>", unsafe_allow_html=True)


def _filter_search_pubmed_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    valid_rows: List[Dict[str, str]] = []
    pmids: List[str] = []
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        pmid = (r.get("pmid") or "").strip()
        if not pmid:
            continue
        valid_rows.append(r)
        pmids.append(pmid)

    if not valid_rows:
        return []

    saved_pmids = get_saved_pmids(pmids)
    hidden_pmids = get_hidden_pubmed_pmids(pmids)
    blocked = saved_pmids.union(hidden_pmids)
    if not blocked:
        return valid_rows

    out: List[Dict[str, str]] = []
    for r in valid_rows:
        pmid = (r.get("pmid") or "").strip()
        if pmid in blocked:
            continue
        out.append(r)
    return out


def _year_sort_key(y: str) -> Tuple[int, str]:
    ys = (y or "").strip()
    if re.fullmatch(r"\d{4}", ys):
        return (0, ys)
    if not ys:
        return (2, "0000")
    return (1, ys)


def _parse_rec_nums(raw: str) -> List[int]:
    s = (raw or "").strip()
    if not s:
        return []
    nums: List[int] = []
    seen = set()
    for tok in re.findall(r"\d+", s):
        try:
            n = int(tok)
        except Exception:
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        nums.append(n)
    return nums


def _delete_recs_from_guideline_md(md: str, delete_nums: List[int]) -> Tuple[str, List[int]]:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    delete_set = set(int(n) for n in (delete_nums or []) if isinstance(n, int) and n > 0)
    if not delete_set:
        return (md or "").strip(), []

    removed: List[int] = []
    filtered: List[str] = []

    for ln in lines:
        m = _REC_LINE_RE.match(ln)
        if m:
            try:
                old_n = int(m.group(1))
            except Exception:
                old_n = -1
            if old_n in delete_set:
                removed.append(old_n)
                continue
        filtered.append(ln)

    if not removed:
        return (md or "").strip(), []

    out: List[str] = []
    i = 0
    while i < len(filtered):
        line = filtered[i]
        if line.startswith("### "):
            heading = line
            i += 1
            block: List[str] = []
            while i < len(filtered) and not filtered[i].startswith("### "):
                block.append(filtered[i])
                i += 1

            has_rec = any(_REC_LINE_RE.match(b or "") for b in block)
            has_meaningful_nonrec = any(
                (b or "").strip() and not _REC_LINE_RE.match(b or "")
                for b in block
            )

            if has_rec or has_meaningful_nonrec:
                out.append(heading)
                out.extend(block)
            else:
                if out and out[-1].strip():
                    out.append("")
        else:
            out.append(line)
            i += 1

    new_md = "\n".join(out).strip()

    still_has_any_rec = any(_REC_LINE_RE.match(ln or "") for ln in out)
    if not still_has_any_rec:
        if new_md:
            new_md += "\n\n_No recommendations remaining._"
        else:
            new_md = "_No recommendations remaining._"

    seen = set()
    removed_ordered: List[int] = []
    for n in removed:
        if n in seen:
            continue
        seen.add(n)
        removed_ordered.append(n)

    return new_md, removed_ordered


def _guideline_md_with_delete_links(md: str, gid: str) -> str:
    base = md or ""
    gid_q = quote_plus((gid or "").strip())

    pat = re.compile(r"(?m)^(\s*(?:-\s+)?\*\*(?:Rec\s+)?(\d+)\.\*\*)(\s*)")

    def repl(m: re.Match) -> str:
        num = m.group(2)
        icon = (
            f"<a href='?gid={gid_q}&delrec={num}' target='_self' "
            f"title='Delete #{num}' "
            f"style='text-decoration:none; opacity:0.35; margin-left:0.25rem;'>🗑️</a>"
        )
        return f"{m.group(1)} {icon}{m.group(3)}"

    return pat.sub(repl, base)


# ---------------- Guideline display: cleanup, colorization, sectioned render ----------------

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


def _guideline_delete_icon(gid: str, num) -> str:
    gid_q = quote_plus((gid or "").strip())
    return (
        f"<a href='?gid={gid_q}&delrec={num}' target='_self' "
        f"title='Delete #{num}' "
        f"style='text-decoration:none; opacity:0.35; margin-left:0.25rem;'>🗑️</a>"
    )


def _split_guideline_sections(md: str) -> List[Tuple[str, List[str]]]:
    """Split cleaned display markdown into (section_title, lines) pairs.

    Level-3 ('### ') headings start a new section. Any content before the first
    heading is returned as a leading section with an empty title."""
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    sections: List[Tuple[str, List[str]]] = []
    cur_title = ""
    cur_lines: List[str] = []

    def _flush() -> None:
        if cur_title or any(ln.strip() for ln in cur_lines):
            sections.append((cur_title, cur_lines))

    for ln in text.split("\n"):
        if ln.startswith("### "):
            _flush()
            cur_title = ln[4:].strip()
            cur_lines = []
        else:
            cur_lines.append(ln)
    _flush()
    return sections


def _render_guideline_rec_lines(lines: List[str], gid: str, edit_mode: bool) -> None:
    """Render a section's lines, restarting recommendation numbering at 1.
    Delete links keep the ORIGINAL stored number so deletion still targets the
    right recommendation."""
    out: List[str] = []
    k = 0
    for ln in lines:
        m = _REC_LINE_RE.match(ln)
        if m:
            k += 1
            icon = (_guideline_delete_icon(gid, m.group(1)) + " ") if edit_mode else ""
            out.append(f"**{k}.** {icon}{m.group(2)}")
        else:
            out.append(ln)
    body = "\n".join(out).strip()
    if body:
        st.markdown(body, unsafe_allow_html=True)


# Sections whose recommendations are grouped into per-entity subsections, and the
# order in which they are pinned to the top of the display (when present).
GUIDELINE_TOP_SECTIONS: List[str] = [
    "Labs",
    "Imaging",
    "Diagnostic procedures",
    "Medicines",
    "Therapeutic procedures",
]
_GUIDELINE_GROUPED_SECTIONS = {s.lower() for s in GUIDELINE_TOP_SECTIONS}
_GUIDELINE_TOP_ORDER = {s.lower(): i for i, s in enumerate(GUIDELINE_TOP_SECTIONS)}


def _render_guideline_grouped(
    lines: List[str], gid: str, edit_mode: bool, rec_labels: Dict[int, str]
) -> None:
    """Render a grouped section (Medicines / Labs / Imaging / procedures) into bold
    per-entity subsections. Numbering restarts at 1 for the section and runs across
    the subsections in display order."""
    rec_entries: List[Tuple[int, str]] = []
    preamble: List[str] = []
    for ln in lines:
        m = _REC_LINE_RE.match(ln)
        if m:
            rec_entries.append((int(m.group(1)), ln))
        elif ln.strip():
            preamble.append(ln)

    if preamble:
        st.markdown("\n".join(preamble).strip(), unsafe_allow_html=True)

    OTHER = "Other"
    order: List[str] = []
    groups: Dict[str, List[Tuple[int, str]]] = {}
    for num, ln in rec_entries:
        lab = (rec_labels.get(num) or "").strip() or OTHER
        if lab not in groups:
            groups[lab] = []
            order.append(lab)
        groups[lab].append((num, ln))

    # Keep "Other" last so unlabeled items don't lead the section.
    if OTHER in order:
        order = [m for m in order if m != OTHER] + [OTHER]

    k = 0
    for lab in order:
        st.markdown(f"**{lab}**")
        out: List[str] = []
        for num, ln in groups[lab]:
            k += 1
            body = _REC_LINE_RE.match(ln).group(2)
            icon = (_guideline_delete_icon(gid, num) + " ") if edit_mode else ""
            out.append(f"**{k}.** {icon}{body}")
        st.markdown("\n".join(out).strip(), unsafe_allow_html=True)
        st.markdown("")


def _order_guideline_sections(
    sections: List[Tuple[str, List[str]]]
) -> List[Tuple[str, List[str]]]:
    """Pin the grouped sections to the top in GUIDELINE_TOP_SECTIONS order (when
    present); keep everything else in its original relative order afterward. Any
    leading untitled preamble stays first."""
    preamble = [s for s in sections if not s[0]]
    titled = [s for s in sections if s[0]]
    pinned = sorted(
        [s for s in titled if s[0].strip().lower() in _GUIDELINE_TOP_ORDER],
        key=lambda s: _GUIDELINE_TOP_ORDER[s[0].strip().lower()],
    )
    rest = [s for s in titled if s[0].strip().lower() not in _GUIDELINE_TOP_ORDER]
    return preamble + pinned + rest


def render_guideline_display(
    raw_md: str,
    gid: str,
    *,
    edit_mode: bool = False,
    rec_labels: Dict[int, str] = None,
    default_expanded: bool = False,
) -> None:
    """Render a guideline's clinician-friendly display: each section in its own
    expander (the lab/imaging/procedure/medicine sections pinned to the top),
    recommendation numbering restarted per section, and grouped sections split into
    per-entity subsections when labels are available."""
    disp = _clean_guideline_display(raw_md)
    disp = _highlight_guideline_strength_evidence(disp)
    if not disp.strip():
        st.info("No clinician-friendly recommendations display saved for this guideline yet.")
        return

    rec_labels = rec_labels or {}
    for title, lines in _order_guideline_sections(_split_guideline_sections(disp)):
        if not title:
            body = "\n".join(lines).strip()
            if body:
                st.markdown(body, unsafe_allow_html=True)
            continue
        with st.expander(title, expanded=default_expanded):
            if title.strip().lower() in _GUIDELINE_GROUPED_SECTIONS and rec_labels:
                _render_guideline_grouped(lines, gid, edit_mode, rec_labels)
            else:
                _render_guideline_rec_lines(lines, gid, edit_mode)


def _qp_first(qp: dict, key: str) -> str:
    v = qp.get(key)
    if isinstance(v, list):
        return v[0] if v else ""
    return str(v) if v is not None else ""


def _get_query_params() -> dict:
    return dict(st.query_params)


def _clear_query_params() -> None:
    st.query_params.clear()


def _browse_search_link(*, pmid: str = "", gid: str = "") -> str:
    if pmid:
        return (
            f"<a href='?pmid={quote_plus(pmid)}' target='_self' title='Open in Single-study view' "
            f"style='text-decoration:none; opacity:0.45; margin-left:0.35rem; font-size:0.9em;'>🔎</a>"
        )
    if gid:
        return (
            f"<a href='?gid={quote_plus(gid)}' target='_self' title='Open in Single-study view' "
            f"style='text-decoration:none; opacity:0.45; margin-left:0.35rem; font-size:0.9em;'>🔎</a>"
        )
    return ""


def _browse_manage_link(*, pmid: str = "", gid: str = "") -> str:
    """Backend-only link that jumps to the Manage page with this item pre-selected
    for editing/deleting. Routed by app.py via the manage_pmid / manage_gid query
    params. Never rendered in public mode."""
    if pmid:
        return (
            f"<a href='?manage_pmid={quote_plus(pmid)}' target='_self' title='Open in Manage (edit / delete)' "
            f"style='text-decoration:none; opacity:0.45; margin-left:0.3rem; font-size:0.9em;'>✏️</a>"
        )
    if gid:
        return (
            f"<a href='?manage_gid={quote_plus(gid)}' target='_self' title='Open in Manage (edit / delete)' "
            f"style='text-decoration:none; opacity:0.45; margin-left:0.3rem; font-size:0.9em;'>✏️</a>"
        )
    return ""


def _format_date_added(iso_str: str) -> str:
    s = (iso_str or "").strip()
    if not s:
        return "—"
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%b ") + str(dt.day) + dt.strftime(", %Y")
    except Exception:
        return s[:10] if len(s) >= 10 else s or "—"
