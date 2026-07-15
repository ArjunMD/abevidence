import calendar
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

from db import hide_pubmed_pmid, list_search_pubmed_ledger, unhide_pubmed_pmid, upsert_search_pubmed_ledger
from extract import search_pubmed_by_date_filters_page, search_pubmed_by_term_page
from pages_shared import _filter_search_pubmed_rows

TERM_SEARCH_FETCH_LIMIT = 500
# Earliest publication year the topic search will reach back to.
TERM_SEARCH_MIN_YEAR = 2000
# Tier 1 (top journals) is NEVER display-capped — losing a top-journal hit would
# defeat the point. Tiers 2 (other named journals) and 3 (the rest of PubMed)
# each get their own cap, which doubles as a guaranteed minimum: because Tier 1
# never eats into them, these tiers always appear (up to their cap).
TERM_SEARCH_NAMED_DISPLAY_CAP = 40
TERM_SEARCH_REST_DISPLAY_CAP = 30

SEARCH_FETCH_LIMIT = 500
LEDGER_STUDY_TYPE_LABEL = "All"

# Pediatric/adolescent studies are out of scope; drop any result whose title
# mentions these (word-boundary matched so "adult" etc. is unaffected).
PEDIATRIC_TITLE_PATTERN = re.compile(
    r"\b("
    r"child|children|childhood|"
    r"pediatric|pediatrics|paediatric|paediatrics|"
    r"adolescent|adolescents|adolescence|"
    r"infant|infants|infancy|"
    r"neonatal|neonate|neonates|neonatology|"
    r"newborn|newborns"
    r")\b",
    re.IGNORECASE,
)


def _is_pediatric_title(title: str) -> bool:
    return bool(PEDIATRIC_TITLE_PATTERN.search(title or ""))

COMBINED_PUBLICATION_TYPE_TERMS = [
    '"Clinical Trial"[Publication Type]',
    '"Meta-Analysis"[Publication Type]',
    '"Systematic Review"[Publication Type]',
    '"Observational Study"[Publication Type]',
    '"Multicenter Study"[Publication Type]',
    '"Comparative Study"[Publication Type]',
    '"Clinical Study"[Publication Type]',
    '"Validation Study"[Publication Type]',
]

# Non-article publication types stripped out of the broad search below.
EXCLUDED_PUBLICATION_TYPE_TERMS = [
    "Editorial[pt]",
    "Letter[pt]",
    "Comment[pt]",
    "News[pt]",
    "Biography[pt]",
    '"Published Erratum"[pt]',
]

# Raw PubMed <PublicationType> tags worth surfacing next to a result, mapped to
# a short display label, ordered by how much they narrow down the evidence type
# (most specific/informative first). PubMed tags most articles with several
# generic types (e.g. "Journal Article") alongside 0-1 of these — the first
# match in this order is shown.
PUBLICATION_TYPE_DISPLAY_LABELS = {
    "Randomized Controlled Trial": "RCT",
    "Meta-Analysis": "Meta-Analysis",
    "Systematic Review": "Systematic Review",
    "Practice Guideline": "Practice Guideline",
    "Multicenter Study": "Multicenter Study",
    "Observational Study": "Observational Study",
    "Clinical Trial": "Clinical Trial",
    "Comparative Study": "Comparative Study",
    "Validation Study": "Validation Study",
    "Case Reports": "Case Report",
    "Clinical Study": "Clinical Study",
    "Review": "Review",
}


def _pick_display_publication_type(publication_types: list) -> str:
    types = {(str(t or "")).strip() for t in (publication_types or [])}
    for raw, label in PUBLICATION_TYPE_DISPLAY_LABELS.items():
        if raw in types:
            return label
    return ""

