"""Dashboard — visual analytics for saved abstracts and review activity."""

import re
from collections import Counter

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import (
    _connect_db,
    dashboard_hidden_per_journal,
    dashboard_saved_per_journal,
    dashboard_saved_specialties,
    dashboard_study_design_distribution,
)

# ── colour palette ──────────────────────────────────────────────────
_PALETTE = px.colors.qualitative.Set2
_PLOTLY_TEMPLATE = "plotly_white"


# ── specialty explosion helper ──────────────────────────────────────
def _explode_specialties(raw_rows: list[dict]) -> Counter:
    counts: Counter = Counter()
    for row in raw_rows:
        raw = (row.get("specialty") or "").strip()
        if not raw:
            counts["Unspecified"] += 1
            continue
        parts = re.split(r"[,;\|\n]+", raw)
        for p in parts:
            s = p.strip()
            if s:
                counts[s] += 1
    return counts


# ── study design grouping ──────────────────────────────────────────
def _group_study_designs(raw_rows: list[dict]) -> Counter:
    counts: Counter = Counter()
    for row in raw_rows:
        raw = (row.get("study_design") or "").strip().lower()
        if not raw:
            counts["Observational studies"] += 1
            continue
        if "systematic review" in raw or "meta-analysis" in raw:
            counts["Systematic reviews & meta-analyses"] += 1
        elif "randomized" in raw:
            counts["RCTs"] += 1
        else:
            counts["Observational studies"] += 1
    return counts


# ── render ─────────────────────────────────────────────────────────
def render() -> None:
    st.title("Dashboard")

    # ── fetch data ──
    saved_per_journal = dashboard_saved_per_journal()
    hidden_per_journal = dashboard_hidden_per_journal()
    specialty_rows = dashboard_saved_specialties()
    study_design_rows = dashboard_study_design_distribution()

    total_saved = sum(r["count"] for r in saved_per_journal)
    total_hidden = sum(r["count"] for r in hidden_per_journal)
    total_reviewed = total_saved + total_hidden
    save_rate = (total_saved / total_reviewed * 100) if total_reviewed else 0
    n_journals = len([r for r in saved_per_journal if r["count"] > 0])
    specialty_counts = _explode_specialties(specialty_rows)

    # ════════════════════════════════════════════════════════════════
    # A. KPI METRICS
    # ════════════════════════════════════════════════════════════════
    st.markdown("### Overview")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Papers saved", f"{total_saved:,}")
    k2.metric("Papers reviewed", f"{total_reviewed:,}")
    k3.metric("Save rate", f"{save_rate:.1f}%")
    k4.metric("Journals", str(n_journals))

    st.divider()

    # ════════════════════════════════════════════════════════════════
    # B. TOP JOURNALS TABLE
    # ════════════════════════════════════════════════════════════════
    _render_top_journals_table()

    st.divider()

    # ════════════════════════════════════════════════════════════════
    # E. SPECIALTY AFFINITY (treemap)
    # ════════════════════════════════════════════════════════════════
    st.markdown("### Specialty affinity")
    st.caption("Multi-specialty papers count toward each tagged specialty")

    if specialty_counts:
        spec_sorted = specialty_counts.most_common()
        spec_names = [s[0] for s in spec_sorted]
        spec_vals = [s[1] for s in spec_sorted]

        fig4 = go.Figure(go.Treemap(
            labels=spec_names,
            parents=[""] * len(spec_names),
            values=spec_vals,
            textinfo="label+value",
            marker=dict(
                colors=spec_vals,
                colorscale="Blues",
                showscale=False,
            ),
            hovertemplate="<b>%{label}</b><br>Papers: %{value}<extra></extra>",
        ))
        fig4.update_layout(
            template=_PLOTLY_TEMPLATE,
            height=500,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig4, width="stretch")

    st.divider()

    # ════════════════════════════════════════════════════════════════
    # F. STUDY DESIGN DISTRIBUTION (donut)
    # ════════════════════════════════════════════════════════════════
    col_design, col_design_table = st.columns([3, 2])

    with col_design:
        st.markdown("### Study design distribution")
        grouped_designs = _group_study_designs(study_design_rows)
        if grouped_designs:
            design_sorted = grouped_designs.most_common()
            labels = [d[0] for d in design_sorted]
            values = [d[1] for d in design_sorted]

            fig5 = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.45,
                textinfo="percent+label",
                textposition="outside",
                marker=dict(colors=_PALETTE * 5),
                hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percent: %{percent}<extra></extra>",
            ))
            fig5.update_layout(
                template=_PLOTLY_TEMPLATE,
                height=450,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig5, width="stretch")

    with col_design_table:
        st.markdown("### Breakdown")
        if grouped_designs:
            design_sorted = grouped_designs.most_common()
            for label, count in design_sorted:
                pct = count / total_saved * 100 if total_saved else 0
                st.markdown(f"**{label}** — {count} ({pct:.1f}%)")


