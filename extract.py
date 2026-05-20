# extract.py
import re
import time
import random
import json
import io
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

import requests
import streamlit as st
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote

try:
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import DocumentContentFormat
except Exception:
    AzureKeyCredential = None
    DocumentIntelligenceClient = None
    DocumentContentFormat = None

if TYPE_CHECKING:
    from azure.ai.documentintelligence import DocumentIntelligenceClient as DocumentIntelligenceClientType

# ---- imports from db layer (must exist in db.py) ----
from db import (
    get_guideline_meta,
    update_guideline_metadata,
    update_guideline_recommendations_display,
)

# ---------------- Constants ----------------

NCBI_TOOL = "streamlit-pmid-abstract"
NCBI_EMAIL = ""
NCBI_API_KEY = ""

NCBI_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
NCBI_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
NCBI_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

GUIDELINE_OPENAI_STRICTNESS = "medium"  # "strict" | "medium" | "loose"

SECTION_TRIAGE_BATCH = 10
SECTION_PREVIEW_HEAD_CHARS = 1200
SECTION_PREVIEW_TAIL_CHARS = 700
SECTION_PREVIEW_MAX_HINT_LINES = 28
SECTION_MAX_CHARS_SEND = 14000
SECTION_PART_OVERLAP_CHARS = 600


_RECO_HINT_RE = re.compile(
    r"(?i)\b(recommend|recommended|should|we suggest|we recommend|is indicated|are indicated|is not recommended|do not|avoid|consider)\b"
)
_LOE_HINT_RE = re.compile(
    r"(?i)\b(level of evidence|loe|class\b|grade\b|grading\b|certainty|strong recommendation|conditional recommendation)\b"
)

_GUIDELINE_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

_PUBMED_MONTH_NAME_TO_NUM = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

# ---------------- Section-based recommendation pipeline ----------------

def _heading_level(line: str) -> int:
    ln = (line or "").lstrip()
    if not ln.startswith("#"):
        return 0
    return len(ln) - len(ln.lstrip("#"))

def _heading_text(line: str) -> str:
    return (line or "").lstrip("#").strip()

def _path_from_stack(stack: List[str]) -> str:
    parts = [p.strip() for p in (stack or []) if p and p.strip()]
    return " > ".join(parts).strip()

def _split_markdown_into_sections(md: str) -> List[Dict[str, str]]:
    """
    Turn markdown into sections keyed by a full heading-path.
    A new section begins at each heading and continues until the next heading.
    """
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    sections: List[Dict[str, str]] = []
    heading_stack: List[str] = []

    current_path = ""
    current_level = 0
    buf: List[str] = []

    def flush():
        nonlocal buf, current_path, current_level
        content = "\n".join(buf).strip()
        buf = []
        if content:
            sections.append(
                {
                    "path": current_path or "(no heading)",
                    "level": str(int(current_level or 0)),
                    "content": content,
                }
            )

    for ln in lines:
        lvl = _heading_level(ln)
        if lvl > 0:
            # New heading -> flush previous section content
            flush()

            title = _heading_text(ln)
            # Maintain a stack where index = level-1
            if lvl <= 0:
                heading_stack = []
            else:
                heading_stack = heading_stack[: max(0, lvl - 1)]
            heading_stack.append(title or "(untitled)")
            current_path = _path_from_stack(heading_stack)
            current_level = lvl

            # Keep the heading line as part of section content (helps GPT)
            buf.append(ln.strip())
            continue

        # normal line
        buf.append(ln)

    flush()

    # If no headings exist, treat whole doc as one section
    if not sections:
        whole = (md or "").strip()
        if whole:
            sections = [{"path": "(no heading)", "level": "0", "content": whole}]

    # assign stable sec_idx in traversal order
    out: List[Dict[str, str]] = []
    for i, s in enumerate(sections, start=1):
        out.append(
            {
                "sec_idx": str(i),
                "path": (s.get("path") or "").strip() or "(no heading)",
                "level": (s.get("level") or "0").strip(),
                "content": (s.get("content") or "").strip(),
            }
        )
    return out

def _section_preview(section_text: str) -> str:
    """
    Preview = head + tail + a few "high-signal" lines that contain recommendation hints.
    Helps triage without missing recs that appear late in a section.
    """
    s = (section_text or "").strip()
    if not s:
        return ""

    head = s[: max(0, SECTION_PREVIEW_HEAD_CHARS)]
    tail = s[-max(0, SECTION_PREVIEW_TAIL_CHARS) :] if len(s) > SECTION_PREVIEW_TAIL_CHARS else ""

    # Hint lines: any line matching recommendation or grading regex
    hint_lines: List[str] = []
    for ln in s.splitlines():
        t = (ln or "").strip()
        if not t:
            continue
        if _RECO_HINT_RE.search(t) or _LOE_HINT_RE.search(t) or re.match(r"(?i)^\s*(recommendation|statement|practice point)\b", t):
            hint_lines.append(t[:240])
        if len(hint_lines) >= SECTION_PREVIEW_MAX_HINT_LINES:
            break

    parts = []
    parts.append("HEAD:\n" + head)
    if hint_lines:
        parts.append("HINT_LINES:\n" + "\n".join(hint_lines))
    if tail and tail != head:
        parts.append("TAIL:\n" + tail)
    return "\n\n".join(parts).strip()

def _split_large_section(text: str, max_chars: int, overlap: int) -> List[str]:
    """
    Split oversized sections into overlapping parts (best-effort, keeps context).
    """
    s = (text or "").strip()
    if not s:
        return []
    if len(s) <= max_chars:
        return [s]

    out: List[str] = []
    start = 0
    while start < len(s):
        end = min(len(s), start + max_chars)
        chunk = s[start:end].strip()
        if chunk:
            out.append(chunk)
        if end >= len(s):
            break
        start = max(0, end - max(0, overlap))
    return out

# ---------------- Core helpers ----------------

def _itertext(el: Optional[ET.Element]) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _ncbi_params_base() -> Dict[str, str]:
    params = {"tool": NCBI_TOOL, "email": (NCBI_EMAIL or "").strip()}
    k = (NCBI_API_KEY or "").strip()
    if k:
        params["api_key"] = k
    return params


@st.cache_resource
def _requests_session() -> requests.Session:
    s = requests.Session()
    email = (NCBI_EMAIL or "").strip()
    ua = "streamlit-pmid-abstract/1.0"
    if email:
        ua += f" ({email})"
    s.headers.update({"User-Agent": ua})
    return s

# ---------------- NCBI fetch + parse ----------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pubmed_xml(pmid: str) -> str:
    sess = _requests_session()
    params = {"db": "pubmed", "id": pmid, "retmode": "xml", **_ncbi_params_base()}
    r = sess.get(NCBI_EFETCH_URL, params=params, timeout=25)
    r.raise_for_status()
    return r.text