# High-yield journals searched broadly (journal NOT the excluded types) so
# original articles that carry no study-type tag are still surfaced. The narrow
# study-type filter (COMBINED_PUBLICATION_TYPE_TERMS) is used for every other
# journal. JAMA Network Open is deliberately NOT here — its volume is too high
# for a broad sweep.
BROAD_SEARCH_JOURNAL_LABELS = {
    "NEJM",
    "JAMA",
    "Lancet",
    "AIM",
    "JAMA Internal Medicine",
    "Journal of Hospital Medicine",
    "American Journal of Medicine",
    "Stroke",
    "Intensive Care Medicine",
    "Critical Care",
    "Journal of the American College of Cardiology",
    "European Heart Journal",
    "Annals of Emergency Medicine",
}
SPECIALTY_JOURNAL_TERMS = {
    "General": {
        "NEJM": '"N Engl J Med"[jour]',
        "JAMA": '"JAMA"[jour]',
        "Lancet": '"Lancet"[jour]',
        "BMJ": '"BMJ"[jour]',
        "Nat Med": '"Nat Med"[jour]',
        "AIM": '"Ann Intern Med"[jour]',
    },
    "Internal Medicine": {
        "JAMA Internal Medicine": '"JAMA Intern Med"[Journal]',
        "JGIM": '"J Gen Intern Med"[Journal]',
        "Journal of Hospital Medicine": '"J Hosp Med"[Journal]',
        "American Journal of Medicine": '"Am J Med"[Journal]',
        "Cochrane Systematic Reviews": '"Cochrane Database Syst Rev"[Journal]',
    },
    "Neurology": {
        "JAMA Neurology": '"JAMA Neurol"[Journal]',
        "Lancet Neurology": '"Lancet Neurol"[Journal]',
        "Stroke": '"Stroke"[Journal]',
    },
    "Critical care": {
        "Intensive Care Medicine": '"Intensive Care Med"[Journal]',
        "Critical Care": '"Crit Care"[Journal]',
        "Anesthesiology": '"Anesthesiology"[Journal]',
    },
    "Cardiology": {
        "JAMA Cardiology": '"JAMA Cardiol"[Journal]',
        "Journal of the American College of Cardiology": '"J Am Coll Cardiol"[Journal]',
        "European Heart Journal": '"Eur Heart J"[Journal]',
        "Circulation": '"Circulation"[Journal]',
    },
    "Infectious Disease": {
        "Lancet Infectious Diseases": '"Lancet Infect Dis"[Journal]',
        "Clinical Infectious Diseases": '"Clin Infect Dis"[Journal]',
    },
    "Pulmonology": {
        "Lancet Respiratory Medicine": '"Lancet Respir Med"[Journal]',
        "American Journal of Respiratory and Critical Care Medicine": '"Am J Respir Crit Care Med"[Journal]',
        "CHEST": '"Chest"[Journal]',
    },
    "Surgery": {
        "JAMA Surgery": '"JAMA Surg"[Journal]',
        "Annals of Surgery": '"Ann Surg"[Journal]',
    },
    "Psychiatry": {
        "JAMA Psychiatry": '"JAMA Psychiatry"[Journal]',
        "Lancet Psychiatry": '"Lancet Psychiatry"[Journal]',
        "World Psychiatry": '"World Psychiatry"[Journal]',
    },
    "Gastroenterology": {
        "Lancet Gastroenterology & Hepatology": '"Lancet Gastroenterol Hepatol"[Journal]',
        "Gastroenterology": '"Gastroenterology"[Journal]',
        "Gut": '"Gut"[Journal]',
        "The American Journal of Gastroenterology": '"Am J Gastroenterol"[Journal]',
    },
    "Emergency Medicine": {
        "Annals of Emergency Medicine": '"Ann Emerg Med"[Journal]',
        "Resuscitation": '"Resuscitation"[Journal]',
    },
    "Nephrology": {
        "Journal of the American Society of Nephrology": '"J Am Soc Nephrol"[Journal]',
        "Kidney International": '"Kidney Int"[Journal]',
        "American Journal of Kidney Diseases": '"Am J Kidney Dis"[Journal]',
    },
    "Endocrinology/Diabetes": {
        "Lancet Diabetes & Endocrinology": '"Lancet Diabetes Endocrinol"[Journal]',
        "Diabetes Care": '"Diabetes Care"[Journal]',
        "Journal of Clinical Endocrinology & Metabolism": '"J Clin Endocrinol Metab"[Journal]',
    },
    "Hematology": {
        "Lancet Haematology": '"Lancet Haematol"[Journal]',
        "Blood": '"Blood"[Journal]',
    },
    "Oncology": {
        "JAMA Oncology": '"JAMA Oncol"[Journal]',
        "Lancet Oncology": '"Lancet Oncol"[Journal]',
        "Journal of Clinical Oncology": '"J Clin Oncol"[Journal]',
    },
    "Rheumatology": {
        "Lancet Rheumatology": '"Lancet Rheumatol"[Journal]',
        "Annals of the Rheumatic Diseases": '"Ann Rheum Dis"[Journal]',
    },
    "Hepatology": {
        "Hepatology": '"Hepatology"[Journal]',
        "Journal of Hepatology": '"J Hepatol"[Journal]',
    },
    "Open-Access": {
        "JAMA Network Open": '"JAMA Netw Open"[Journal]',
    },
    "Palliative Care": {
        "Journal of Pain and Symptom Management": '"J Pain Symptom Manage"[Journal]',
    },
}

