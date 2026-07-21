import html
import os
import re
import time
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


# ---------------- Password gate (Reviews) ----------------
#
# A reusable password gate: any page that calls render_gate() shares ONE unlock,
# which lasts GATED_TTL_SECONDS before it is re-requested. State lives in
# session_state, so it naturally resets on a full browser reload / new tab —
# that keeps this dependency-free. Currently only the Reviews page uses it.

GATED_TTL_SECONDS = 12 * 3600  # how long a single unlock stays valid
_GATED_AT_KEY = "gated_authed_at"


def gated_password() -> str:
    """Shared password for the gated pages. st.secrets first, then env var.
    Empty means unconfigured, in which case the pages refuse access."""
    try:
        if "NOTES_PASSWORD" in st.secrets:
            return str(st.secrets["NOTES_PASSWORD"]).strip()
    except Exception:
        pass
    return os.environ.get("NOTES_PASSWORD", "").strip()


def gated_unlocked() -> bool:
    ts = st.session_state.get(_GATED_AT_KEY)
    try:
        return bool(ts) and (time.time() - float(ts)) < GATED_TTL_SECONDS
    except Exception:
        return False


def gated_unlock() -> None:
    st.session_state[_GATED_AT_KEY] = time.time()


def gated_lock() -> None:
    st.session_state.pop(_GATED_AT_KEY, None)


def render_gate(page_title: str) -> bool:
    """Return True if the shared gate is unlocked. Otherwise render the password
    UI (or a config warning) and return False. `page_title` names the page for
    the headings, e.g. "Reviews"."""
    configured = gated_password()
    if not configured:
        st.title(f"🔒 {page_title}")
        st.warning(
            "No password configured. Add `NOTES_PASSWORD` to `.streamlit/secrets.toml` "
            "(local) or your hosting provider's secrets (deployed) to enable this page."
        )
        return False

    if gated_unlocked():
        return True

    st.title(f"🔒 {page_title}")
    st.caption("Password-protected — may contain excerpts from copyrighted material for personal reference only.")
    with st.form(f"gate_form_{page_title}"):
        candidate = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock")
    if submitted:
        if candidate and candidate == configured:
            gated_unlock()
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


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


def _split_specialties(raw: str) -> list[str]:
    s = (raw or "").strip()
    if not s:
        return ["Unspecified"]
    toks = re.split(r"[,\n;|]+", s)
    out: list[str] = []
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


def _fmt_article(r: dict[str, str]) -> str:
    title = (r.get("title") or "").strip() or "(no title)"
    journal = display_journal(r.get("journal") or "")
    year = (r.get("year") or "").strip()

    bits: list[str] = []
    if journal:
        bits.append(journal)
    if year:
        bits.append(year)

    meta = " • ".join(bits)
    return f"{title}{f' — {meta}' if meta else ''}"


def _fmt_search_item(it: dict[str, str]) -> str:
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


def _filter_search_pubmed_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    valid_rows: list[dict[str, str]] = []
    pmids: list[str] = []
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

    out: list[dict[str, str]] = []
    for r in valid_rows:
        pmid = (r.get("pmid") or "").strip()
        if pmid in blocked:
            continue
        out.append(r)
    return out


def _year_sort_key(y: str) -> tuple[int, str]:
    ys = (y or "").strip()
    if re.fullmatch(r"\d{4}", ys):
        return (0, ys)
    if not ys:
        return (2, "0000")
    return (1, ys)


def _parse_rec_nums(raw: str) -> list[int]:
    s = (raw or "").strip()
    if not s:
        return []
    nums: list[int] = []
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


def _delete_recs_from_guideline_md(md: str, delete_nums: list[int]) -> tuple[str, list[int]]:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    delete_set = {int(n) for n in (delete_nums or []) if isinstance(n, int) and n > 0}
    if not delete_set:
        return (md or "").strip(), []

    removed: list[int] = []
    filtered: list[str] = []

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

    out: list[str] = []
    i = 0
    while i < len(filtered):
        line = filtered[i]
        if line.startswith("### "):
            heading = line
            i += 1
            block: list[str] = []
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
    removed_ordered: list[int] = []
    for n in removed:
        if n in seen:
            continue
        seen.add(n)
        removed_ordered.append(n)

    return new_md, removed_ordered


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


def _split_guideline_sections(md: str) -> list[tuple[str, list[str]]]:
    """Split cleaned display markdown into (section_title, lines) pairs.

    Level-3 ('### ') headings start a new section. Any content before the first
    heading is returned as a leading section with an empty title."""
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    sections: list[tuple[str, list[str]]] = []
    cur_title = ""
    cur_lines: list[str] = []

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


