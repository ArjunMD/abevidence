import calendar
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

from db import hide_pubmed_pmid, list_search_pubmed_ledger, upsert_search_pubmed_ledger
from extract import search_pubmed_by_date_filters_page
from pages_shared import _filter_search_pubmed_rows

SEARCH_FETCH_LIMIT = 500
LEDGER_STUDY_TYPE_LABEL = "All"
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

SPECIALTY_LEDGER_BG_COLORS = {
    "general": "#fff4d6",
    "internal medicine": "#dff4ff",
    "neurology": "#e6ebff",
    "critical care": "#ffe2e2",
    "cardiology": "#fde3ec",
    "infectious disease": "#e5ffe8",
    "pulmonology": "#dffaf5",
    "surgery": "#ffe9db",
    "psychiatry": "#f0e8ff",
    "gastroenterology": "#fff1d9",
    "emergency medicine": "#ffe8cc",
    "nephrology": "#e5f0ff",
    "endocrinology/diabetes": "#fff2c2",
    "hematology": "#ffe7f0",
    "oncology": "#ffe2ea",
    "rheumatology": "#f3ecff",
    "hepatology": "#fef3d7",
    "open-access": "#e8f5e9",
    "palliative care": "#f3e5f5",
}


def _infer_specialty_from_journal_label(journal_label: str) -> str:
    jl = (journal_label or "").strip().lower()
    if not jl:
        return "—"
    for specialty, journals in SPECIALTY_JOURNAL_TERMS.items():
        for label in journals:
            if jl == (label or "").strip().lower():
                return specialty
    return "—"


def _specialty_cell_style(value: object) -> str:
    specialty = str(value or "").strip().lower()
    bg = SPECIALTY_LEDGER_BG_COLORS.get(specialty, "#f3f4f6")
    return f"background-color: {bg}; color: #1f2937; font-weight: 600;"


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


def _latest_clearable_year_month(today) -> tuple[int, int] | None:
    """
    Return the most recent (year, month) that is clearable under the 30-day rule.
    """
    yy = int(today.year)
    mm = int(today.month)
    for _ in range(2400):
        ym = f"{yy:04d}-{mm:02d}"
        if _is_year_month_clearable(ym, today=today):
            return (yy, mm)
        if mm == 1:
            yy -= 1
            mm = 12
        else:
            mm -= 1
    return None


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _canonical_ledger_study_type(label: str) -> str:
    s = " ".join((label or "").strip().lower().replace("-", " ").replace("_", " ").split())
    if s in ("clinical trial", "clinical trials"):
        return "clinical_trial"
    if s in ("meta analysis", "meta analyses"):
        return "meta_analysis"
    if s in ("systematic review", "systematic reviews"):
        return "systematic_review"
    return ""