def _run_search_page(
    start_date: str,
    end_date: str,
    journal_term: str,
    publication_type_terms: list[str],
    retmax: int,
    retstart: int,
    exclude_publication_type_terms: list[str] | None = None,
    exclude_review_unless_terms: list[str] | None = None,
) -> dict[str, object]:
    page = search_pubmed_by_date_filters_page(
        start_date=start_date,
        end_date=end_date,
        journal_term=journal_term,
        publication_type_terms=publication_type_terms,
        retmax=int(retmax),
        retstart=int(retstart),
        exclude_publication_type_terms=exclude_publication_type_terms,
        exclude_review_unless_terms=exclude_review_unless_terms,
    )
    rows = [r for r in (page.get("rows") or []) if isinstance(r, dict)]
    try:
        total_count = int(page.get("total_count") or 0)
    except Exception:
        total_count = 0
    return {"rows": rows, "total_count": max(0, total_count)}


def _format_pub_date(pub_year: object, pub_month: object) -> str:
    """"Month Year" (or just "Year") for display next to a journal name.
    ``pub_month`` is the "MM" token extract.py already parses out of the
    efetch XML — no extra PubMed call needed."""
    year = (str(pub_year or "")).strip()
    if not year:
        return ""
    month_raw = (str(pub_month or "")).strip()
    try:
        m = int(month_raw)
        if 1 <= m <= 12:
            return f"{calendar.month_name[m]} {year}"
    except Exception:
        pass
    return year


def _parse_year_month_parts(year_month: str) -> dict[str, str]:
    ym = (year_month or "").strip()
    try:
        parts = ym.split("-")
        if len(parts) == 2:
            y = int(parts[0])
            m = int(parts[1])
            if 1 <= m <= 12:
                return {"year": str(y), "month": calendar.month_name[m]}
    except Exception:
        pass
    return {"year": ym or "—", "month": "—"}


def _parse_year_month_key(year_month: str) -> tuple[int, int] | None:
    ym = (year_month or "").strip()
    try:
        parts = ym.split("-")
        if len(parts) != 2:
            return None
        y = int(parts[0])
        m = int(parts[1])
        if y < 1900 or not (1 <= m <= 12):
            return None
        return (y, m)
    except Exception:
        return None


def _clearable_on_date_for_month(year: int, month: int):
    """
    Month is clearable 30 days after month-end to allow late indexing/backfill.
    """
    end_day = int(calendar.monthrange(int(year), int(month))[1])
    end_date = datetime(int(year), int(month), end_day, tzinfo=timezone.utc).date()
    return end_date + timedelta(days=30)


def _is_year_month_clearable(year_month: str, today) -> bool:
    ym = _parse_year_month_key(year_month)
    if ym is None:
        return True
    yy, mm = ym
    return bool(today >= _clearable_on_date_for_month(yy, mm))