# Strength → colored dot (5-tier). The dot encodes the recommendation's strength;
# Level of Evidence stays as text. Covers ACC/AHA COR, GRADE, and practice
# statements. COR direction is explicit in the class; GRADE direction is inferred
# from the recommendation text.
_DOT_STRONG = "🟢"
_DOT_MODERATE = "🟡"
_DOT_WEAK = "🟠"
_DOT_AGAINST = "🔴"
_DOT_PRACTICE = "⚪"

# Sort rank for ordering recommendations within a (sub)section: strongest first,
# then negatives, then practice points, then ungraded.
_DOT_ORDER = {_DOT_STRONG: 0, _DOT_MODERATE: 1, _DOT_WEAK: 2, _DOT_AGAINST: 3, _DOT_PRACTICE: 4}


def _dot_rank(dot: str) -> int:
    return _DOT_ORDER.get(dot, 5)

_STRENGTH_VALUE_RE = re.compile(r"Strength:\s*([^;)\n<]+)", re.IGNORECASE)
_GRADE_INLINE_RE = re.compile(
    r"\b(strong recommendation|weak recommendation|conditional recommendation|"
    r"good practice statement|best[- ]practice statement|clinical principle|expert opinion)\b",
    re.IGNORECASE,
)
# A recommendation phrased AGAINST an action (used only for GRADE-style strengths).
# Deliberately excludes a bare "do not", which matches patient-population descriptors
# like "patients who do not have SIRS" rather than a recommendation direction.
_AGAINST_RE = re.compile(
    r"(?:recommend|suggest|advise)\w*\s+against|\bshould not\b|"
    r"\bis not recommended\b|\bare not recommended\b|"
    r"\bnot be (?:used|performed|administered|given|routinely)\b|"
    r"\bwe recommend not\b|\bwe suggest not\b|\bnot offering\b|\bnot prescribing\b",
    re.IGNORECASE,
)


def _guideline_strength_dot(body: str) -> str:
    """Return the colored strength dot for a recommendation, or '' if ungraded."""
    text = body or ""
    m = _STRENGTH_VALUE_RE.search(text)
    if m:
        raw = m.group(1)
    else:
        gm = _GRADE_INLINE_RE.search(text)
        raw = gm.group(1) if gm else ""
    v = raw.strip().lower()
    if not v:
        return ""
    against = bool(_AGAINST_RE.search(text))

    # ACC/AHA COR — direction is explicit in the class, so no against-flip.
    if re.search(r"(?:^|[^a-z0-9])(?:3|iii)(?:[^a-z0-9]|$)", v) or "harm" in v or "no benefit" in v or "no-benefit" in v:
        return _DOT_AGAINST
    if re.search(r"\b2a\b|\biia\b", v):
        return _DOT_MODERATE
    if re.search(r"\b2b\b|\biib\b", v):
        return _DOT_WEAK
    if re.search(r"(?:^|[^a-z0-9])(?:1|i)(?:[^a-z0-9]|$)", v) or re.search(r"grade\s*-?\s*1", v):
        return _DOT_STRONG
    # GRADE — direction inferred from the recommendation text.
    if "strong" in v:
        return _DOT_AGAINST if against else _DOT_STRONG
    if "moderate" in v:
        return _DOT_MODERATE
    if "conditional" in v or "weak" in v:
        return _DOT_AGAINST if against else _DOT_WEAK
    # Practice statements / consensus.
    if "practice" in v or "clinical principle" in v or "expert opinion" in v or "consensus" in v:
        return _DOT_PRACTICE
    return ""


def _strip_strength_label(body: str) -> str:
    """Remove the now-redundant 'Strength: X' text (a dot replaces it), keeping the
    Level of Evidence."""
    s = body or ""
    # "(Strength: X; Evidence: Y)" -> "(Evidence: Y)"
    s = re.sub(r"\(\s*Strength:\s*[^;)\n]+;\s*(Evidence:)", r"(\1", s, flags=re.IGNORECASE)
    # "(Strength: X)" with no Evidence -> drop the parenthetical
    s = re.sub(r"\s*\(\s*Strength:\s*[^)\n]+\)", "", s, flags=re.IGNORECASE)
    # stray "Strength: X;" outside parentheses -> drop
    s = re.sub(r"\s*Strength:\s*[^;)\n]+;\s*", " ", s, flags=re.IGNORECASE)
    return s