# ── Top journals table ─────────────────────────────────────────────

# Mapping: Search PubMed display label → DB journal name (lowercase).
# DB names come from PubMed XML <Journal><Title> and can differ from display labels.
_LABEL_TO_DB_JOURNAL: dict[str, str] = {
    "NEJM": "the new england journal of medicine",
    "JAMA": "jama",
    "Lancet": "lancet (london, england)",
    "BMJ": "bmj (clinical research ed.)",
    "Nat Med": "nature medicine",
    "AIM": "annals of internal medicine",
    "JAMA Internal Medicine": "jama internal medicine",
    "JGIM": "journal of general internal medicine",
    "Journal of Hospital Medicine": "journal of hospital medicine",
    "American Journal of Medicine": "the american journal of medicine",
    "Cochrane Systematic Reviews": "the cochrane database of systematic reviews",
    "JAMA Neurology": "jama neurology",
    "Lancet Neurology": "the lancet. neurology",
    "Stroke": "stroke",
    "Intensive Care Medicine": "intensive care medicine",
    "Critical Care": "critical care (london, england)",
    "Anesthesiology": "anesthesiology",
    "JAMA Cardiology": "jama cardiology",
    "Journal of the American College of Cardiology": "journal of the american college of cardiology",
    "European Heart Journal": "european heart journal",
    "Circulation": "circulation",
    "Lancet Infectious Diseases": "the lancet. infectious diseases",
    "Clinical Infectious Diseases": "clinical infectious diseases : an official publication of the infectious diseases society of america",
    "Lancet Respiratory Medicine": "the lancet. respiratory medicine",
    "American Journal of Respiratory and Critical Care Medicine": "american journal of respiratory and critical care medicine",
    "CHEST": "chest",
    "JAMA Surgery": "jama surgery",
    "Annals of Surgery": "annals of surgery",
    "JAMA Psychiatry": "jama psychiatry",
    "Lancet Psychiatry": "the lancet. psychiatry",
    "World Psychiatry": "world psychiatry",
    "Lancet Gastroenterology & Hepatology": "the lancet. gastroenterology & hepatology",
    "Gastroenterology": "gastroenterology",
    "Gut": "gut",
    "The American Journal of Gastroenterology": "the american journal of gastroenterology",
    "Annals of Emergency Medicine": "annals of emergency medicine",
    "Resuscitation": "resuscitation",
    "Journal of the American Society of Nephrology": "journal of the american society of nephrology : jasn",
    "Kidney International": "kidney international",
    "American Journal of Kidney Diseases": "american journal of kidney diseases : the official journal of the national kidney foundation",
    "Lancet Diabetes & Endocrinology": "the lancet. diabetes & endocrinology",
    "Diabetes Care": "diabetes care",
    "Journal of Clinical Endocrinology & Metabolism": "the journal of clinical endocrinology and metabolism",
    "Lancet Haematology": "the lancet. haematology",
    "Blood": "blood",
    "JAMA Oncology": "jama oncology",
    "Lancet Oncology": "the lancet. oncology",
    "Journal of Clinical Oncology": "journal of clinical oncology : official journal of the american society of clinical oncology",
    "Lancet Rheumatology": "the lancet. rheumatology",
    "Annals of the Rheumatic Diseases": "annals of the rheumatic diseases",
    "Hepatology": "hepatology (baltimore, md.)",
    "Journal of Hepatology": "journal of hepatology",
    "JAMA Network Open": "jama network open",
    "Journal of Pain and Symptom Management": "journal of pain and symptom management",
}