def _is_future_year_month(year_month: str, today) -> bool:
    ym = _parse_year_month_key(year_month)
    if ym is None:
        return False
    return bool((int(ym[0]), int(ym[1])) > (int(today.year), int(today.month)))


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _render_search_ledger() -> None:
    st.markdown("##### Ledger")
    st.caption("One row per month searched (all journals together). Months clear 30 days after month-end.")
    today = datetime.now(timezone.utc).date()
    rows = list_search_pubmed_ledger()
    if not rows:
        st.caption("No months searched yet.")
        return

    # Aggregate by month so the ledger is robust to multiple rows per month
    # (e.g. legacy per-journal rows): one display row per month, cleared only
    # when every underlying row is cleared.
    by_month: dict[str, dict[str, object]] = {}
    for r in rows:
        ym_raw = (r.get("year_month") or "").strip()
        if not ym_raw or _is_future_year_month(ym_raw, today=today):
            continue
        agg = by_month.get(ym_raw)
        if agg is None:
            agg = {"still_shown": 0, "cleared": True, "verified": True, "last": ""}
            by_month[ym_raw] = agg
        agg["still_shown"] = int(agg["still_shown"]) + _safe_int(r.get("visible_matches"), 0)
        agg["cleared"] = bool(agg["cleared"]) and ((r.get("is_cleared") or "0") == "1")
        agg["verified"] = bool(agg["verified"]) and ((r.get("is_verified") or "0") == "1")
        lc = (r.get("last_checked_at") or "").strip()
        if lc > str(agg["last"]):
            agg["last"] = lc

    table_rows: list[dict[str, object]] = []
    for ym_raw, agg in by_month.items():
        ym_parts = _parse_year_month_parts(ym_raw)
        ym_key = _parse_year_month_key(ym_raw)
        clearable = _is_year_month_clearable(ym_raw, today=today)
        still_shown = int(agg["still_shown"])
        is_cleared = bool(agg["cleared"])
        is_verified = bool(agg["verified"])

        if is_cleared and clearable:
            status = "✅ Cleared"
        elif not is_verified:
            status = "Unverified"
        elif not clearable:
            status = "Not clearable yet"
        elif still_shown > 0:
            status = "In progress"
        else:
            status = "Ready to clear"

        year = (ym_parts.get("year") or "").strip()
        month = (ym_parts.get("month") or "").strip()
        if month and month != "—" and year and year != "—":
            month_label = f"{month} {year}"
        else:
            month_label = ym_raw or "—"

        last_checked = str(agg["last"]).strip()
        last_checked = last_checked[:10] if last_checked else "—"

        ym_sort = int(ym_key[0]) * 100 + int(ym_key[1]) if ym_key is not None else -1
        table_rows.append(
            {
                "Month": month_label,
                "Still shown": still_shown,
                "Status": status,
                "Last checked": last_checked,
                "_ym_sort": ym_sort,
            }
        )

    if not table_rows:
        st.caption("No months to display.")
        return

    table_rows.sort(key=lambda x: -_safe_int(x.get("_ym_sort"), -1))
    df = pd.DataFrame(table_rows)[["Month", "Still shown", "Status", "Last checked"]]
    st.dataframe(df, hide_index=True, width="stretch")


def _ordered_specialties() -> list[str]:
    return sorted(
        SPECIALTY_JOURNAL_TERMS.keys(),
        key=lambda s: (0 if str(s or "").strip().lower() == "general" else 1, str(s or "").lower()),
    )


def _all_journal_targets() -> list[tuple[str, str, str]]:
    """(specialty_label, journal_label, journal_term) for every configured journal."""
    targets: list[tuple[str, str, str]] = []
    for specialty in _ordered_specialties():
        for journal_label, journal_term in SPECIALTY_JOURNAL_TERMS.get(specialty, {}).items():
            targets.append((specialty, journal_label, journal_term))
    return targets


def _journal_label_map() -> dict[str, str]:
    """Map an NLM ISO abbreviation (lowercased) → display label for every
    configured journal, so results show a friendly name. The abbreviation is
    pulled from the quoted name in each journal term (e.g. '"N Engl J Med"[jour]'
    → "n engl j med")."""
    out: dict[str, str] = {}
    for (_specialty, label, term) in _all_journal_targets():
        m = re.match(r'\s*"([^"]+)"', term or "")
        if m:
            out[m.group(1).strip().lower()] = label
    return out


def _broad_journals_or_term() -> str:
    """OR of the [jour] clauses for the 'top journals' — the BROAD_SEARCH subset
    that gets the lenient study-type filter in the monthly sweep. Used to pull
    those journals into their own section of the topic-search results."""
    terms = [
        term
        for (_specialty, label, term) in _all_journal_targets()
        if (term or "").strip() and label in BROAD_SEARCH_JOURNAL_LABELS
    ]
    if not terms:
        return ""
    return "(" + " OR ".join(terms) + ")"


def _named_journals_or_term() -> str:
    """OR of every configured journal's [jour] clause (top + the rest of the
    named list), for the second tier of the topic search."""
    terms = [term for (_specialty, _label, term) in _all_journal_targets() if (term or "").strip()]
    if not terms:
        return ""
    return "(" + " OR ".join(terms) + ")"