def _merge_cleared_all_rows(table_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Rule priority:
    For the same specialty + journal + month, if Clinical Trial + Meta analysis + Systematic Review
    are all cleared, replace those rows with one cleared row labeled Study type = All.
    """
    required = {"clinical_trial", "meta_analysis", "systematic_review"}
    grouped: dict[tuple[str, str, str], list[tuple[int, dict[str, object], str]]] = {}

    for idx, row in enumerate(table_rows):
        if (row.get("Status") or "") != "Cleared":
            continue
        canonical = _canonical_ledger_study_type(str(row.get("Study type") or ""))
        if canonical not in required:
            continue
        specialty_key = str(row.get("Specialty") or "").strip().lower()
        journal_key = str(row.get("Journal") or "").strip().lower()
        ym_key = str(row.get("_ym_raw") or "").strip()
        grouped.setdefault((specialty_key, journal_key, ym_key), []).append((idx, row, canonical))

    to_remove: set[int] = set()
    merged_rows: list[dict[str, object]] = []
    for _, members in grouped.items():
        present = {canonical for _, _, canonical in members}
        if not required.issubset(present):
            continue

        picked: dict[str, tuple[int, dict[str, object]]] = {}
        for idx, row, canonical in members:
            picked.setdefault(canonical, (idx, row))

        chosen = [picked["clinical_trial"], picked["meta_analysis"], picked["systematic_review"]]
        chosen_rows = [row for _, row in chosen]
        to_remove.update(idx for idx, _ in chosen)

        rep = chosen_rows[0]
        visible_total = sum(_safe_int(r.get("_visible_matches"), 0) for r in chosen_rows)
        match_total = sum(_safe_int(r.get("_total_matches"), 0) for r in chosen_rows)
        merged_rows.append(
            {
                "Specialty": rep.get("Specialty") or "—",
                "Journal": rep.get("Journal") or "—",
                "Study type": "All",
                "Month": rep.get("Month") or "—",
                "Status": "Cleared",
                "Visible / Total": f"{visible_total}/{match_total}",
                "_status_rank": rep.get("_status_rank"),
                "_ym_sort": rep.get("_ym_sort"),
                "_ym_raw": rep.get("_ym_raw"),
                "_visible_matches": visible_total,
                "_total_matches": match_total,
            }
        )

    if not merged_rows:
        return table_rows

    out: list[dict[str, object]] = []
    for idx, row in enumerate(table_rows):
        if idx in to_remove:
            continue
        out.append(row)
    out.extend(merged_rows)
    return out


def _month_idx_from_ym(ym: tuple[int, int]) -> int:
    return int(ym[0]) * 12 + int(ym[1])


def _ym_from_month_idx(month_idx: int) -> tuple[int, int]:
    yy = int(month_idx) // 12
    mm = int(month_idx) % 12
    if mm == 0:
        yy -= 1
        mm = 12
    return (yy, mm)


def _month_label_from_month_idx(month_idx: int) -> str:
    yy, mm = _ym_from_month_idx(month_idx)
    return f"{calendar.month_name[int(mm)]} {int(yy)}"


def _month_ranges(month_values: set[int]) -> list[tuple[int, int]]:
    if not month_values:
        return []
    vals = sorted(int(v) for v in month_values)
    out: list[tuple[int, int]] = []
    start = vals[0]
    end = vals[0]
    for cur in vals[1:]:
        if cur == (end + 1):
            end = cur
            continue
        out.append((start, end))
        start = cur
        end = cur
    out.append((start, end))
    return out


def _month_range_label(start_month_idx: int, end_month_idx: int, latest_clearable_month_idx: int | None) -> str:
    start_label = _month_label_from_month_idx(start_month_idx)
    if int(start_month_idx) == int(end_month_idx):
        return start_label
    if latest_clearable_month_idx is not None and int(end_month_idx) == int(latest_clearable_month_idx):
        return f"{start_label} to present"
    end_label = _month_label_from_month_idx(end_month_idx)
    return f"{start_label} to {end_label}"


def _configured_journal_keys_for_specialty(specialty_key: str) -> set[str]:
    skey = (specialty_key or "").strip().lower()
    if not skey:
        return set()
    for specialty, journals in SPECIALTY_JOURNAL_TERMS.items():
        if skey == (specialty or "").strip().lower():
            return {
                (label or "").strip().lower()
                for label in journals
                if (label or "").strip()
            }
    return set()


def _merge_consecutive_cleared_all_rows(table_rows: list[dict[str, object]], today) -> list[dict[str, object]]:
    """
    Consolidate cleared Study type=All rows in two passes:
    1) Merge consecutive months per specialty + journal.
    2) Add specialty-level "All journals" ranges where all configured journals in the
       specialty are cleared for the same months.

    Journal-level rows are hidden only when their full month range is already covered by
    the specialty-level "All journals" range.
    """
    passthrough_rows: list[dict[str, object]] = []
    month_rows: list[dict[str, object]] = []

    for row in table_rows:
        if (row.get("Status") or "") != "Cleared":
            passthrough_rows.append(row)
            continue
        if str(row.get("Study type") or "").strip().lower() != "all":
            passthrough_rows.append(row)
            continue
        ym = _parse_year_month_key(str(row.get("_ym_raw") or ""))
        if ym is None:
            passthrough_rows.append(row)
            continue
        month_rows.append(row)

    if not month_rows:
        return table_rows

    latest_clearable = _latest_clearable_year_month(today=today)
    latest_clearable_month_idx = (
        _month_idx_from_ym(latest_clearable) if latest_clearable is not None else None
    )

    spec_label_by_key: dict[str, str] = {}
    journal_label_by_key: dict[tuple[str, str], str] = {}
    journal_months: dict[tuple[str, str], set[int]] = {}
    journal_month_totals: dict[tuple[str, str, int], tuple[int, int]] = {}

    for row in month_rows:
        ym = _parse_year_month_key(str(row.get("_ym_raw") or ""))
        if ym is None:
            continue
        month_idx = _month_idx_from_ym(ym)
        spec_label = str(row.get("Specialty") or "—").strip() or "—"
        journal_label = str(row.get("Journal") or "—").strip() or "—"
        spec_key = spec_label.lower()
        journal_key = journal_label.lower()

        spec_label_by_key.setdefault(spec_key, spec_label)
        journal_label_by_key.setdefault((spec_key, journal_key), journal_label)
        journal_months.setdefault((spec_key, journal_key), set()).add(month_idx)

        k = (spec_key, journal_key, month_idx)
        prev_visible, prev_total = journal_month_totals.get(k, (0, 0))
        journal_month_totals[k] = (
            int(prev_visible) + _safe_int(row.get("_visible_matches"), 0),
            int(prev_total) + _safe_int(row.get("_total_matches"), 0),
        )

    specialty_keys = {spec for spec, _ in journal_months}
    specialty_all_months: dict[str, set[int]] = {}
    specialty_required_journals: dict[str, set[str]] = {}

    for spec_key in specialty_keys:
        present_journals = {
            journal_key
            for s_key, journal_key in journal_months
            if s_key == spec_key
        }
        configured_journals = _configured_journal_keys_for_specialty(spec_key)
        required_journals = configured_journals if configured_journals else present_journals
        specialty_required_journals[spec_key] = set(required_journals)

        if not required_journals:
            specialty_all_months[spec_key] = set()
            continue

        common: set[int] | None = None
        for journal_key in required_journals:
            months = set(journal_months.get((spec_key, journal_key), set()))
            if common is None:
                common = months
            else:
                common = common.intersection(months)
        specialty_all_months[spec_key] = set(common or set())

    merged_rows: list[dict[str, object]] = []

    for (spec_key, journal_key), month_set in journal_months.items():
        month_ranges = _month_ranges(month_set)
        specialty_month_set = specialty_all_months.get(spec_key, set())
        for start_month_idx, end_month_idx in month_ranges:
            fully_covered = all(
                int(mm) in specialty_month_set
                for mm in range(int(start_month_idx), int(end_month_idx) + 1)
            )
            if fully_covered:
                continue

            visible_total = 0
            match_total = 0
            for mm in range(int(start_month_idx), int(end_month_idx) + 1):
                vis, tot = journal_month_totals.get((spec_key, journal_key, int(mm)), (0, 0))
                visible_total += int(vis)
                match_total += int(tot)

            end_ym = _ym_from_month_idx(end_month_idx)
            month_label = _month_range_label(
                start_month_idx=start_month_idx,
                end_month_idx=end_month_idx,
                latest_clearable_month_idx=latest_clearable_month_idx,
            )
            merged_rows.append(
                {
                    "Specialty": spec_label_by_key.get(spec_key, "—"),
                    "Journal": journal_label_by_key.get((spec_key, journal_key), "—"),
                    "Study type": "All",
                    "Month": month_label,
                    "Status": "Cleared",
                    "Visible / Total": f"{visible_total}/{match_total}",
                    "_status_rank": 2,
                    "_ym_sort": int(end_ym[0]) * 100 + int(end_ym[1]),
                    "_ym_raw": f"{int(end_ym[0])}-{int(end_ym[1]):02d}",
                    "_visible_matches": visible_total,
                    "_total_matches": match_total,
                }
            )

    for spec_key, common_months in specialty_all_months.items():
        required_journals = specialty_required_journals.get(spec_key, set())
        if not common_months or not required_journals:
            continue
        month_ranges = _month_ranges(common_months)
        for start_month_idx, end_month_idx in month_ranges:
            visible_total = 0
            match_total = 0
            for mm in range(int(start_month_idx), int(end_month_idx) + 1):
                for journal_key in required_journals:
                    vis, tot = journal_month_totals.get((spec_key, journal_key, int(mm)), (0, 0))
                    visible_total += int(vis)
                    match_total += int(tot)

            end_ym = _ym_from_month_idx(end_month_idx)
            month_label = _month_range_label(
                start_month_idx=start_month_idx,
                end_month_idx=end_month_idx,
                latest_clearable_month_idx=latest_clearable_month_idx,
            )
            merged_rows.append(
                {
                    "Specialty": spec_label_by_key.get(spec_key, "—"),
                    "Journal": "All journals",
                    "Study type": "All",
                    "Month": month_label,
                    "Status": "Cleared",
                    "Visible / Total": f"{visible_total}/{match_total}",
                    "_status_rank": 2,
                    "_ym_sort": int(end_ym[0]) * 100 + int(end_ym[1]),
                    "_ym_raw": f"{int(end_ym[0])}-{int(end_ym[1]):02d}",
                    "_visible_matches": visible_total,
                    "_total_matches": match_total,
                }
            )

    out = list(passthrough_rows)
    out.extend(merged_rows)
    return out


def _render_search_ledger() -> None:
    st.markdown("##### Ledger")
    st.caption("Entries are eligible to clear 30 days after month-end.")
    today = datetime.now(timezone.utc).date()
    rows = list_search_pubmed_ledger()
    if not rows:
        st.caption("No ledger entries yet.")
        return

    table_rows: list[dict[str, object]] = []
    for r in rows:
        ym_raw = (r.get("year_month") or "").strip()
        if _is_future_year_month(ym_raw, today=today):
            continue
        ym_parts = _parse_year_month_parts(ym_raw)
        ym_key = _parse_year_month_key(ym_raw)
        clearable = _is_year_month_clearable(ym_raw, today=today)

        try:
            total_matches = int(r.get("total_matches") or 0)
        except Exception:
            total_matches = 0
        try:
            visible_matches = int(r.get("visible_matches") or 0)
        except Exception:
            visible_matches = 0
        is_cleared = (r.get("is_cleared") or "0") == "1"
        is_verified = (r.get("is_verified") or "0") == "1"

        if is_cleared and clearable:
            status = "Cleared"
            status_rank = 2
        elif not is_verified:
            status = "Unverified"
            status_rank = 3
        elif not clearable:
            status = "Not clearable yet"
            status_rank = 0
        elif visible_matches > 0:
            status = "Not cleared"
            status_rank = 1
        else:
            status = "Ready to clear"
            status_rank = 1

        if ym_key is not None:
            ym_sort = int(ym_key[0]) * 100 + int(ym_key[1])
        else:
            ym_sort = -1

        year = (ym_parts.get("year") or "").strip()
        month = (ym_parts.get("month") or "").strip()
        if month and month != "—" and year and year != "—":
            month_label = f"{month} {year}"
        else:
            month_label = ym_raw or "—"

        table_rows.append(
            {
                "Specialty": (r.get("specialty_label") or "").strip()
                or _infer_specialty_from_journal_label((r.get("journal_label") or "").strip()),
                "Journal": (r.get("journal_label") or "").strip() or "—",
                "Study type": (r.get("study_type_label") or "").strip() or "—",
                "Month": month_label,
                "Status": status,
                "Visible / Total": f"{visible_matches}/{total_matches}",
                "_ym_raw": ym_raw,
                "_total_matches": total_matches,
                "_visible_matches": visible_matches,
                "_status_rank": status_rank,
                "_ym_sort": ym_sort,
            }
        )

    table_rows = _merge_cleared_all_rows(table_rows)
    table_rows = _merge_consecutive_cleared_all_rows(table_rows, today=today)

    table_rows = sorted(
        table_rows,
        key=lambda x: (
            -_safe_int(x.get("_ym_sort"), -1),
            _safe_int(x.get("_status_rank"), 99),
            str(x.get("Specialty") or "").lower(),
            str(x.get("Journal") or "").lower(),
            str(x.get("Study type") or "").lower(),
        ),
    )

    display_rows = [r for r in table_rows if (r.get("Status") or "") == "Cleared"]

    if not display_rows:
        st.caption("No ledger entries to display.")
        return

    cols = ["Specialty", "Journal", "Month"]
    df = pd.DataFrame(display_rows)
    if not df.empty:
        df = df[cols]
    styled = df.style.map(_specialty_cell_style, subset=["Specialty"])
    st.dataframe(styled, hide_index=True, width="stretch")


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
        for k in ["search_pubmed_groups", "search_pubmed_range"]:
            st.session_state.pop(k, None)
        st.rerun()

    if search_clicked:
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
        return

    groups = [g for g in (st.session_state.get("search_pubmed_groups") or []) if isinstance(g, dict)]
    rng = st.session_state.get("search_pubmed_range") or {}
    ym_key = (rng.get("year_month") or "").strip()
    ym_label = (rng.get("year_month_label") or "").strip()
    is_future = _is_future_year_month(ym_key, today=today)
    is_time_clearable = _is_year_month_clearable(ym_key, today=today)

    grand_total = sum(
        len([r for r in (g.get("rows") or []) if isinstance(r, dict)]) for g in groups
    )
    header_bits = []
    if ym_label:
        header_bits.append(f"Month: {ym_label}")
    header_bits.append(f"{len(groups)} journals searched")
    header_bits.append(f"{grand_total} matches")
    st.caption(" | ".join(header_bits))

    any_visible = False
    current_specialty: str | None = None
    for gi, g in enumerate(groups):
        specialty_label = (g.get("specialty") or "").strip()
        journal_label = (g.get("journal") or "").strip()
        # raw_count is PubMed's esearch match count (includes items later dropped
        # for lacking a real abstract); used only for the >200 truncation check.
        # fetched_count is the accurate number of real-research articles we hold.
        raw_count = int(g.get("total_count") or 0)
        rows = [r for r in (g.get("rows") or []) if isinstance(r, dict)]
        fetched_count = len(rows)
        visible_rows = _filter_search_pubmed_rows(rows)
        visible_count = len(visible_rows)
        hidden_count = max(0, fetched_count - visible_count)
        is_verified = raw_count <= int(SEARCH_FETCH_LIMIT)
        is_cleared = bool(visible_count == 0 and is_verified and is_time_clearable)

        if not is_future:
            upsert_search_pubmed_ledger(
                year_month=ym_key,
                specialty_label=specialty_label,
                journal_label=journal_label,
                study_type_label=LEDGER_STUDY_TYPE_LABEL,
                total_matches=fetched_count,
                visible_matches=visible_count,
                hidden_matches=hidden_count,
                is_cleared=is_cleared,
                is_verified=is_verified,
            )

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
                pub_types = [
                    str(t).strip()
                    for t in (r.get("pub_types") or [])
                    if str(t).strip() and str(t).strip().lower() != "journal article"
                ]
                if pub_types:
                    st.caption(" · ".join(pub_types))
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
                            st.rerun()
                    with b2:
                        if st.button(
                            "Open abstract",
                            key=f"search_pubmed_open_abstract_{gi}_{pmid}",
                            use_container_width=True,
                        ):
                            st.query_params["open_abs_pmid"] = pmid
                            st.rerun()

    if not any_visible:
        st.info("No visible results across any journal for this month.")

    st.divider()
    _render_search_ledger()