def parse_abstract(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    abstract_elems = root.findall(".//Abstract/AbstractText")
    parts: List[str] = []
    for el in abstract_elems:
        label = el.attrib.get("Label") or el.attrib.get("NlmCategory") or ""
        txt = _itertext(el)
        if not txt:
            continue
        parts.append(f"{label}: {txt}" if label else txt)
    return "\n\n".join(parts).strip()


def parse_year(xml_text: str) -> str:
    root = ET.fromstring(xml_text)

    year = _itertext(root.find(".//JournalIssue/PubDate/Year"))
    if year:
        return year

    year = _itertext(root.find(".//ArticleDate/Year"))
    if year:
        return year

    medline = _itertext(root.find(".//JournalIssue/PubDate/MedlineDate"))
    if medline:
        m = re.search(r"(\d{4})", medline)
        if m:
            return m.group(1)

    for path in [".//DateCreated/Year", ".//DateCompleted/Year"]:
        year = _itertext(root.find(path))
        if year:
            return year

    return ""


def _parse_pubmed_month_token(raw: str) -> str:
    token = (raw or "").strip().lower().replace(".", "")
    if not token:
        return ""

    if re.fullmatch(r"\d{1,2}", token):
        n = int(token)
        if 1 <= n <= 12:
            return f"{n:02d}"
        return ""

    first = re.split(r"[\s\-/]+", token)[0]
    if not first:
        return ""
    if first in _PUBMED_MONTH_NAME_TO_NUM:
        return _PUBMED_MONTH_NAME_TO_NUM[first]
    return _PUBMED_MONTH_NAME_TO_NUM.get(first[:3], "")


def _parse_pubmed_month_from_medline_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    m = re.search(
        r"(?i)\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\b",
        s,
    )
    if not m:
        return ""
    return _parse_pubmed_month_token(m.group(1))


def parse_pub_month(xml_text: str) -> str:
    root = ET.fromstring(xml_text)

    for path in [
        ".//JournalIssue/PubDate/Month",
        ".//ArticleDate/Month",
        ".//DateCreated/Month",
        ".//DateCompleted/Month",
    ]:
        month = _parse_pubmed_month_token(_itertext(root.find(path)))
        if month:
            return month

    medline = _itertext(root.find(".//JournalIssue/PubDate/MedlineDate"))
    if medline:
        month = _parse_pubmed_month_from_medline_date(medline)
        if month:
            return month

    return ""


def parse_journal(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    journal = _itertext(root.find(".//Journal/Title"))
    if journal:
        return journal
    return _itertext(root.find(".//Journal/ISOAbbreviation"))


def parse_title(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    return _itertext(root.find(".//ArticleTitle"))


# ---------------- Neighbors (ELink) ----------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_neighbors_elink_xml(pmid: str, retmax: int = 50) -> str:
    sess = _requests_session()
    params = {
        "dbfrom": "pubmed",
        "db": "pubmed",
        "id": pmid,
        "cmd": "neighbor_score",
        "linkname": "pubmed_pubmed",
        "retmode": "xml",
        "retmax": str(int(retmax)),
        **_ncbi_params_base(),
    }
    r = sess.get(NCBI_ELINK_URL, params=params, timeout=25)
    r.raise_for_status()
    return r.text


def parse_neighbor_pmids(elink_xml: str, exclude_pmid: str = "") -> List[str]:
    root = ET.fromstring(elink_xml)

    def _parse_score_any(s: str) -> Optional[float]:
        m = re.search(r"[-+]?\d*\.?\d+", (s or "").strip())
        if not m:
            return None
        try:
            return float(m.group(0))
        except Exception:
            return None

    best: List[Tuple[str, Optional[float]]] = []
    best_rank: Tuple[int, int, int] = (-1, -1, -1)

    for lsdb in root.findall(".//LinkSetDb"):
        linkname = (_itertext(lsdb.find("LinkName")) or "").strip().lower()
        links = lsdb.findall("Link")
        if not links:
            continue

        extracted: List[Tuple[str, Optional[float]]] = []
        has_scores = 0

        for link in links:
            pid = _itertext(link.find("Id")).strip()
            if not pid:
                continue

            score: Optional[float] = None
            for child in list(link):
                if (child.tag or "").strip().lower() in ("score", "linkscore"):
                    score = _parse_score_any(_itertext(child))
                    break

            if score is not None:
                has_scores = 1

            extracted.append((pid, score))

        if not extracted:
            continue

        pref_pubmed = 1 if "pubmed_pubmed" in linkname else 0
        rank = (pref_pubmed, has_scores, len(extracted))
        if rank > best_rank:
            best_rank = rank
            best = extracted

    if not best:
        return []

    if any(s is not None for _, s in best):
        best.sort(key=lambda t: (t[1] is None, -(t[1] or 0.0), t[0]))

    out: List[str] = []
    seen = set()
    ex = (exclude_pmid or "").strip()
    for pid, _ in best:
        if ex and pid == ex:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)

    return out


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pubmed_esummary_xml(pmids_csv: str) -> str:
    sess = _requests_session()
    params = {"db": "pubmed", "id": pmids_csv, "retmode": "xml", **_ncbi_params_base()}
    r = sess.get(NCBI_ESUMMARY_URL, params=params, timeout=25)
    r.raise_for_status()
    return r.text


def parse_esummary_titles(esummary_xml: str) -> Dict[str, str]:
    root = ET.fromstring(esummary_xml)
    out: Dict[str, str] = {}
    for docsum in root.findall(".//DocSum"):
        pid = _itertext(docsum.find("Id"))
        if not pid:
            continue
        title = ""
        for item in docsum.findall("Item"):
            if item.attrib.get("Name") == "Title":
                title = _itertext(item)
                break
        out[pid] = (title or "").strip()
    return out


def get_top_neighbors(pmid: str, top_n: int = 5) -> List[Dict[str, str]]:
    elink_xml = fetch_neighbors_elink_xml(pmid, retmax=max(50, int(top_n) * 10))
    pmids = parse_neighbor_pmids(elink_xml, exclude_pmid=pmid)[: int(top_n)]
    if not pmids:
        return []
    esum_xml = fetch_pubmed_esummary_xml(",".join(pmids))
    titles = parse_esummary_titles(esum_xml)
    return [{"pmid": p, "title": titles.get(p, "").strip()} for p in pmids]


@st.cache_data(ttl=1800, show_spinner=False)
def search_pubmed_pmids_page(
    term: str,
    mindate: str,
    maxdate: str,
    retmax: int = 200,
    retstart: int = 0,
) -> Dict[str, object]:
    q = (term or "").strip()
    if not q:
        return {"pmids": [], "total_count": 0}

    md = (mindate or "").strip()
    xd = (maxdate or "").strip()
    if not md or not xd:
        return {"pmids": [], "total_count": 0}

    sess = _requests_session()
    params = {
        "db": "pubmed",
        "term": q,
        "retmode": "json",
        "retmax": str(max(1, int(retmax))),
        "retstart": str(max(0, int(retstart))),
        "sort": "pub date",
        "datetype": "pdat",
        "mindate": md,
        "maxdate": xd,
        **_ncbi_params_base(),
    }
    r = sess.get(NCBI_ESEARCH_URL, params=params, timeout=25)
    r.raise_for_status()

    payload = r.json() or {}
    esearch = payload.get("esearchresult") or {}
    idlist = esearch.get("idlist") or []
    total_count_raw = str(esearch.get("count") or "").strip()
    try:
        total_count = int(total_count_raw)
    except Exception:
        total_count = 0

    out: List[str] = []
    seen = set()
    for pid in idlist:
        p = str(pid or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return {"pmids": out, "total_count": int(total_count)}


def _fetch_pubmed_titles_for_pmids(pmids: List[str]) -> Dict[str, str]:
    ids: List[str] = []
    seen = set()
    for raw in (pmids or []):
        p = str(raw or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        ids.append(p)

    if not ids:
        return {}

    out: Dict[str, str] = {}
    chunk_size = 200
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        if not chunk:
            continue
        esum_xml = fetch_pubmed_esummary_xml(",".join(chunk))
        out.update(parse_esummary_titles(esum_xml))
    return out


def search_pubmed_by_date_filters_page(
    start_date: str,
    end_date: str,
    journal_term: str,
    publication_type_terms: List[str],
    retmax: int = 200,
    retstart: int = 0,
) -> Dict[str, object]:
    """
    Return one page of PubMed results in a publication-date range using journal +
    publication-type terms. Date format expected: YYYY/MM/DD.
    """
    journal_q = (journal_term or "").strip()
    pub_type_terms = [(t or "").strip() for t in (publication_type_terms or []) if (t or "").strip()]

    term_bits: List[str] = []
    if journal_q:
        term_bits.append(journal_q)
    if pub_type_terms:
        if len(pub_type_terms) == 1:
            term_bits.append(pub_type_terms[0])
        else:
            term_bits.append("(" + " OR ".join(pub_type_terms) + ")")

    if not term_bits:
        return {"rows": [], "total_count": 0}

    term = " AND ".join(term_bits)
    page = search_pubmed_pmids_page(
        term=term,
        mindate=start_date,
        maxdate=end_date,
        retmax=retmax,
        retstart=retstart,
    )
    pmids = [str(p).strip() for p in (page.get("pmids") or []) if str(p).strip()]
    if not pmids:
        return {"rows": [], "total_count": int(page.get("total_count") or 0)}

    titles = _fetch_pubmed_titles_for_pmids(pmids)
    rows = [{"pmid": p, "title": titles.get(p, "").strip()} for p in pmids]
    return {"rows": rows, "total_count": int(page.get("total_count") or 0)}


# ---------------- OpenAI helpers ----------------

def _openai_api_key() -> str:
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return str(st.secrets["OPENAI_API_KEY"]).strip()
    except Exception:
        pass


def _openai_model() -> str:
    return ("gpt-5.4")


# ---------------- Semantic Scholar helpers ----------------

SEMANTIC_SCHOLAR_RECOMMEND_FORPAPER_URL = "https://api.semanticscholar.org/recommendations/v1/papers/forpaper/"

def _semantic_scholar_api_key() -> str:
    """Return Semantic Scholar API key (supports multiple secrets.toml layouts)."""
    try:
        if "SEMANTIC_SCHOLAR_API_KEY" in st.secrets:
            return str(st.secrets["SEMANTIC_SCHOLAR_API_KEY"]).strip()
    except Exception:
        pass

@st.cache_data(show_spinner=False, ttl=60 * 60)
def get_s2_similar_papers(pmid: str, top_n: int = 5) -> List[Dict[str, str]]:
    """Return top Semantic Scholar recommendations for a PubMed PMID."""
    pmid = (pmid or "").strip()
    if not pmid:
        return []

    api_key = _semantic_scholar_api_key()
    if not api_key:
        raise ValueError(
            "Semantic Scholar API key not found. Add SEMANTIC_SCHOLAR_API_KEY to .streamlit/secrets.toml "
            "or set the SEMANTIC_SCHOLAR_API_KEY environment variable."
        )

    # Recommendations API accepts paper ids including PMID/PMCID/DOI formats.
    # Use explicit 'PMID:' prefix to avoid ambiguity.
    paper_id = f"PMID:{pmid}"
    url = SEMANTIC_SCHOLAR_RECOMMEND_FORPAPER_URL + quote(paper_id, safe="")
    params = {
        "limit": str(int(top_n)),
        "fields": "title,url,year,externalIds",
    }
    headers = {"x-api-key": api_key}

    sess = _requests_session()
    r = sess.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()

    payload = r.json() or {}
    recs = payload.get("recommendedPapers") or []

    out: List[Dict[str, str]] = []
    for p in recs[: int(top_n)]:
        ext = p.get("externalIds") or {}
        out.append(
            {
                "title": (p.get("title") or "").strip(),
                "url": (p.get("url") or "").strip(),
                "paperId": (p.get("paperId") or "").strip(),
                "year": str(p.get("year") or "").strip(),
                "pmid": str(ext.get("PubMed") or "").strip(),
                "doi": str(ext.get("DOI") or "").strip(),
            }
        )
    return out


def _post_with_retries(
    url: str,
    headers: Dict[str, str],
    json: Dict,
    timeout: int = 30,
    max_attempts: int = 5,
) -> requests.Response:
    sess = _requests_session()
    last_exc: Optional[Exception] = None

    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        try:
            r = sess.post(url, headers=headers, json=json, timeout=timeout)

            if r.status_code in (429, 500, 502, 503, 504):
                retry_after = r.headers.get("Retry-After", "").strip()
                ra = int(retry_after) if retry_after.isdigit() else None

                backoff = (2 ** attempt) + random.random()
                sleep_s = ra if ra is not None else min(backoff, 10)
                time.sleep(max(0.5, float(sleep_s)))
                continue

            r.raise_for_status()
            return r

        except Exception as e:
            last_exc = e
            backoff = (2 ** attempt) + random.random()
            time.sleep(min(backoff, 10))

    if last_exc:
        raise last_exc
    raise RuntimeError("POST failed after retries")


def _extract_output_text(resp_json: Dict) -> str:
    if isinstance(resp_json.get("output_text"), str) and resp_json["output_text"].strip():
        return resp_json["output_text"].strip()

    parts: List[str] = []
    for item in (resp_json.get("output") or []):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for c in (item.get("content") or []):
            if isinstance(c, dict) and c.get("type") == "output_text" and isinstance(c.get("text"), str):
                parts.append(c["text"])
    return "\n".join(parts).strip()

# ---------------- Guideline clinician-friendly display (sectioned) ----------------

_GUIDELINE_SECTION_CHOICES = [
    "History / Presentation",
    "Physical exam",
    "Risk stratification",
    "Labs",
    "Imaging",
    "Diagnostic procedures",
    "Consultation",
    "Disposition",
    "Supportive care",
    "Medicines",
    "Therapeutic procedures",
    "Cautions / Contraindications",
    "Monitoring",
    "Post-hospitalization care",
    "Secondary prevention",
    "Special populations",
    "Possible repeats",
]

_GUIDELINE_SECTION_ORDER = {name: i for i, name in enumerate(_GUIDELINE_SECTION_CHOICES, start=1)}


# Build a canonical lookup once
_GUIDELINE_SECTION_CANON = {s.lower(): s for s in _GUIDELINE_SECTION_CHOICES}

def _safe_section_label(s: str) -> str:
    lab = (s or "").strip()
    if not lab:
        return "Other"

    lab = re.sub(r"\s{2,}", " ", lab).strip()
    if len(lab) > 80:
        lab = lab[:80].rstrip() + "…"

    # Canonicalize exact matches ignoring case
    canon = _GUIDELINE_SECTION_CANON.get(lab.lower())
    return canon if canon else lab



def _extract_bracket_path(source_snippet: str) -> str:
    """
    source_snippet often looks like: "[Heading > Path] excerpt..."
    Return just the bracket path if present.
    """
    s = (source_snippet or "").strip()
    m = re.match(r"^\[([^\]]{1,220})\]\s*(.*)$", s)
    if not m:
        return ""
    return (m.group(1) or "").strip()


_GUIDELINE_PSEUDO_ATTR_START_RE = re.compile(
    r"(?i)^\s*(?:we\s+)?(?:recommend|suggest|consider|avoid|do\s+not|don't|should)\b"
)
_GUIDELINE_GRADE_SIGNAL_RE = re.compile(
    r"(?i)\b("
    r"class\s*(?:[ivx]+|\d+[a-z]?)|"
    r"level(?:\s+of\s+evidence)?\s*[a-d](?:-[a-z]+)?|"
    r"loe\s*[a-d](?:-[a-z]+)?|"
    r"grade\s*(?:[a-d]|\d+[a-z]?)|"
    r"(?:strong|weak|conditional)\s+recommendation|"
    r"good\s+practice\s+statement|"
    r"(?:very\s+low|low|moderate|high)\s+(?:certainty|quality)"
    r")\b"
)


def _normalize_guideline_attr_text(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("(") and s.endswith(")") and len(s) >= 3:
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s).strip(" ;,.-")
    return s


def _sanitize_guideline_attr_value(raw: str) -> str:
    s = _normalize_guideline_attr_text(raw)
    if not s:
        return ""
    low = s.lower()
    if _GUIDELINE_PSEUDO_ATTR_START_RE.search(low) and not _GUIDELINE_GRADE_SIGNAL_RE.search(low):
        return ""
    return s


def _attr_value_present_in_reco_text(reco_text: str, attr_value: str) -> bool:
    txt = (reco_text or "").strip().lower()
    val = _normalize_guideline_attr_text(attr_value).lower()
    if not txt or not val:
        return False

    txt_norm = re.sub(r"[^a-z0-9]+", "", txt)
    val_norm = re.sub(r"[^a-z0-9]+", "", val)
    if len(val_norm) >= 4 and val_norm in txt_norm:
        return True

    toks = [t for t in re.findall(r"[a-z0-9]+", val) if len(t) >= 3]
    if len(toks) >= 2 and all(re.search(rf"\b{re.escape(t)}\b", txt) for t in toks):
        return True

    return False


def _chunk_recs_for_classification(items: List[Dict], max_chars: int = 14000, max_items: int = 45) -> List[List[Dict]]:
    """
    Chunk items so each OpenAI call stays bounded.
    We classify using truncated rec text; full text is rendered later (guarantees completeness).
    """
    chunks: List[List[Dict]] = []
    cur: List[Dict] = []
    cur_chars = 0

    for it in items:
        text = (it.get("text") or "")
        blob = f"{it.get('i')}. {text}"
        # start new chunk if needed
        if cur and (len(cur) >= max_items or (cur_chars + len(blob) > max_chars)):
            chunks.append(cur)
            cur = []
            cur_chars = 0
        cur.append(it)
        cur_chars += len(blob)

    if cur:
        chunks.append(cur)
    return chunks


def _parse_json_from_model(raw: str) -> Dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}


def _truncate_for_prompt(text: str, max_chars: int) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    lim = max(1, int(max_chars))
    if len(s) <= lim:
        return s
    return s[:lim].rstrip() + "…"


def _cap_prior_repeat_context(
    items: List[Dict],
    max_chars: int = 26000,
    max_items: int = 170,
    head_keep: int = 45,
) -> List[Dict]:
    """
    Keep a bounded prior context for repeat checks.
    Mixes early "anchor" items with recent items to preserve global order context.
    """
    if not items:
        return []

    selected: List[Dict] = []
    seen_i = set()
    total_chars = 0

    def _try_add(it: Dict) -> bool:
        nonlocal total_chars
        try:
            ii = int(it.get("i"))
        except Exception:
            return False
        if ii in seen_i:
            return False

        txt = (it.get("text") or "").strip()
        if not txt:
            return False
        cost = len(txt) + 24
        if selected and (len(selected) >= max_items or (total_chars + cost > max_chars)):
            return False

        selected.append({"i": ii, "text": txt})
        seen_i.add(ii)
        total_chars += cost
        return True

    head_n = min(max(0, int(head_keep)), len(items))
    for it in items[:head_n]:
        _try_add(it)
        if len(selected) >= max_items:
            break

    if len(selected) < max_items:
        for it in reversed(items[head_n:]):
            _try_add(it)
            if len(selected) >= max_items:
                break

    selected.sort(key=lambda x: int(x.get("i") or 0))
    return selected


def _openai_global_repeat_post_pass(
    recs: List[Dict[str, str]],
    i_to_section: Dict[int, str],
    progress_cb=None,
) -> Dict[int, int]:
    """
    Global post-pass for repeats:
    - works in original recommendation order (lower i appears earlier in source)
    - only marks *later* recommendations as repeats
    - skips items already in "Possible repeats"
    Returns mapping: later_recommendation_i -> earlier_recommendation_i
    """
    key = _openai_api_key()
    if not key:
        return {}

    check_items: List[Dict] = []
    ii = 0
    for r in recs or []:
        txt = (r.get("recommendation_text") or "").strip()
        if not txt:
            continue
        ii += 1
        section_now = _safe_section_label(i_to_section.get(ii, "Other"))
        if section_now == "Possible repeats":
            continue
        check_items.append({"i": ii, "text": _truncate_for_prompt(txt, 1200)})

    if len(check_items) < 2:
        return {}

    def _progress(done=0, total=0, msg="", detail=""):
        if not progress_cb:
            return
        try:
            progress_cb(done, total, msg=msg, detail=detail)
        except TypeError:
            try:
                progress_cb(done, total, msg or detail or "")
            except TypeError:
                progress_cb(done, total)

    instructions = (
        "You are running a global post-pass to detect later duplicate/near-duplicate guideline recommendations.\n"
        "Return ONLY valid JSON with this exact shape:\n"
        "{\"items\":[{\"i\":12,\"duplicate_of\":3}]}\n\n"
        "Input JSON contains:\n"
        "- prior_items: recommendations that appeared earlier and are already kept as non-repeats.\n"
        "- batch_items: the next recommendations in original order.\n\n"
        "Rules:\n"
        "- Mark ONLY batch_items that are later duplicates/near-duplicates of earlier recommendations.\n"
        "- 'Earlier' means: any prior_item, or a lower-numbered item in the same batch.\n"
        "- Never mark the first occurrence of an idea.\n"
        "- i and duplicate_of must both be recommendation indices from input; duplicate_of must be < i.\n"
        "- If uncertain, do not mark.\n"
        "- No extra keys. No markdown. No commentary."
    )

    batches = _chunk_recs_for_classification(check_items, max_chars=10000, max_items=28)
    total_batches = len(batches)
    repeat_map: Dict[int, int] = {}
    canonical_prior: List[Dict] = []

    _progress(
        0,
        max(1, total_batches),
        msg="Step 4/4 — Global repeat post-pass…",
        detail=f"Checking {len(check_items)} recommendation(s) across {total_batches} batch(es)",
    )

    for bi, batch in enumerate(batches, start=1):
        _progress(
            bi - 1,
            max(1, total_batches),
            msg="Step 4/4 — Global repeat post-pass…",
            detail=f"Repeat check batch {bi}/{total_batches}",
        )

        prior_payload_raw = [
            {"i": int(p.get("i") or 0), "text": _truncate_for_prompt((p.get("text") or ""), 420)}
            for p in canonical_prior
            if int(p.get("i") or 0) > 0
        ]
        prior_payload = _cap_prior_repeat_context(
            prior_payload_raw,
            max_chars=26000,
            max_items=170,
            head_keep=45,
        )
        batch_payload = [
            {"i": int(b.get("i") or 0), "text": _truncate_for_prompt((b.get("text") or ""), 1000)}
            for b in batch
            if int(b.get("i") or 0) > 0
        ]

        if not batch_payload:
            continue

        payload = {
            "model": _openai_model(),
            "instructions": instructions,
            "input": "INPUT_JSON:\n"
            + json.dumps(
                {
                    "prior_items": prior_payload,
                    "batch_items": batch_payload,
                },
                ensure_ascii=False,
            )
            + "\n\nReturn JSON now.",
            "text": {"verbosity": "low"},
            "max_output_tokens": 900,
            "temperature": 0,
            "reasoning": {"effort": "none"},
            "store": False,
        }

        obj: Dict = {}
        try:
            r = _post_with_retries(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=75,
            )
            r.raise_for_status()
            obj = _parse_json_from_model(_extract_output_text(r.json()))
        except Exception:
            obj = {}

        out_items = obj.get("items") if isinstance(obj, dict) else None
        if not isinstance(out_items, list):
            out_items = []

        prior_i_set = set()
        for p in prior_payload:
            try:
                prior_i_set.add(int(p.get("i")))
            except Exception:
                continue

        batch_i_set = set()
        for b in batch_payload:
            try:
                batch_i_set.add(int(b.get("i")))
            except Exception:
                continue

        valid_context_ids = prior_i_set | batch_i_set
        proposed: Dict[int, int] = {}

        for oi in out_items:
            if not isinstance(oi, dict):
                continue
            try:
                i_val = int(oi.get("i"))
                dup_of = int(oi.get("duplicate_of"))
            except Exception:
                continue
            if i_val not in batch_i_set:
                continue
            if dup_of not in valid_context_ids:
                continue
            if dup_of >= i_val:
                continue
            prev = proposed.get(i_val)
            if prev is None or dup_of < prev:
                proposed[i_val] = dup_of

        for b in batch_payload:
            i_val = int(b.get("i") or 0)
            if i_val <= 0:
                continue
            if i_val in proposed:
                repeat_map[i_val] = int(proposed.get(i_val) or 0)
                continue
            canonical_prior.append({"i": i_val, "text": (b.get("text") or "")})

        _progress(
            bi,
            max(1, total_batches),
            msg="Step 4/4 — Global repeat post-pass…",
            detail=f"Finished repeat batch {bi}/{total_batches} • {len(repeat_map)} marked",
        )

    return repeat_map


def gpt_generate_guideline_recommendations_display(
    recs: List[Dict[str, str]],
    meta: Optional[Dict[str, str]] = None,
    progress_cb=None,
) -> str:
    """
    Produces markdown with clinician-friendly sections.
    OpenAI is used to classify recommendations and then run a global repeat post-pass.
    Inferior duplicates are dropped; an exception keeps an ungraded-but-more-complete
    copy as a "Possible repeat" when the best copy is graded.
    """
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    meta = meta or {}
    gname = (meta.get("guideline_name") or meta.get("filename") or "Guideline").strip()

    # Build items in stable display order
    items: List[Dict] = []
    for i, r in enumerate(recs or [], start=1):
        txt = (r.get("recommendation_text") or "").strip()
        if not txt:
            continue
        # truncate only for classification
        txt_short = txt[:1600] + ("…" if len(txt) > 1600 else "")
        items.append(
            {
                "i": i,
                "text": txt_short,
            }
        )

    if not items:
        return f"# {gname}\n\n_No recommendations found._"

    # Classify in chunks
    i_to_section: Dict[int, str] = {}

    instructions = (
        "You are categorizing clinical guideline recommendations into clinician-friendly sections.\n"
        "Return ONLY valid JSON with this shape:\n"
        "{\"items\":[{\"i\":1,\"section\":\"Labs\"}, ...]}\n\n"
        "Rules:\n"
        "- Each input item must appear exactly once in output.\n"
        "- section must be ONE short label. Prefer from this list and in this order:\n"
        f"{', '.join(s for s in _GUIDELINE_SECTION_CHOICES if s != 'Possible repeats')}\n"
        "- If none fit, place in 'Other'.\n"
        "- A note about the 'Disposition' section: This refers to just after initial evaluaion. I.e., whether the patient should be discharged from the emergency department, admitted to the a hospital floor, or admitted to the intensive care unit (or sometimes other options as well).\n"
        "- A note about the 'Cautions / Contraindications' section: Use this ONLY for actual safety warnings — specific clinical scenarios where a therapy is contraindicated, should be avoided, or requires dose modification. Do NOT use it for qualifying context, methodological caveats, or clarifying statements about other recommendations. Those belong in the clinical section they relate to (e.g., a caveat about antibiotic duration belongs in Medicines).\n"
        "- Do NOT include any extra keys. No markdown. No commentary."
    )

    def _progress(done=0, total=0, msg="", detail=""):
        if not progress_cb:
            return
        try:
            progress_cb(done, total, msg=msg, detail=detail)
        except TypeError:
            try:
                progress_cb(done, total, msg or detail or "")
            except TypeError:
                progress_cb(done, total)

    chunks = _chunk_recs_for_classification(items, max_chars=14000, max_items=45)
    total_chunks = len(chunks)

    _progress(
        0,
        max(1, total_chunks),
        msg="Step 4/4 — Categorizing recommendations into clinician-friendly sections…",
        detail=f"{len(items)} recommendation(s) in {total_chunks} batch(es)",
    )

    for ci, ch in enumerate(chunks, start=1):
        _progress(
            ci - 1,
            max(1, total_chunks),
            msg="Step 4/4 — Categorizing recommendations into clinician-friendly sections…",
            detail=f"Running batch {ci}/{total_chunks}",
        )

        payload = {
            "model": _openai_model(),
            "instructions": instructions,
            "input": "INPUT_JSON:\n" + json.dumps({"items": ch}, ensure_ascii=False) + "\n\nReturn JSON now.",
            "text": {"verbosity": "low"},
            "max_output_tokens": 1200,
            "temperature": 0,
            "reasoning": {"effort": "none"},
            "store": False,
        }
        r = _post_with_retries(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        obj = _parse_json_from_model(_extract_output_text(r.json()))
        out_items = obj.get("items") if isinstance(obj, dict) else None
        if not isinstance(out_items, list):
            out_items = []

        for oi in out_items:
            if not isinstance(oi, dict):
                continue
            try:
                ii = int(oi.get("i"))
            except Exception:
                continue
            sec = _safe_section_label(oi.get("section") or "")
            i_to_section[ii] = sec

        _progress(
            ci,
            max(1, total_chunks),
            msg="Step 4/4 — Categorizing recommendations into clinician-friendly sections…",
            detail=f"Finished batch {ci}/{total_chunks}",
        )

    rec_has_grade_signal: Dict[int, bool] = {}
    ii_grade = 0
    for r in recs or []:
        txt = (r.get("recommendation_text") or "").strip()
        if not txt:
            continue
        ii_grade += 1
        strength = _sanitize_guideline_attr_value(r.get("strength_raw") or "")
        evidence = _sanitize_guideline_attr_value(r.get("evidence_raw") or "")
        rec_has_grade_signal[ii_grade] = bool(strength or evidence)

    repeat_overrides: Dict[int, int] = {}
    try:
        repeat_overrides = _openai_global_repeat_post_pass(recs, i_to_section, progress_cb=_progress)
    except Exception:
        repeat_overrides = {}

    drop_set: Set[int] = set()

    if repeat_overrides:
        pre_repeat_sections = {
            int(i): _safe_section_label(sec)
            for i, sec in i_to_section.items()
        }

        # Build text length map for completeness comparison
        rec_text_len: Dict[int, int] = {}
        ii_len = 0
        for r in recs or []:
            txt_r = (r.get("recommendation_text") or "").strip()
            if not txt_r:
                continue
            ii_len += 1
            rec_text_len[ii_len] = len(txt_r)

        # Resolve chains: if A→B and B→C, resolve both to C's ultimate canonical
        resolved: Dict[int, int] = {}
        for later_i in repeat_overrides:
            canon = int(repeat_overrides[later_i])
            seen = {int(later_i)}
            while canon in repeat_overrides and canon not in seen:
                seen.add(canon)
                canon = int(repeat_overrides[canon])
            resolved[int(later_i)] = canon

        # Group all duplicates by their ultimate canonical item
        canon_groups: Dict[int, List[int]] = {}
        for later_i, canon_i in resolved.items():
            canon_groups.setdefault(canon_i, []).append(later_i)

        keep_later_real: Dict[int, int] = {}

        for canon_i, later_list in canon_groups.items():
            all_items = [canon_i] + sorted(later_list)

            # Pick the best: prefer graded (has strength/evidence), then longest text
            def _dup_score(idx: int) -> tuple:
                g = 1 if rec_has_grade_signal.get(idx, False) else 0
                return (g, rec_text_len.get(idx, 0))

            best_i = max(all_items, key=_dup_score)
            best_has_grade = bool(rec_has_grade_signal.get(best_i, False))
            best_len = rec_text_len.get(best_i, 0)

            for item_i in all_items:
                if item_i == best_i:
                    # If the best is a later item, it needs the canonical's section
                    if item_i != canon_i:
                        keep_later_real[item_i] = canon_i
                    continue

                item_has_grade = bool(rec_has_grade_signal.get(item_i, False))
                item_len = rec_text_len.get(item_i, 0)
                item_is_more_complete = (item_len > best_len + 30
                                         and item_len > best_len * 1.2)

                # Exception: best has grade, item is ungraded but meaningfully
                # more complete — keep the item as a possible repeat so the
                # clinician can review it.
                if best_has_grade and not item_has_grade and item_is_more_complete:
                    i_to_section[item_i] = "Possible repeats"
                else:
                    drop_set.add(item_i)

        # Ensure kept later items get a proper clinical section
        for later_i, canon_i in keep_later_real.items():
            if later_i in drop_set:
                continue
            sec_now = _safe_section_label(i_to_section.get(later_i, "Other"))
            if sec_now != "Possible repeats":
                continue
            fallback = _safe_section_label(pre_repeat_sections.get(canon_i, "Other"))
            if fallback == "Possible repeats":
                fallback = "Other"
            i_to_section[later_i] = fallback

    _progress(
        max(1, total_chunks),
        max(1, total_chunks),
        msg="Step 4/4 — Rendering clinician-friendly display…",
        detail="Formatting final Markdown output",
    )

    # Render recommendations (full text + strength/evidence/source), skipping dropped repeats
    enriched: List[Dict] = []
    ii = 0
    for r in recs or []:
        txt = (r.get("recommendation_text") or "").strip()
        if not txt:
            continue
        ii += 1
        if ii in drop_set:
            continue
        strength = _sanitize_guideline_attr_value(r.get("strength_raw") or "")
        evidence = _sanitize_guideline_attr_value(r.get("evidence_raw") or "")
        enriched.append(
            {
                "i": ii,
                "section": _safe_section_label(i_to_section.get(ii, "Other")),
                "text": txt,
                "strength": strength,
                "evidence": evidence,
                "path": _extract_bracket_path(r.get("source_snippet") or ""),
            }
        )

    # Group by section
    grouped: Dict[str, List[Dict]] = {}
    for e in enriched:
        grouped.setdefault(e["section"], []).append(e)

    def _sec_sort_key(s: str) -> Tuple[int, str]:
        return (_GUIDELINE_SECTION_ORDER.get(s, 10_000), s.lower())

    sections_sorted = sorted(grouped.keys(), key=_sec_sort_key)

    md_lines: List[str] = [""]

    display_num = 0
    for sec in sections_sorted:
        md_lines.append(f"### {sec}")
        md_lines.append("")
        for e in grouped.get(sec, []):
            display_num += 1
            rec_txt = e["text"]
            # Clean PDF artifacts from recommendation text
            rec_txt = re.sub(r"(\w)- (\w)", r"\1\2", rec_txt)  # line-break hyphens
            rec_txt = re.sub(r"(?<=[a-zA-Z])\.(\d+(?:[,\-–]\s*\d+)*)", ".", rec_txt)  # inline citations
            rec_txt = re.sub(r"\s*\(\d+(?:[,\s\-–]+\d+)*\)", "", rec_txt)  # parenthetical citations
            rec_txt = re.sub(r"(?<=[a-zA-Z])[*†‡§]+(?=[\s,;.\)]|$)", "", rec_txt)  # footnote markers
            # Strip leading transitional words that read awkwardly as standalone bullets
            rec_txt = re.sub(
                r"^(Thus|However|Therefore|Accordingly|Furthermore|Moreover|Hence|Consequently|In addition|Additionally),?\s*",
                "", rec_txt, flags=re.IGNORECASE,
            )
            if rec_txt:
                rec_txt = rec_txt[0].upper() + rec_txt[1:]
            rec_txt = rec_txt.strip()
            extras: List[str] = []
            if e["strength"] and not _attr_value_present_in_reco_text(rec_txt, e["strength"]):
                extras.append(f"Strength: {e['strength']}")
            if e["evidence"] and not _attr_value_present_in_reco_text(rec_txt, e["evidence"]):
                extras.append(f"Evidence: {e['evidence']}")
            extra_txt = f" ({'; '.join(extras)})" if extras else ""
            md_lines.append(f"**{display_num}.** {rec_txt}{extra_txt}<br>")
        md_lines.append("")

    return "\n".join(md_lines).strip()


def _parse_nonneg_int(raw: str) -> Optional[int]:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    try:
        n = int(m.group(1))
        return n if n >= 0 else None
    except Exception:
        return None


def _parse_tag_list(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"(?i)\s*(none|n/a|na|null|0|unknown)\s*", s):
        return ""

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
    return ", ".join(out).strip()


def _normalize_bullets(raw: str) -> str:
    out_text = (raw or "").strip()
    if not out_text:
        return ""
    lines = [ln.strip() for ln in out_text.splitlines() if ln.strip()]
    bullets: List[str] = []
    for ln in lines:
        if ln.startswith("- "):
            bullets.append(ln)
        else:
            bullets.append("- " + ln.lstrip("-• ").strip())

    seen = set()
    final: List[str] = []
    for b in bullets:
        key = b.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        final.append(b)
    return "\n".join(final).strip()


# ---------------- OpenAI extractors ----------------

@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_specialty(
    title: str,
    abstract: str,
    timeout_s: int = 30,
    max_attempts: int = 5,
) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return ""

    instructions = (
        "You extract medical specialty labels from a PubMed title+abstract.\n"
        "Return a comma-separated list of specialty names (or an empty string if unclear).\n"
        "Rules:\n"
        "- Output MUST be ONLY the comma-separated specialties on one line (no extra text).\n"
        "- You must restrict your choice to the following specialties: Cardiology, Endocrinology, Gastroenterology, Hematology, Infectious Disease, Nephrology, Neurology, Oncology, Pulmonology, Rheumatology, Critical Care, Emergency Medicine, Surgery, Obstetrics and Gynecology, Psychiatry, Dermatology, Ophthalmology, Otolaryngology, Urology, Orthopedics.\n"
        "- You may return multiple specialties if truly relevant.\n"
        "- Do not invent specialties; use only what is explicitly stated or strongly implied.\n"
        "- Keep it concise (max 2)."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": f"TITLE:\n{title}\n\nABSTRACT:\n{abstract}\n\nReturn the specialty list.",
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 48,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=max(5, int(timeout_s)),
        max_attempts=max(1, int(max_attempts)),
    )
    r.raise_for_status()

    return _parse_tag_list(_extract_output_text(r.json()))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_study_design(title: str, abstract: str) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return ""

    instructions = (
        "You extract study design descriptors from a PubMed abstract.\n"
        "Return a comma-separated list of short tags (no extra text).\n"
        "Only include tags that are explicitly stated or very strongly implied by the abstract.\n"
        "If unclear, return an empty string.\n"
        "\n"
        "Include BOTH:\n"
        "1) study design tags (trial/observational/review etc)\n"
        "2) setting/geography tags when stated (country/region, community hospital vs academic center, ICU/ED/inpatient/outpatient, multicenter, multinational)\n"
        "\n"
        "Output rules:\n"
        "- Output MUST be ONLY the comma-separated tags, on one line.\n"
        "- Do NOT explain.\n"
        "- Do NOT invent tags not supported by the abstract."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": f"TITLE:\n{title}\n\nABSTRACT:\n{abstract}\n\nReturn the study design + setting/geography tags.",
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 72,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    return _parse_tag_list(_extract_output_text(r.json()))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_patient_details(title: str, abstract: str, patient_n: int, study_design: str) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return ""

    instructions = (
        "You extract patient population details from a PubMed abstract.\n"
        "Return ONLY bullet lines, each starting with '- ' (or return an empty string).\n"
        "Hard rules:\n"
        "- Use ONLY information explicitly stated in the abstract. Do not invent or infer beyond what's stated.\n"
        "- Do NOT include any headers, labels, or subheadings.\n"
        "- Do NOT repeat the total patient count or any study design descriptors/tags.\n"
        "- Prioritize eligibility criteria and baseline characteristics.\n"
        "- Keep it concise and high-yield. Prefer 3–10 bullets when possible.\n"
        "- If the abstract does not state meaningful eligibility/baseline details, return an empty string."
    )

    user_input = (
        f"TITLE:\n{title}\n\n"
        f"ALREADY EXTRACTED (do not repeat):\n"
        f"- Patient count: {int(patient_n) if patient_n is not None else 0}\n"
        f"- Study design tags: {study_design or ''}\n\n"
        f"ABSTRACT:\n{abstract}\n\nReturn the bullet list."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": user_input,
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 350,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    return _normalize_bullets(_extract_output_text(r.json()))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_intervention_comparison(
    title: str,
    abstract: str,
    patient_n: int,
    study_design: str,
    patient_details: str,
) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return ""

    instructions = (
        "You extract the intervention and the comparison from a PubMed abstract.\n"
        "Return ONLY bullet lines, each starting with '- ' (or return an empty string).\n"
        "Hard rules:\n"
        "- Use ONLY information explicitly stated in the abstract. Do not invent or infer beyond what's stated.\n"
        "- Do NOT include any headers, labels, or subheadings.\n"
        "- Do NOT repeat patient count, study design tags, or patient population details.\n"
        "- Capture: intervention/exposure, comparator/control/reference, dosing/intensity, timing, duration, co-interventions if stated.\n"
        "- If no clear intervention/comparator is described, return an empty string.\n"
        "- Keep it concise (prefer 2–8 bullets)."
    )

    user_input = (
        f"TITLE:\n{title}\n\n"
        f"ALREADY EXTRACTED (do not repeat):\n"
        f"- Patient count: {int(patient_n) if patient_n is not None else 0}\n"
        f"- Study design tags: {study_design or ''}\n"
        f"- Patient details:\n{patient_details or ''}\n\n"
        f"ABSTRACT:\n{abstract}\n\nReturn the bullet list."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": user_input,
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 320,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    return _normalize_bullets(_extract_output_text(r.json()))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_authors_conclusions(
    title: str,
    abstract: str,
    patient_n: int,
    study_design: str,
    patient_details: str,
    intervention_comparison: str,
) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return ""

    instructions = (
        "Extract the authors' conclusion statement from a PubMed abstract.\n"
        "Output MUST be plain text only (no bullets, no labels, no quotes), ideally 1–2 sentences.\n"
        "Be as close to verbatim as possible from the abstract text (prefer the Conclusions sentence if present).\n"
        "Preserve any numeric values exactly as written when they are part of the conclusion statement.\n"
        "Do NOT repeat patient count, study design tags, patient details, or intervention/comparison specifics.\n"
        "If no clear conclusion statement exists, return an empty string."
    )

    user_input = (
        f"TITLE:\n{title}\n\n"
        f"ALREADY EXTRACTED (do not repeat):\n"
        f"- Patient count: {int(patient_n) if patient_n is not None else 0}\n"
        f"- Study design tags: {study_design or ''}\n"
        f"- Patient details:\n{patient_details or ''}\n"
        f"- Intervention/comparison:\n{intervention_comparison or ''}\n\n"
        f"ABSTRACT:\n{abstract}\n\nReturn the authors' conclusion statement."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": user_input,
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 160,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    return (_extract_output_text(r.json()) or "").strip()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_results(
    title: str,
    abstract: str,
    patient_n: int,
    study_design: str,
    patient_details: str,
    intervention_comparison: str,
) -> str:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return ""

    instructions = (
        "Extract the RESULTS from a PubMed abstract.\n"
        "Return ONLY bullet lines, each starting with '- '. No headers, no labels.\n"
        "Make ONE bullet per distinct reported result.\n"
        "Rules:\n"
        "- Use ONLY information explicitly stated in the abstract. Do not invent.\n"
        "- Avoid repeating patient count, study design tags, patient details, and intervention/comparison descriptions.\n"
        "- If a confidence interval (CI) is provided for a result, do NOT include a p-value for that same result.\n"
        "- Prefer including: outcome name, time horizon (if stated), effect estimate (RR/OR/HR/MD/etc), and CI when stated.\n"
        "- If results are not clearly stated, return an empty string.\n"
        "- Keep it concise; prefer 2–12 bullets."
    )

    user_input = (
        f"TITLE:\n{title}\n\n"
        f"ALREADY EXTRACTED (do not repeat):\n"
        f"- Patient count: {int(patient_n) if patient_n is not None else 0}\n"
        f"- Study design tags: {study_design or ''}\n"
        f"- Patient details:\n{patient_details or ''}\n"
        f"- Intervention/comparison:\n{intervention_comparison or ''}\n\n"
        f"ABSTRACT:\n{abstract}\n\nReturn the results bullet list."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": user_input,
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 520,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    return _normalize_bullets(_extract_output_text(r.json()))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_patient_n(title: str, abstract: str) -> int:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    title = (title or "").strip()
    abstract = (abstract or "").strip()
    if not abstract:
        return 0

    instructions = (
        "You extract the total integer number of human patients/participants studied from a PubMed abstract.\n"
        "Rules:\n"
        "- Output MUST be a single integer on one line, with no other text.\n"
        "- If multiple groups are reported (e.g., randomized arms), output the total enrolled/analyzed participants across all groups.\n"
        "- If multiple cohorts or phases are described, sum the unique participant counts when clearly stated; otherwise use the best single total.\n"
        "- If the abstract is not a human patient/participant study, or the total is not stated/derivable, output 0.\n"
        "- Do not output words, units, punctuation, or explanations."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": f"TITLE:\n{title}\n\nABSTRACT:\n{abstract}\n\nReturn the total number of patients studied.",
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 16,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()

    n = _parse_nonneg_int(_extract_output_text(r.json()))
    return int(n) if n is not None else 0


# ---------------- Azure Document Intelligence (Layout -> Markdown) ----------------

def _azure_di_endpoint() -> str:
    try:
        if "AZURE_DI_ENDPOINT" in st.secrets:
            return str(st.secrets["AZURE_DI_ENDPOINT"]).strip()
    except Exception:
        pass


def _azure_di_key() -> str:
    try:
        if "AZURE_DI_KEY" in st.secrets:
            return str(st.secrets["AZURE_DI_KEY"]).strip()
    except Exception:
        pass

def _require_azure_di() -> None:
    if DocumentIntelligenceClient is None or AzureKeyCredential is None:
        raise RuntimeError("azure-ai-documentintelligence is not installed. Run: pip install azure-ai-documentintelligence")
    ep = _azure_di_endpoint()
    key = _azure_di_key()
    if not ep or not key:
        raise RuntimeError("Missing AZURE_DI_ENDPOINT / AZURE_DI_KEY in secrets.toml (or env vars).")


def _azure_di_client() -> "DocumentIntelligenceClientType":
    _require_azure_di()
    return DocumentIntelligenceClient(endpoint=_azure_di_endpoint(), credential=AzureKeyCredential(_azure_di_key()))


def analyze_pdf_to_markdown_azure(pdf_bytes: bytes, pages: str = "", timeout_s: Optional[float] = None) -> str:
    client = _azure_di_client()
    body = io.BytesIO(pdf_bytes)
    kwargs = {}
    if (pages or "").strip():
        kwargs["pages"] = (pages or "").strip()

    try:
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=body,
            output_content_format=DocumentContentFormat.MARKDOWN,
            **kwargs,
        )
    except Exception:
        body.seek(0)
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=body,
            output_content_format="markdown",
            **kwargs,
        )

    if timeout_s is not None and float(timeout_s) > 0:
        result = poller.result(timeout=float(timeout_s))
    else:
        result = poller.result()
    return (getattr(result, "content", "") or "").strip()


def markdown_from_pdf_bytes(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""
    return (analyze_pdf_to_markdown_azure(pdf_bytes) or "").strip()

# ---------------- Guideline extraction: OpenAI recos from elements ----------------

def _openai_triage_sections(sections: List[Dict[str, str]]) -> List[int]:
    """
    First pass: decide which sections likely contain formal recommendations.
    Returns a list of sec_idx (ints) to pursue.
    """
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    items = []
    for s in sections:
        try:
            sec_idx = int(s.get("sec_idx") or 0)
        except Exception:
            continue
        path = (s.get("path") or "").strip()
        content = (s.get("content") or "").strip()
        if not content:
            continue
        items.append(
            {
                "sec_idx": sec_idx,
                "path": path[:220],
                "preview": _section_preview(content)[:5000],
            }
        )

    if not items:
        return []

    strictness = (GUIDELINE_OPENAI_STRICTNESS or "medium").strip().lower()

    instructions = f"""You are triaging sections of a clinical guideline to find where *formal clinical recommendations* likely appear.
Input is JSON with items: sec_idx, path (heading path), preview (head/tail + hint lines).

Return ONLY valid JSON with this exact shape:
{{ "keep": [<sec_idx integers>], "maybe": [<sec_idx integers>] }}

Guidance:
- "keep": sections very likely to contain formal recommendations/statements/practice points/graded directives.
- "maybe": sections that might contain recommendations but you are less confident.
- Prefer precision but don't miss obvious recommendation sections (e.g., 'Recommendations', 'Practice points', 'Summary of recommendations', 'Algorithm', 'Key statements').

Do NOT include methods/background/evidence review unless there is clear directive language intended as guidance.

Strictness mode is '{strictness}'. In 'strict', be more conservative.
"""

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": "SECTIONS_JSON:\n" + json.dumps({"items": items}, ensure_ascii=False) + "\n\nReturn JSON now.",
        "text": {"verbosity": "low"},
        "max_output_tokens": 900,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()

    raw = (_extract_output_text(r.json()) or "").strip()
    if not raw:
        return []

    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
        if not m:
            return []
        try:
            obj = json.loads(m.group(1))
        except Exception:
            return []

    keep = obj.get("keep") or []
    maybe = obj.get("maybe") or []

    out: List[int] = []
    for arr in (keep, maybe):
        if not isinstance(arr, list):
            continue
        for v in arr:
            try:
                out.append(int(v))
            except Exception:
                continue

    # dedupe while preserving order
    seen = set()
    final = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        final.append(x)
    return final

def _openai_extract_recos_from_section(section_text: str, heading_path: str) -> List[Dict[str, str]]:
    """
    Second pass: extract recommendations from the full section text.
    """
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    sec = (section_text or "").strip()
    if not sec:
        return []

    strictness = (GUIDELINE_OPENAI_STRICTNESS or "medium").strip().lower()

    instructions = f"""You extract *formal clinical guideline recommendations* from a single guideline section.
You must be faithful to the text. The audience is a hospital-based clinician.

Return ONLY valid JSON with this exact shape:
{{ "items": [ {{"recommendation_text":"...","strength_raw":"...","evidence_raw":"...","source_snippet":"..."}}, ... ] }}

Rules:
- Use ONLY what is explicitly present in the section. Never infer.
- If no formal recommendation is present, return {{ "items": [] }}.
- recommendation_text: include the full actionable directive sentence(s). Do not truncate clauses.
- strength_raw / evidence_raw: include only if explicitly stated AND clearly tied to that exact recommendation (same sentence, same bullet/numbered item, or immediate adjacent label).
- If strength/evidence appears only as a section/table-wide label or the mapping is ambiguous, leave it empty.
- Never copy a strength/evidence label from one recommendation to a different recommendation.
- Do NOT use directive wording (e.g., "we recommend", "we suggest") as strength/evidence labels.
- source_snippet: verbatim excerpt <= 240 chars that supports the recommendation (include grade markers if present).
- Strings only; never null. No extra keys.

Do NOT extract any of the following:
- Flowchart labels, captions, or single-step fragments (e.g., "Perform diagnostic imaging", "All criteria met?").
- Administrative, documentation, or quality-assurance directives (e.g., "results should be stored in the medical record").
- Training or credentialing requirements (e.g., "clinician skill level must be formally assessed").
- Vague truisms that any clinician already knows (e.g., "decisions should be tailored to each patient's needs").
- Meta-commentary about evidence quality, guideline methodology, or how to interpret recommendations.
- Sentences that only qualify or caveat another recommendation without standalone clinical value (e.g., "However, this recommendation does not obviate…").
- References to tables, figures, or other guidelines that carry no standalone clinical content (e.g., "Refer to References 6 and 7").
- Patient communication, shared decision-making guidance, or patient education materials.

Strictness mode: '{strictness}'
- In 'strict': extract only clearly labeled/graded or clearly directive guidance intended as recommendations.
- In 'loose': allow ungraded but clearly directive practice guidance.
"""

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": f"HEADING_PATH:\n{(heading_path or '').strip()}\n\nSECTION_TEXT:\n{sec}\n\nReturn JSON now.",
        "text": {"verbosity": "low"},
        "max_output_tokens": 1400,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    r.raise_for_status()

    raw = (_extract_output_text(r.json()) or "").strip()
    if not raw:
        return []

    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
        if not m:
            return []
        try:
            obj = json.loads(m.group(1))
        except Exception:
            return []

    items = obj.get("items")
    if not isinstance(items, list):
        return []

    def _strength_evidence_clearly_associated(source_snippet: str, strength_raw: str, evidence_raw: str) -> bool:
        strength = (strength_raw or "").strip()
        evidence = (evidence_raw or "").strip()
        if not strength and not evidence:
            return True

        snip = re.sub(r"\s+", " ", (source_snippet or "").strip().lower())
        if not snip:
            return False

        for raw in [strength, evidence]:
            piece = (raw or "").strip()
            if not piece:
                continue

            pnorm = re.sub(r"\s+", " ", piece.lower())
            if pnorm and pnorm in snip:
                continue

            toks = [t for t in re.findall(r"[a-z0-9]+", pnorm) if len(t) >= 2]
            if toks and not any(t in snip for t in toks):
                return False

        return True

    out: List[Dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        rec = (it.get("recommendation_text") or "").strip()
        if not rec:
            continue
        strength = _sanitize_guideline_attr_value(it.get("strength_raw") or "")
        evidence = _sanitize_guideline_attr_value(it.get("evidence_raw") or "")
        snippet = (it.get("source_snippet") or "").strip()

        if not _strength_evidence_clearly_associated(snippet, strength, evidence):
            strength = ""
            evidence = ""

        out.append(
            {
                "recommendation_text": rec,
                "strength_raw": strength,
                "evidence_raw": evidence,
                "source_snippet": snippet,
            }
        )
    return out

def extract_and_store_guideline_recommendations_azure(guideline_id: str, pdf_bytes: bytes, progress_cb=None) -> int:
    gid = (guideline_id or "").strip()
    if not gid:
        return 0
    
    def _progress(done=0, total=0, msg="", detail=""):
        if not progress_cb:
            return
        try:
            progress_cb(done, total, msg=msg, detail=detail)
        except TypeError:
            try:
                progress_cb(done, total, msg or detail or "")
            except TypeError:
                progress_cb(done, total)


    _progress(
        0, 0,
        msg="Step 1/4 — Converting PDF to text…",
        detail="Azure Document Intelligence → Markdown",
    )
    md = markdown_from_pdf_bytes(pdf_bytes)
    if not md:
        _progress(0, 0, msg="No extractable text found.", detail="PDF → Markdown returned empty content")
        return 0

    _progress(
        0, 0,
        msg="Step 2/4 — Splitting document into sections…",
        detail="Parsing headings and building a section map",
    )
    sections = _split_markdown_into_sections(md)
    if not sections:
        _progress(0, 0, msg="No sections found.", detail="Could not split document into headings/sections")
        return 0
    if len(sections) > 3000:
        sections = sections[:3000]

    _progress(
        0, len(sections),
        msg="Step 2/4 — Triaging sections for recommendations…",
        detail="Scanning section previews for directive/recommendation language",
    )

    keep_sec_idxs: List[int] = []
    for b0 in range(0, len(sections), SECTION_TRIAGE_BATCH):
        batch = sections[b0 : b0 + SECTION_TRIAGE_BATCH]
        try:
            keep = _openai_triage_sections(batch)
        except Exception:
            keep = []
        keep_sec_idxs.extend(keep)

        _progress(
            min(b0 + len(batch), len(sections)),
            len(sections),
            msg="Step 2/4 — Triaging sections for recommendations…",
            detail="Scanning section previews for directive/recommendation language",
        )

    keep_set = set(int(x) for x in keep_sec_idxs if isinstance(x, int) or str(x).isdigit())
    if not keep_set:
        _progress(
            len(sections), len(sections),
            msg="No recommendation sections detected.",
            detail="Triage step did not flag any candidate sections",
        )
        return 0

    keep_sections: List[Dict[str, str]] = []
    for s in sections:
        try:
            sec_idx = int(s.get("sec_idx") or 0)
        except Exception:
            continue
        if sec_idx in keep_set:
            keep_sections.append(s)

    _progress(
        0, len(keep_sections),
        msg="Step 3/4 — Extracting recommendations…",
        detail=f"Analyzing {len(keep_sections)} candidate section(s)",
    )

    # Build rec list in memory (no DB rec table)
    recs: List[Dict[str, str]] = []
    seen = set()

    total_keep = len(keep_sections)
    for si, s in enumerate(keep_sections, start=1):
        path = (s.get("path") or "").strip() or "(no heading)"
        content = (s.get("content") or "").strip()
        if not content:
            _progress(si, total_keep, msg="Step 3/4 — Extracting recommendations…", detail=f"Skipped empty section {si}/{total_keep}")
            continue

        _progress(
            si - 1, total_keep,
            msg="Step 3/4 — Extracting recommendations…",
            detail=f"Section {si}/{total_keep}: {path[:90]}",
        )

        parts = _split_large_section(content, max_chars=SECTION_MAX_CHARS_SEND, overlap=SECTION_PART_OVERLAP_CHARS)
        for pi, part in enumerate(parts, start=1):
            part_path = path if len(parts) == 1 else f"{path} (part {pi}/{len(parts)})"
            try:
                extracted = _openai_extract_recos_from_section(part, part_path)
            except Exception:
                extracted = []

            for rco in extracted:
                rec_text = (rco.get("recommendation_text") or "").strip()
                if not rec_text:
                    continue
                strength = (rco.get("strength_raw") or "").strip()
                evidence = (rco.get("evidence_raw") or "").strip()
                snippet = (rco.get("source_snippet") or "").strip()

                dedupe_key = (rec_text.lower(), strength.lower(), evidence.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                snip_final = f"[{path}] {snippet}".strip() if snippet else f"[{path}]".strip()
                recs.append(
                    {
                        "recommendation_text": rec_text,
                        "strength_raw": strength,
                        "evidence_raw": evidence,
                        "source_snippet": snip_final,
                    }
                )

        _progress(
            si, total_keep,
            msg="Step 3/4 — Extracting recommendations…",
            detail=f"Finished section {si}/{total_keep} • {len(recs)} unique recommendation(s) found so far",
        )

    if not recs:
        _progress(total_keep, total_keep, msg="No recommendations extracted.", detail="Candidate sections produced no extractable recommendations")
        return 0

    meta_now = get_guideline_meta(gid) or {}
    _progress(
        0, 0,
        msg="Step 4/4 — Generating clinician-friendly display…",
        detail=f"Organizing {len(recs)} recommendation(s) into sections",
    )
    disp_md = gpt_generate_guideline_recommendations_display(recs, meta_now, progress_cb=_progress)

    _progress(0, 0, msg="Step 4/4 — Saving display…", detail="Writing final Markdown to database")
    update_guideline_recommendations_display(gid, disp_md)

    _progress(0, 0, msg="Done.", detail=f"Saved {len(recs)} recommendation(s)")
    return len(recs)



# ---------------- Guideline metadata extraction ----------------

def _parse_year4(raw: str) -> str:
    s = (raw or "").strip()
    m = _GUIDELINE_YEAR_RE.search(s)
    if not m:
        return ""
    y = int(m.group(1))
    if 1900 <= y <= (datetime.now().year + 1):
        return str(y)
    return ""


def _guideline_meta_snippet(md: str, max_chars: int = 9000) -> str:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    head = "\n".join(lines[:140])

    kw_re = re.compile(
        r"(?i)\b(published|publication|issued|released|updated|update|revision|copyright|©|guideline|statement|"
        r"recommendation|consensus|society|association|college)\b"
    )

    picked = []
    seen = set()
    for ln in lines[:600]:
        if _GUIDELINE_YEAR_RE.search(ln) or kw_re.search(ln) or ln.startswith("#"):
            key = ln.lower()
            if key in seen:
                continue
            seen.add(key)
            picked.append(ln)
        if len(picked) >= 220:
            break

    blob = head + "\n\n" + "\n".join(picked)
    return blob[:max_chars].strip()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def gpt_extract_guideline_title_year(
    filename: str,
    snippet: str,
    timeout_s: int = 60,
    max_attempts: int = 5,
) -> Dict[str, str]:
    key = _openai_api_key()
    if not key:
        raise RuntimeError("Missing OpenAI API key. Put OPENAI_API_KEY in .streamlit/secrets.toml.")

    fn = (filename or "").strip()
    sn = (snippet or "").strip()
    if not sn:
        return {"guideline_name": "", "society": "", "pub_year": ""}

    instructions = (
        "You extract metadata from a clinical guideline document excerpt.\n"
        "Return ONLY valid JSON (no markdown) with this exact shape:\n"
        "{\"guideline_name\":\"...\",\"society\":\"...\",\"pub_year\":\"...\"}\n"
        "Rules:\n"
        "- Use ONLY what is explicitly present in the text.\n"
        "- guideline_name: the guideline title WITHOUT the society/organization name prefix "
        "and WITHOUT any year. Strip leading society names, acronyms, and boilerplate like "
        "'Clinical Guideline:', 'Clinical Practice Update:', 'Practice Guideline:', "
        "'Expert Consensus', etc. Also strip any leading or trailing 4-digit year. "
        "Keep the core clinical topic and scope. "
        "Example: '2026 ACG Clinical Guideline: Hepatic Encephalopathy' "
        "→ guideline_name='Hepatic Encephalopathy', society='ACG', pub_year='2026'.\n"
        "- society: the abbreviated name (acronym) of the publishing society/organization "
        "(e.g. 'ACG', 'AHA/ACC', 'IDSA', 'SCCM', 'AGA', 'KDIGO', 'ASCO'). "
        "If multiple societies, join with '/'. If not identifiable, use empty string.\n"
        "- pub_year: a 4-digit year ONLY if explicitly stated as the publication year; else empty string.\n"
        "- If multiple years appear, choose the one most clearly tied to publication.\n"
        "- Strings only; never null; no extra keys."
    )

    payload = {
        "model": _openai_model(),
        "instructions": instructions,
        "input": f"FILENAME:\n{fn}\n\nTEXT EXCERPT:\n{sn}\n\nReturn JSON now.",
        "text": {"verbosity": "low"},
        "max_output_tokens": 220,
        "temperature": 0,
        "store": False,
    }

    r = _post_with_retries(
        OPENAI_RESPONSES_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=max(5, int(timeout_s)),
        max_attempts=max(1, int(max_attempts)),
    )
    r.raise_for_status()

    raw = (_extract_output_text(r.json()) or "").strip()
    if not raw:
        return {"guideline_name": "", "society": "", "pub_year": ""}

    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
        if not m:
            return {"guideline_name": "", "society": "", "pub_year": ""}
        try:
            obj = json.loads(m.group(1))
        except Exception:
            return {"guideline_name": "", "society": "", "pub_year": ""}

    return {
        "guideline_name": (obj.get("guideline_name") or "").strip(),
        "society": (obj.get("society") or "").strip(),
        "pub_year": (obj.get("pub_year") or "").strip(),
    }

def extract_and_store_guideline_metadata_azure(guideline_id: str, pdf_bytes: bytes) -> Dict[str, str]:
    gid = (guideline_id or "").strip()
    if not gid:
        return {}

    meta = get_guideline_meta(gid) or {}
    if not meta:
        return {}

    md = ""
    try:
        # Metadata does not need full-document OCR; keep this fast and bounded.
        md = analyze_pdf_to_markdown_azure(pdf_bytes, pages="1-5", timeout_s=18.0)
    except Exception:
        try:
            md = analyze_pdf_to_markdown_azure(pdf_bytes, pages="1-2", timeout_s=10.0)
        except Exception:
            md = ""

    if not md:
        return {}

    snippet = _guideline_meta_snippet(md)
    fn = meta.get("filename", "")

    gname = ""
    society = ""
    year = ""
    try:
        out = gpt_extract_guideline_title_year(fn, snippet, timeout_s=15, max_attempts=1)
        gname = (out.get("guideline_name") or "").strip()
        society = (out.get("society") or "").strip()
        year = _parse_year4(out.get("pub_year") or "")
    except Exception:
        gname = ""
        society = ""
        year = ""

    if not year:
        year = _parse_year4(snippet[:1200])

    try:
        spec = gpt_extract_specialty(gname or fn, snippet, timeout_s=15, max_attempts=1)
    except Exception:
        spec = ""

    existing = get_guideline_meta(gid) or {}
    final_name = (gname or "").strip() or (existing.get("guideline_name") or "").strip()
    final_society = (society or "").strip() or (existing.get("society") or "").strip()
    final_year = (year or "").strip() or (existing.get("pub_year") or "").strip()
    final_spec = (spec or "").strip() or (existing.get("specialty") or "").strip()

    update_guideline_metadata(
        guideline_id=gid,
        guideline_name=final_name or None,
        pub_year=final_year or None,
        specialty=final_spec or None,
        society=final_society or None,
    )

    return {"guideline_name": final_name, "society": final_society, "pub_year": final_year, "specialty": final_spec}