def _render_term_search() -> None:
    """Free-text PubMed search (any journal, year >= TERM_SEARCH_MIN_YEAR),
    mutually exclusive with the month-by-month journal sweep above. Uses the
    lenient study-type filter for everything, and excludes trials already in the
    DB. Results are split into three tiers — top journals (BROAD_SEARCH subset,
    shown in full), the rest of the named journals, then every other PubMed
    journal (each of the latter two capped) — newest first within each. 'Don't
    show again' hides a PMID (shared with the sweep's hidden list); there's no
    ledger — searches themselves aren't saved."""
    st.markdown("##### Search by topic")
    st.caption(
        f"Search any term across all journals, {TERM_SEARCH_MIN_YEAR}–present "
        "(e.g. “Bacterial meningitis”). Top journals first, then your other named "
        "journals, then the rest of PubMed — newest first in each. Trials already "
        "in your database are skipped."
    )

    c_in, c_btn = st.columns([5, 1])
    with c_in:
        query = st.text_input(
            "Search term",
            key="search_pubmed_term_query",
            label_visibility="collapsed",
            placeholder="e.g. Bacterial meningitis",
        )
    with c_btn:
        term_clicked = st.button("Search", type="primary", width="stretch", key="search_pubmed_term_btn")

    titles_only = st.checkbox(
        "Search titles only",
        value=True,
        key="search_pubmed_term_titles_only",
        help="When on, only matches the term against article titles. Turn off to also "
        "match against abstracts/MeSH terms (broader, noisier).",
    )

    if term_clicked:
        q = (query or "").strip()
        if not q:
            st.warning("Enter a search term.")
        else:
            # Mutually exclusive with the journal sweep — clear its results.
            # Also drop any stale undo from a previous topic search.
            for k in [
                "search_pubmed_groups",
                "search_pubmed_range",
                "search_pubmed_last_hidden",
                "search_pubmed_term_last_hidden",
            ]:
                st.session_state.pop(k, None)
            with st.spinner(f"Searching PubMed for “{q}”…"):
                try:
                    # Three passes, each restricted by journal so a tier reliably
                    # surfaces even on high-volume topics (the long tail can't
                    # crowd it out of the most-recent window):
                    #   1. top journals  (BROAD_SEARCH subset)
                    #   2. all named journals  → tier 2 is this minus tier 1
                    #   3. every journal       → tier 3 is this minus tiers 1 & 2
                    def _run(journal_term: str) -> dict:
                        return search_pubmed_by_term_page(
                            term_query=q,
                            publication_type_terms=[],
                            retmax=int(TERM_SEARCH_FETCH_LIMIT),
                            retstart=0,
                            exclude_publication_type_terms=EXCLUDED_PUBLICATION_TYPE_TERMS,
                            exclude_review_unless_terms=COMBINED_PUBLICATION_TYPE_TERMS,
                            journal_term=journal_term,
                            mindate=f"{TERM_SEARCH_MIN_YEAR}/01/01",
                            titles_only=titles_only,
                        )

                    top = _run(_broad_journals_or_term())
                    named = _run(_named_journals_or_term())
                    everything = _run("")

                    def _rows(page: dict) -> list[dict]:
                        return [r for r in (page.get("rows") or []) if isinstance(r, dict)]

                    def _pmid(r: dict) -> str:
                        return (r.get("pmid") or "").strip()

                    top_rows = _rows(top)
                    top_pmids = {_pmid(r) for r in top_rows}
                    named_other_rows = [r for r in _rows(named) if _pmid(r) not in top_pmids]
                    named_pmids = top_pmids | {_pmid(r) for r in _rows(named)}
                    rest_rows = [r for r in _rows(everything) if _pmid(r) not in named_pmids]

                    st.session_state["search_pubmed_term_results"] = {
                        "query": q,
                        "top_rows": top_rows,
                        "named_other_rows": named_other_rows,
                        "rest_rows": rest_rows,
                        "total_count": int(everything.get("total_count") or 0),
                    }
                except requests.HTTPError as e:
                    st.session_state.pop("search_pubmed_term_results", None)
                    st.error(f"PubMed search failed: {e}")
                except Exception as e:
                    st.session_state.pop("search_pubmed_term_results", None)
                    st.error(f"Unexpected search error: {e}")

    result = st.session_state.get("search_pubmed_term_results")
    if not isinstance(result, dict):
        return

    last_hidden = st.session_state.get("search_pubmed_term_last_hidden")
    if isinstance(last_hidden, dict) and (last_hidden.get("pmid") or "").strip():
        u_msg, u_btn = st.columns([6, 1])
        with u_msg:
            _hidden_title = (last_hidden.get("title") or "").strip() or str(last_hidden.get("pmid"))
            if len(_hidden_title) > 70:
                _hidden_title = _hidden_title[:70].rstrip() + "…"
            st.caption(f"Hidden “{_hidden_title}”")
        with u_btn:
            if st.button("↩︎ Undo", key="search_pubmed_term_undo_hide", use_container_width=True):
                unhide_pubmed_pmid(str(last_hidden.get("pmid") or ""))
                st.session_state.pop("search_pubmed_term_last_hidden", None)
                st.rerun()

    label_map = _journal_label_map()

    def _clean(rows: list) -> list[dict]:
        # Drops trials already in the DB (saved), previously-hidden PMIDs, and
        # pediatric titles. Sorts newest first (no rank within a tier).
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        rows = _filter_search_pubmed_rows(rows)
        rows = [r for r in rows if not _is_pediatric_title(r.get("title"))]
        rows.sort(key=lambda r: _safe_int(r.get("recency_rank"), 10**9))
        return rows

    # Three tiers, no rank within any — each newest first.
    top_rows = _clean(result.get("top_rows"))
    named_rows = _clean(result.get("named_other_rows"))
    rest_rows = _clean(result.get("rest_rows"))

    # Tier 1 shown in full; Tiers 2 & 3 each capped (so they always appear and
    # stay bounded regardless of how large Tier 1 is).
    top_shown = top_rows
    named_shown = named_rows[:TERM_SEARCH_NAMED_DISPLAY_CAP]
    rest_shown = rest_rows[:TERM_SEARCH_REST_DISPLAY_CAP]

    visible_count = len(top_shown) + len(named_shown) + len(rest_shown)
    hidden = (len(named_rows) - len(named_shown)) + (len(rest_rows) - len(rest_shown))

    q_label = (result.get("query") or "").strip()
    total = int(result.get("total_count") or 0)
    caption = f"“{q_label}” — {visible_count} shown"
    if total:
        caption += f" (of {total} matches)"
    if hidden > 0:
        caption += f"; {hidden} more hidden"
    st.caption(caption)

    if visible_count == 0:
        st.info("No new results for this term.")
        return

    def _render_rows(rows: list[dict]) -> None:
        for r in rows:
            title = (r.get("title") or "").strip() or "(no title)"
            pmid = (r.get("pmid") or "").strip() or "—"
            iso = (r.get("journal_iso") or "").strip()
            label = label_map.get(iso.lower(), iso) or "Other journal"
            date_bit = _format_pub_date(r.get("pub_year"), r.get("pub_month"))
            if date_bit:
                label = f"{label} — {date_bit}"
            pub_type = _pick_display_publication_type(r.get("publication_types"))
            if pub_type:
                label = f"{label} — {pub_type}"

            c_left, c_right = st.columns([5, 3])
            with c_left:
                st.markdown(f"- {title}  \n  _{label}_")
            with c_right:
                if pmid != "—":
                    b1, b2 = st.columns(2, gap="small")
                    with b1:
                        if st.button(
                            "Don't show again",
                            key=f"search_pubmed_term_hide_{pmid}",
                            use_container_width=True,
                        ):
                            hide_pubmed_pmid(pmid, journal=label)
                            st.session_state["search_pubmed_term_last_hidden"] = {
                                "pmid": pmid,
                                "title": title,
                            }
                            st.rerun()
                    with b2:
                        if st.button(
                            "Open abstract",
                            key=f"search_pubmed_term_open_{pmid}",
                            use_container_width=True,
                        ):
                            st.query_params["open_abs_pmid"] = pmid
                            st.rerun()

    if top_shown:
        st.markdown("### Top journals")
        _render_rows(top_shown)
    if named_shown:
        st.markdown("### Other named journals")
        _render_rows(named_shown)
    if rest_shown:
        st.markdown("### All other journals")
        _render_rows(rest_shown)