def _strip_evidence(body: str) -> str:
    """Remove the Level-of-Evidence text (kept in storage, hidden by default in the
    display). Drops '(Evidence: Y)' as well as inline grade parentheticals, since the
    strength dot already conveys the recommendation class."""
    s = body or ""
    s = re.sub(r"\s*\(\s*Evidence:\s*[^)\n]*\)", "", s, flags=re.IGNORECASE)
    s = _GUIDELINE_INLINE_GRADE_RE.sub("", s)
    s = re.sub(r"\s*;\s*Evidence:\s*[^)\n;<]+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[ \t]+(<br\s*/?>)", r"\1", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


# Level-of-Evidence text that the "Show level of evidence" toggle reveals: an
# "(Evidence: …)" or "; Evidence: …" segment, or an inline grade parenthetical.
# Checked against the strength-stripped text because the Strength label is removed
# in both modes, so a "(Strength: strong recommendation)" parenthetical on its own
# is not something the toggle reveals.
_EVIDENCE_SEGMENT_RE = re.compile(r"\(\s*Evidence:|;\s*Evidence:", re.IGNORECASE)


def guideline_has_evidence(md: str) -> bool:
    """True if the guideline display has any Level-of-Evidence text the toggle would
    reveal. Lets callers hide the toggle for guidelines (e.g. anaphylaxis) that carry
    no evidence grading, so it only appears when there is something to reveal."""
    disp = _clean_guideline_display(md)
    if not disp:
        return False
    base = _strip_strength_label(disp)
    return bool(_EVIDENCE_SEGMENT_RE.search(base) or _GUIDELINE_INLINE_GRADE_RE.search(base))


def _format_guideline_rec_body(body: str, show_evidence: bool) -> tuple[str, str]:
    """Return (strength_dot, html_body) for a recommendation body: derive the dot,
    strip the redundant Strength text, optionally hide the Level of Evidence, and
    colorize whatever remains."""
    dot = _guideline_strength_dot(body)
    stripped = _strip_strength_label(body)
    if not show_evidence:
        stripped = _strip_evidence(stripped)
    return dot, _highlight_guideline_strength_evidence(stripped)


def _render_guideline_rec_lines(lines: list[str], gid: str, edit_mode: bool, show_evidence: bool) -> None:
    """Render a section's recommendations, ordered by strength dot (strongest first),
    with numbering restarted at 1. Delete links keep the ORIGINAL stored number so
    deletion still targets the right recommendation."""
    rec_entries: list[tuple[int, str]] = []
    preamble: list[str] = []
    for ln in lines:
        m = _REC_LINE_RE.match(ln)
        if m:
            rec_entries.append((int(m.group(1)), ln))
        elif ln.strip():
            preamble.append(ln)

    if preamble:
        st.markdown(
            "\n".join(_highlight_guideline_strength_evidence(p) for p in preamble).strip(),
            unsafe_allow_html=True,
        )

    # Stable sort by strength tier (preserves original order within a tier).
    rec_entries.sort(key=lambda e: _dot_rank(_guideline_strength_dot(_REC_LINE_RE.match(e[1]).group(2))))

    out: list[str] = []
    for k, (num, ln) in enumerate(rec_entries, start=1):
        icon = (_guideline_delete_icon(gid, num) + " ") if edit_mode else ""
        dot, body = _format_guideline_rec_body(_REC_LINE_RE.match(ln).group(2), show_evidence)
        prefix = f"{dot} " if dot else ""
        out.append(f"{prefix}**{k}.** {icon}{body}")
    body = "\n".join(out).strip()
    if body:
        st.markdown(body, unsafe_allow_html=True)


# Sections whose recommendations are grouped into per-entity subsections, and the
# order in which they are pinned to the top of the display (when present).
GUIDELINE_TOP_SECTIONS: list[str] = [
    "Labs",
    "Imaging",
    "Diagnostic procedures",
    "Medicines",
    "Therapeutic procedures",
]
_GUIDELINE_GROUPED_SECTIONS = {s.lower() for s in GUIDELINE_TOP_SECTIONS}
_GUIDELINE_TOP_ORDER = {s.lower(): i for i, s in enumerate(GUIDELINE_TOP_SECTIONS)}


def _render_guideline_grouped(
    lines: list[str], gid: str, edit_mode: bool, rec_labels: dict[int, str], show_evidence: bool
) -> None:
    """Render a grouped section (Medicines / Labs / Imaging / procedures) into bold
    per-entity subsections. Numbering restarts at 1 for the section and runs across
    the subsections in display order."""
    rec_entries: list[tuple[int, str]] = []
    preamble: list[str] = []
    for ln in lines:
        m = _REC_LINE_RE.match(ln)
        if m:
            rec_entries.append((int(m.group(1)), ln))
        elif ln.strip():
            preamble.append(ln)

    if preamble:
        st.markdown(
            "\n".join(_highlight_guideline_strength_evidence(p) for p in preamble).strip(),
            unsafe_allow_html=True,
        )

    OTHER = "Other"
    order: list[str] = []
    groups: dict[str, list[tuple[int, str]]] = {}
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
        # Stable sort each subsection by strength tier (strongest first).
        group = sorted(
            groups[lab],
            key=lambda e: _dot_rank(_guideline_strength_dot(_REC_LINE_RE.match(e[1]).group(2))),
        )
        out: list[str] = []
        for num, ln in group:
            k += 1
            dot, body = _format_guideline_rec_body(_REC_LINE_RE.match(ln).group(2), show_evidence)
            icon = (_guideline_delete_icon(gid, num) + " ") if edit_mode else ""
            prefix = f"{dot} " if dot else ""
            out.append(f"{prefix}**{k}.** {icon}{body}")
        st.markdown("\n".join(out).strip(), unsafe_allow_html=True)
        st.markdown("")


def _order_guideline_sections(
    sections: list[tuple[str, list[str]]]
) -> list[tuple[str, list[str]]]:
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


def _render_guideline_acronym_legend(acronyms: list[tuple[str, str, bool]]) -> None:
    """Render the abbreviations legend as a collapsed expander at the top."""
    rows = [a for a in (acronyms or []) if a and a[0] and a[1]]
    if not rows:
        return
    with st.expander(f"Abbreviations ({len(rows)})", expanded=False):
        lines = []
        for acr, exp, uncertain in rows:
            mark = " *(?)*" if uncertain else ""
            lines.append(f"**{html.escape(acr)}** — {html.escape(exp)}{mark}")
        st.markdown("  \n".join(lines), unsafe_allow_html=True)


def _render_guideline_strength_legend(disp: str) -> None:
    """Render the strength-dot key as a caption, only if any recommendation is graded."""
    has_dot = any(
        _REC_LINE_RE.match(ln) and _guideline_strength_dot(_REC_LINE_RE.match(ln).group(2))
        for ln in disp.split("\n")
    )
    if not has_dot:
        return
    st.caption(
        f"{_DOT_STRONG} Strong · {_DOT_MODERATE} Moderate · {_DOT_WEAK} Weak · "
        f"{_DOT_AGAINST} Against / harm / no benefit · {_DOT_PRACTICE} Practice point"
    )


def render_guideline_display(
    raw_md: str,
    gid: str,
    *,
    edit_mode: bool = False,
    rec_labels: dict[int, str] | None = None,
    acronyms: list[tuple[str, str, bool]] | None = None,
    show_evidence: bool = False,
    default_expanded: bool = False,
) -> None:
    """Render a guideline's clinician-friendly display: a collapsed abbreviations
    legend at the top, then each section in its own expander (the lab/imaging/
    procedure/medicine sections pinned to the top), recommendation numbering
    restarted per section, and grouped sections split into per-entity subsections
    when labels are available."""
    disp = _clean_guideline_display(raw_md)
    if not disp.strip():
        st.info("No clinician-friendly recommendations display saved for this guideline yet.")
        return

    _render_guideline_acronym_legend(acronyms)
    _render_guideline_strength_legend(disp)
    rec_labels = rec_labels or {}
    for title, lines in _order_guideline_sections(_split_guideline_sections(disp)):
        if not title:
            body = "\n".join(_highlight_guideline_strength_evidence(l) for l in lines).strip()
            if body:
                st.markdown(body, unsafe_allow_html=True)
            continue
        is_pinned = title.strip().lower() in _GUIDELINE_TOP_ORDER
        with st.expander(title, expanded=default_expanded or is_pinned):
            if title.strip().lower() in _GUIDELINE_GROUPED_SECTIONS and rec_labels:
                _render_guideline_grouped(lines, gid, edit_mode, rec_labels, show_evidence)
            else:
                _render_guideline_rec_lines(lines, gid, edit_mode, show_evidence)


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


def clear_public_study_overlay() -> None:
    """Reset the public single-study overlay back to the Browse list. Shared by
    app.py (sidebar nav callback) and the Single-study view's "Back to studies"
    buttons so the overlay state is torn down the same way in every place."""
    st.session_state["public_study_overlay"] = False
    st.session_state.pop("db_search_open_pmid", None)
    st.session_state.pop("db_search_open_gid", None)