def _get_journal_counts() -> dict[str, tuple[int, int]]:
    """Return {display_label: (saved_count, hidden_count)} for Search PubMed journals."""
    with _connect_db() as conn:
        saved_rows = conn.execute(
            "SELECT LOWER(TRIM(journal)) AS j, COUNT(*) AS cnt FROM abstracts "
            "WHERE journal IS NOT NULL GROUP BY j;"
        ).fetchall()
        hidden_rows = conn.execute(
            "SELECT LOWER(TRIM(journal)) AS j, COUNT(*) AS cnt FROM hidden_pubmed_pmids "
            "WHERE journal IS NOT NULL GROUP BY j;"
        ).fetchall()

    saved_by_db: dict[str, int] = {r["j"]: int(r["cnt"]) for r in saved_rows}
    hidden_by_db: dict[str, int] = {r["j"]: int(r["cnt"]) for r in hidden_rows}

    result: dict[str, tuple[int, int]] = {}
    for label, db_key in _LABEL_TO_DB_JOURNAL.items():
        s = saved_by_db.get(db_key, 0)
        # Hidden articles may be stored under the full DB name OR the short
        # display label (the Search PubMed page historically stored the label).
        # Sum both to avoid undercounting.
        h = hidden_by_db.get(db_key, 0)
        label_key = label.lower().strip()
        if label_key != db_key:
            h += hidden_by_db.get(label_key, 0)
        result[label] = (s, h)
    return result


# Minimum reviewed articles for a journal to qualify on the save-rate ranking,
# so a single saved paper can't produce a misleading 100% rate.
_RATE_MIN_REVIEWED = 10


def _render_top_journals_table() -> None:
    st.markdown("### Top journals")
    st.caption(
        "Journals in the top 10 by papers saved or by save rate "
        f"(rate ranked among journals with at least {_RATE_MIN_REVIEWED} reviewed). "
        "Sorted by papers saved."
    )

    counts = _get_journal_counts()
    journals: list[dict] = []
    for label, (saved, hidden) in counts.items():
        reviewed = saved + hidden
        rate = (saved / reviewed) if reviewed > 0 else 0.0
        journals.append({
            "label": label,
            "saved": saved,
            "reviewed": reviewed,
            "rate": rate,
        })

    # Top 10 by papers saved (ignore journals with nothing saved).
    by_saved = sorted(journals, key=lambda j: (j["saved"], j["rate"]), reverse=True)
    top_saved = {j["label"] for j in by_saved[:10] if j["saved"] > 0}

    # Top 10 by save rate, among journals with enough reviewed articles.
    eligible = [j for j in journals if j["reviewed"] >= _RATE_MIN_REVIEWED]
    by_rate = sorted(eligible, key=lambda j: (j["rate"], j["saved"]), reverse=True)
    top_rate = {j["label"] for j in by_rate[:10]}

    selected = [j for j in journals if j["label"] in (top_saved | top_rate)]
    selected.sort(key=lambda j: (j["saved"], j["rate"]), reverse=True)

    if not selected:
        st.info("No saved papers yet.")
        return

    rows_md = []
    for j in selected:
        rate_str = f"{j['rate'] * 100:.1f}%" if j["reviewed"] > 0 else "—"
        rows_md.append(f"| {j['label']} | {j['saved']} | {j['reviewed']} | {rate_str} |")
    table = (
        "| Journal | Saved | Reviewed | Save rate |\n"
        "|:--------|------:|---------:|----------:|\n"
        + "\n".join(rows_md)
    )
    st.markdown(table)