def render() -> None:
    st.title("🔎 Search PubMed")

    today = datetime.now(timezone.utc).date()
    default_month_date = today - timedelta(days=30)
    default_year = int(default_month_date.year)
    default_month = int(default_month_date.month)
    min_year = max(1900, default_year - 25)
    year_options = list(range(default_year, min_year - 1, -1))
    sticky = st.session_state.get("search_pubmed_filters_sticky")
    if not isinstance(sticky, dict):
        sticky = {}

    c1, c2 = st.columns(2)
    with c1:
        sticky_year = sticky.get("year")
        year_default = int(sticky_year) if isinstance(sticky_year, int) and sticky_year in year_options else int(default_year)
        selected_year = st.selectbox(
            "Year",
            options=year_options,
            index=year_options.index(year_default),
            key="search_pubmed_year",
        )
    with c2:
        sticky_month = sticky.get("month")
        month_default = int(sticky_month) if isinstance(sticky_month, int) and 1 <= int(sticky_month) <= 12 else int(default_month)
        selected_month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            index=max(0, min(11, month_default - 1)),
            format_func=lambda m: calendar.month_name[int(m)],
            key="search_pubmed_month",
        )

    st.session_state["search_pubmed_filters_sticky"] = {
        "year": int(selected_year),
        "month": int(selected_month),
    }

    b_search, b_clear = st.columns(2)
    with b_search:
        search_clicked = st.button("Search all journals", type="primary", width="stretch", key="search_pubmed_btn")
    with b_clear:
        clear_clicked = st.button("Clear search", width="stretch", key="search_pubmed_clear_btn")

    if clear_clicked:
        for k in ["search_pubmed_groups", "search_pubmed_range", "search_pubmed_last_hidden"]:
            st.session_state.pop(k, None)
        st.rerun()

    if search_clicked:
        # Mutually exclusive with the topic search below — clear its results.
        st.session_state.pop("search_pubmed_term_results", None)
        st.session_state.pop("search_pubmed_term_last_hidden", None)
        try:
            start_date = datetime(int(selected_year), int(selected_month), 1, tzinfo=timezone.utc).date()
            end_day = int(calendar.monthrange(int(selected_year), int(selected_month))[1])
            end_date = datetime(int(selected_year), int(selected_month), end_day, tzinfo=timezone.utc).date()
        except Exception:
            st.error("Invalid year/month selection.")
            st.stop()

        if (int(selected_year), int(selected_month)) > (int(today.year), int(today.month)):
            for k in ["search_pubmed_groups", "search_pubmed_range"]:
                st.session_state.pop(k, None)
            st.error("Future months are not allowed in Search PubMed. Please choose the current month or earlier.")
        else:
            start_s = start_date.strftime("%Y/%m/%d")
            end_s = end_date.strftime("%Y/%m/%d")
            pub_terms = list(COMBINED_PUBLICATION_TYPE_TERMS)
            targets = _all_journal_targets()
            groups: list[dict[str, object]] = []
            progress = st.progress(0.0, text="Searching PubMed…")
            errored = False
            try:
                for i, (specialty_label, journal_label, journal_term) in enumerate(targets):
                    progress.progress(i / max(1, len(targets)), text=f"Searching {journal_label}…")
                    broad = journal_label in BROAD_SEARCH_JOURNAL_LABELS
                    page = _run_search_page(
                        start_date=start_s,
                        end_date=end_s,
                        journal_term=journal_term,
                        publication_type_terms=[] if broad else pub_terms,
                        retmax=int(SEARCH_FETCH_LIMIT),
                        retstart=0,
                        exclude_publication_type_terms=EXCLUDED_PUBLICATION_TYPE_TERMS if broad else None,
                        exclude_review_unless_terms=pub_terms if broad else None,
                    )
                    rows = [r for r in (page.get("rows") or []) if isinstance(r, dict)]
                    groups.append(
                        {
                            "specialty": specialty_label,
                            "journal": journal_label,
                            "total_count": int(page.get("total_count") or 0),
                            "rows": rows,
                        }
                    )
            except requests.HTTPError as e:
                errored = True
                st.error(f"PubMed search failed: {e}")
            except Exception as e:
                errored = True
                st.error(f"Unexpected search error: {e}")
            finally:
                progress.empty()

            if not errored:
                st.session_state.pop("search_pubmed_last_hidden", None)
                st.session_state["search_pubmed_groups"] = groups
                st.session_state["search_pubmed_range"] = {
                    "start": start_s,
                    "end": end_s,
                    "year_month": f"{int(selected_year)}-{int(selected_month):02d}",
                    "year_month_label": f"{calendar.month_name[int(selected_month)]} {int(selected_year)}",
                }

    if "search_pubmed_groups" not in st.session_state:
        st.info("Choose a year and month, then click Search all journals.")
        st.divider()
        _render_search_ledger()
        st.divider()
        _render_term_search()
        return

    groups = [g for g in (st.session_state.get("search_pubmed_groups") or []) if isinstance(g, dict)]
    rng = st.session_state.get("search_pubmed_range") or {}
    ym_key = (rng.get("year_month") or "").strip()
    ym_label = (rng.get("year_month_label") or "").strip()
    is_future = _is_future_year_month(ym_key, today=today)
    is_time_clearable = _is_year_month_clearable(ym_key, today=today)

    grand_matches = sum(
        len([r for r in (g.get("rows") or []) if isinstance(r, dict)]) for g in groups
    )
    # Filled after the loop so it can report shown vs hidden, which depend on the
    # per-journal saved/hidden filtering done below.
    header_slot = st.empty()

    last_hidden = st.session_state.get("search_pubmed_last_hidden")
    if isinstance(last_hidden, dict) and (last_hidden.get("pmid") or "").strip():
        u_msg, u_btn = st.columns([6, 1])
        with u_msg:
            _hidden_title = (last_hidden.get("title") or "").strip() or str(last_hidden.get("pmid"))
            if len(_hidden_title) > 70:
                _hidden_title = _hidden_title[:70].rstrip() + "…"
            st.caption(f"Hidden “{_hidden_title}”")
        with u_btn:
            if st.button("↩︎ Undo", key="search_pubmed_undo_hide", use_container_width=True):
                unhide_pubmed_pmid(str(last_hidden.get("pmid") or ""))
                st.session_state.pop("search_pubmed_last_hidden", None)
                st.rerun()

    any_visible = False
    grand_shown = 0
    all_verified = True
    current_specialty: str | None = None
    for gi, g in enumerate(groups):
        specialty_label = (g.get("specialty") or "").strip()
        journal_label = (g.get("journal") or "").strip()
        # raw_count is PubMed's esearch match count (includes items later dropped
        # for lacking a real abstract); used for the >200 truncation check and the
        # month-level "all journals verified" roll-up.
        raw_count = int(g.get("total_count") or 0)
        rows = [r for r in (g.get("rows") or []) if isinstance(r, dict)]
        visible_rows = _filter_search_pubmed_rows(rows)
        visible_rows = [r for r in visible_rows if not _is_pediatric_title(r.get("title"))]
        visible_count = len(visible_rows)
        grand_shown += visible_count
        all_verified = all_verified and (raw_count <= int(SEARCH_FETCH_LIMIT))

        # Always surface truncation, even when this journal has no visible rows —
        # otherwise an over-cap journal that looks "empty" would hide the overflow.
        if raw_count > int(SEARCH_FETCH_LIMIT):
            st.warning(
                f"Failsafe: {journal_label} returned {raw_count} matches (> {SEARCH_FETCH_LIMIT}). "
                f"Only the first {SEARCH_FETCH_LIMIT} were fetched."
            )

        if not visible_rows:
            continue
        any_visible = True

        if specialty_label != current_specialty:
            current_specialty = specialty_label
            st.markdown(f"### {specialty_label}")
        st.markdown(f"**{journal_label}**")

        for r in visible_rows:
            title = (r.get("title") or "").strip() or "(no title)"
            pmid = (r.get("pmid") or "").strip() or "—"
            c_left, c_right = st.columns([5, 3])
            with c_left:
                st.markdown(f"- {title}")
            with c_right:
                if pmid != "—":
                    b1, b2 = st.columns(2, gap="small")
                    with b1:
                        if st.button(
                            "Don't show again",
                            key=f"search_pubmed_hide_{gi}_{pmid}",
                            use_container_width=True,
                        ):
                            _ym_parts = (ym_key or "").split("-")
                            _hide_year = _ym_parts[0] if len(_ym_parts) >= 1 else ""
                            _hide_month = _ym_parts[1] if len(_ym_parts) >= 2 else ""
                            hide_pubmed_pmid(
                                pmid,
                                journal=journal_label,
                                year=_hide_year,
                                pub_month=_hide_month,
                            )
                            st.session_state["search_pubmed_last_hidden"] = {
                                "pmid": pmid,
                                "title": title,
                            }
                            st.rerun()
                    with b2:
                        if st.button(
                            "Open abstract",
                            key=f"search_pubmed_open_abstract_{gi}_{pmid}",
                            use_container_width=True,
                        ):
                            st.query_params["open_abs_pmid"] = pmid
                            st.rerun()

    grand_hidden = max(0, grand_matches - grand_shown)

    # One ledger row per month (all journals rolled into one). The month is
    # cleared when nothing is left to show across every journal.
    if not is_future:
        month_cleared = bool(grand_shown == 0 and all_verified and is_time_clearable)
        upsert_search_pubmed_ledger(
            year_month=ym_key,
            specialty_label="All",
            journal_label="All",
            study_type_label=LEDGER_STUDY_TYPE_LABEL,
            total_matches=grand_matches,
            visible_matches=grand_shown,
            hidden_matches=grand_hidden,
            is_cleared=month_cleared,
            is_verified=all_verified,
        )

    header_bits = []
    if ym_label:
        header_bits.append(f"Month: {ym_label}")
    header_bits.append(f"{len(groups)} journals searched")
    header_bits.append(f"{grand_matches} matches ({grand_shown} shown, {grand_hidden} hidden)")
    header_slot.caption(" | ".join(header_bits))

    if not any_visible:
        st.info("No visible results across any journal for this month.")

    st.divider()
    _render_search_ledger()
    st.divider()
    _render_term_search()
