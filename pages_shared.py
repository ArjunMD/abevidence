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
