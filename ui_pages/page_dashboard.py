"""Dashboard — visual analytics for saved abstracts and review activity."""

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

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
_PRIMARY = "#4C78A8"
_ACCENT = "#F58518"
_PLOTLY_TEMPLATE = "plotly_white"

# Consistent journal name normalization
_JOURNAL_SHORT: Dict[str, str] = {
    "The New England journal of medicine": "NEJM",
    "Lancet (London, England)": "Lancet",
    "BMJ (Clinical research ed.)": "BMJ",
    "Critical care (London, England)": "Critical Care",
    "The Cochrane database of systematic reviews": "Cochrane",
    "Clinical infectious diseases : an official publication of the Infectious Diseases Society of America": "Clin Infect Dis",
    "Journal of clinical oncology : official journal of the American Society of Clinical Oncology": "J Clin Oncol",
    "The Lancet. Oncology": "Lancet Oncol",
    "The Lancet. Infectious diseases": "Lancet Infect Dis",
    "The Lancet. Respiratory medicine": "Lancet Respir Med",
    "The Lancet. Gastroenterology & hepatology": "Lancet Gastro Hepatol",
    "The Lancet. Psychiatry": "Lancet Psychiatry",
    "The Lancet. Haematology": "Lancet Haematol",
    "The Lancet. Rheumatology": "Lancet Rheumatol",
    "The Lancet. Diabetes & endocrinology": "Lancet Diabetes Endocrinol",
    "The Journal of clinical endocrinology and metabolism": "J Clin Endocrinol Metab",
    "Journal of the American College of Cardiology": "JACC",
    "European heart journal": "Eur Heart J",
    "Annals of internal medicine": "Ann Intern Med",
    "JAMA internal medicine": "JAMA Intern Med",
    "JAMA network open": "JAMA Netw Open",
    "JAMA neurology": "JAMA Neurol",
    "JAMA cardiology": "JAMA Cardiol",
    "JAMA surgery": "JAMA Surg",
    "JAMA psychiatry": "JAMA Psychiatry",
    "JAMA oncology": "JAMA Oncol",
    "Intensive care medicine": "Intensive Care Med",
    "Annals of emergency medicine": "Ann Emerg Med",
    "American journal of respiratory and critical care medicine": "Am J Respir Crit Care Med",
    "Journal of the American Society of Nephrology : JASN": "JASN",
    "Kidney international": "Kidney Int",
    "Journal of hepatology": "J Hepatol",
    "Annals of surgery": "Ann Surg",
    "Annals of the rheumatic diseases": "Ann Rheum Dis",
    "Journal of general internal medicine": "JGIM",
    "Journal of hospital medicine": "J Hosp Med",
    "American journal of medicine (The)": "Am J Med",
    "Nature medicine": "Nat Med",
    "Diabetes care": "Diabetes Care",
    "Journal of pain and symptom management": "J Pain Symptom Manage",
    "World psychiatry : official journal of the World Psychiatric Association (WPA)": "World Psychiatry",
}


def _short_journal(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return "Unknown"
    low = s.lower()
    for long, short in _JOURNAL_SHORT.items():
        if long.lower() == low:
            return short
    # Fallback: title-case, truncate
    if len(s) > 30:
        return s[:27] + "..."
    return s


# ── specialty explosion helper ──────────────────────────────────────
def _explode_specialties(raw_rows: List[Dict]) -> Counter:
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
def _group_study_designs(raw_rows: List[Dict]) -> Counter:
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
    # B. SAVED PAPERS BY JOURNAL (horizontal bar)
    # ════════════════════════════════════════════════════════════════
    st.markdown("### Saved papers by journal")
    top_n = 20
    top_saved = saved_per_journal[:top_n]
    if top_saved:
        journals = [_short_journal(r["journal"]) for r in reversed(top_saved)]
        counts = [r["count"] for r in reversed(top_saved)]
        fig = go.Figure(
            go.Bar(
                x=counts,
                y=journals,
                orientation="h",
                marker_color=_PRIMARY,
                text=counts,
                textposition="outside",
            )
        )
        fig.update_layout(
            template=_PLOTLY_TEMPLATE,
            height=max(400, len(top_saved) * 28),
            margin=dict(l=10, r=40, t=10, b=10),
            xaxis_title="Papers saved",
            yaxis=dict(tickfont=dict(size=12)),
        )
        st.plotly_chart(fig, width="stretch")

    st.divider()

    # ════════════════════════════════════════════════════════════════
    # D. SAVE RATE BY JOURNAL (bar chart)
    # ════════════════════════════════════════════════════════════════
    hidden_map: Dict[str, int] = {}
    for r in hidden_per_journal:
        key = _short_journal(r["journal"])
        hidden_map[key] = hidden_map.get(key, 0) + int(r["count"])

    journal_total_reviewed: Dict[str, int] = {}
    saved_map: Dict[str, int] = {}
    for r in saved_per_journal:
        key = _short_journal(r["journal"])
        saved_map[key] = saved_map.get(key, 0) + int(r["count"])

    all_journals = set(saved_map.keys()) | set(hidden_map.keys())
    for j in all_journals:
        journal_total_reviewed[j] = saved_map.get(j, 0) + hidden_map.get(j, 0)
    st.markdown("### Save rate by journal")
    st.caption("Among journals with at least 10 reviewed articles")

    rate_data = []
    for j in all_journals:
        s = saved_map.get(j, 0)
        t = journal_total_reviewed.get(j, 0)
        if t >= 10:
            rate_data.append({"journal": j, "rate": s / t * 100, "saved": s, "total": t})

    rate_data.sort(key=lambda x: x["rate"], reverse=True)
    top_rates = rate_data[:20]

    if top_rates:
        fig3 = go.Figure(
            go.Bar(
                x=[r["rate"] for r in reversed(top_rates)],
                y=[r["journal"] for r in reversed(top_rates)],
                orientation="h",
                marker_color=[_ACCENT if r["rate"] >= save_rate else "#93B7D6" for r in reversed(top_rates)],
                text=[f'{r["rate"]:.0f}% ({r["saved"]}/{r["total"]})' for r in reversed(top_rates)],
                textposition="outside",
            )
        )
        fig3.update_layout(
            template=_PLOTLY_TEMPLATE,
            height=max(350, len(top_rates) * 28),
            margin=dict(l=10, r=80, t=10, b=10),
            xaxis_title="Save rate (%)",
            xaxis=dict(range=[0, max(r["rate"] for r in top_rates) * 1.3]),
            yaxis=dict(tickfont=dict(size=12)),
        )
        st.plotly_chart(fig3, width="stretch")

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

    st.divider()

    # ════════════════════════════════════════════════════════════════
    # G. JOURNAL TIERS
    # ════════════════════════════════════════════════════════════════
    _render_journal_tiers()


# ── Journal tier system ────────────────────────────────────────────

# Mapping: Search PubMed display label → DB journal name (lowercase).
# DB names come from PubMed XML <Journal><Title> and can differ from display labels.
_LABEL_TO_DB_JOURNAL: Dict[str, str] = {
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


def _get_journal_counts() -> Dict[str, Tuple[int, int]]:
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

    saved_by_db: Dict[str, int] = {r["j"]: int(r["cnt"]) for r in saved_rows}
    hidden_by_db: Dict[str, int] = {r["j"]: int(r["cnt"]) for r in hidden_rows}

    result: Dict[str, Tuple[int, int]] = {}
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


def _compute_journal_tiers() -> Optional[Dict[int, List[Dict]]]:
    """Compute 5 tiers of journals using the W/X/Y/Z optimization algorithm.

    Returns {1: [...], 2: [...], 3: [...], 4: [...], 5: [...]} where each
    value is a list of dicts with keys: label, saved, reviewed, rate.
    """
    counts = _get_journal_counts()
    if not counts:
        return None

    N = len(counts)
    target = N / 5.0

    # Build journal data
    journals: List[Dict] = []
    for label, (saved, hidden) in counts.items():
        reviewed = saved + hidden
        rate = (saved / reviewed) if reviewed > 0 else 0.0
        journals.append({
            "label": label,
            "saved": saved,
            "reviewed": reviewed,
            "rate": rate,
        })

    # List A: ranked by saved count desc, tiebreaker: higher rate
    list_a = sorted(journals, key=lambda j: (j["saved"], j["rate"]), reverse=True)
    # List B: ranked by save rate desc, tiebreaker: higher saved count
    list_b = sorted(journals, key=lambda j: (j["rate"], j["saved"]), reverse=True)

    # Assign ranks (0-indexed)
    rank_a: Dict[str, int] = {j["label"]: i for i, j in enumerate(list_a)}
    rank_b: Dict[str, int] = {j["label"]: i for i, j in enumerate(list_b)}

    labels = [j["label"] for j in journals]
    label_set = set(labels)

    # For each journal, store (rank_a, rank_b)
    pairs = {la: (rank_a[la], rank_b[la]) for la in labels}

    # Precompute 2D prefix sums for fast overlap counting.
    # Grid cell [ra][rb] = 1 if a journal has that (rank_a, rank_b) pair.
    grid = [[0] * (N + 2) for _ in range(N + 2)]
    for la in labels:
        ra, rb = pairs[la]
        grid[ra + 1][rb + 1] = 1
    # prefix[i][j] = count of journals with rank_a < i AND rank_b < j
    prefix = [[0] * (N + 2) for _ in range(N + 2)]
    for i in range(1, N + 2):
        for j2 in range(1, N + 2):
            prefix[i][j2] = (
                grid[i][j2]
                + prefix[i - 1][j2]
                + prefix[i][j2 - 1]
                - prefix[i - 1][j2 - 1]
            )

    def _count_rect(ra_lo: int, ra_hi: int, rb_lo: int, rb_hi: int) -> int:
        """Count journals with ra_lo <= rank_a < ra_hi AND rb_lo <= rank_b < rb_hi."""
        if ra_lo >= ra_hi or rb_lo >= rb_hi:
            return 0
        return (
            prefix[ra_hi][rb_hi]
            - prefix[ra_lo][rb_hi]
            - prefix[ra_hi][rb_lo]
            + prefix[ra_lo][rb_lo]
        )

    best_score = float("inf")
    best_wxyz: Tuple[int, int, int, int] = (0, 0, 0, 0)

    for W in range(0, N + 1):
        for X in range(0, N + 1):
            # tier1 = rank_a < W AND rank_b < X
            t1 = _count_rect(0, W, 0, X)
            top_union = W + X - t1
            t2 = top_union - t1

            for Y in range(0, N - W + 1):
                for Z in range(0, N - X + 1):
                    # tier5 = rank_a >= N-Y AND rank_b >= N-Z
                    t5 = _count_rect(N - Y, N, N - Z, N)
                    bot_union = Y + Z - t5
                    t4 = bot_union - t5

                    # Cross-dimension overlap:
                    # journals in top (rank_a<W OR rank_b<X) AND
                    #   bot (rank_a>=N-Y OR rank_b>=N-Z)
                    # Since W+Y<=N → rank_a<W and rank_a>=N-Y are disjoint.
                    # Since X+Z<=N → rank_b<X and rank_b>=N-Z are disjoint.
                    # Overlap = (rank_a<W AND rank_b>=N-Z)
                    #         + (rank_b<X AND rank_a>=N-Y)
                    cross = (
                        _count_rect(0, W, N - Z, N)
                        + _count_rect(N - Y, N, 0, X)
                    )
                    if cross > 0:
                        continue

                    t3 = N - top_union - bot_union
                    if t3 < 0:
                        continue

                    sizes = [t1, t2, t3, t4, t5]
                    score = sum((s - target) ** 2 for s in sizes)

                    if score < best_score:
                        best_score = score
                        best_wxyz = (W, X, Y, Z)

    W, X, Y, Z = best_wxyz
    top_a = {la for la in labels if rank_a[la] < W}
    top_b = {la for la in labels if rank_b[la] < X}
    bot_a = {la for la in labels if rank_a[la] >= N - Y}
    bot_b = {la for la in labels if rank_b[la] >= N - Z}

    tier1 = top_a & top_b
    tier2 = (top_a | top_b) - tier1
    tier5 = bot_a & bot_b
    tier4 = (bot_a | bot_b) - tier5
    tier3 = set(labels) - (tier1 | tier2) - (tier4 | tier5)

    # Build lookup
    jdata = {j["label"]: j for j in journals}

    def _tier_list(s: set) -> List[Dict]:
        return sorted(
            [jdata[la] for la in s],
            key=lambda j: (j["saved"], j["rate"]),
            reverse=True,
        )

    return {
        1: _tier_list(tier1),
        2: _tier_list(tier2),
        3: _tier_list(tier3),
        4: _tier_list(tier4),
        5: _tier_list(tier5),
    }


_TIER_COLORS = {
    1: "#1a7431",  # dark green
    2: "#4CAF50",  # green
    3: "#757575",  # neutral grey
    4: "#EF6C00",  # orange
    5: "#C62828",  # red
}

_TIER_LABELS = {
    1: "Tier 1",
    2: "Tier 2",
    3: "Tier 3",
    4: "Tier 4",
    5: "Tier 5",
}


def _render_journal_tiers() -> None:
    st.markdown("### Journal tiers")
    st.caption(
        "Journals ranked into 5 tiers based on how many papers you save (volume) "
        "and what fraction you save (rate). Tier 1 = highest on both dimensions."
    )

    if st.button("Compute tiers", key="dashboard_compute_tiers"):
        with st.spinner("Computing journal tiers..."):
            st.session_state["dashboard_journal_tiers"] = _compute_journal_tiers()

    tiers = st.session_state.get("dashboard_journal_tiers")
    if not tiers:
        st.info("Click **Compute tiers** to generate journal tier rankings.")
        return

    for tier_num in (1, 2, 3, 4, 5):
        journals = tiers.get(tier_num, [])
        color = _TIER_COLORS[tier_num]
        label = _TIER_LABELS[tier_num]

        st.markdown(
            f"<div style='border-left: 4px solid {color}; padding-left: 12px; margin-bottom: 8px;'>"
            f"<strong style='color: {color}; font-size: 1.1em;'>{label}</strong>"
            f"<span style='color: #888; margin-left: 8px;'>({len(journals)} journals)</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if journals:
            rows_md = []
            for j in journals:
                rate_str = f"{j['rate'] * 100:.1f}%" if j["reviewed"] > 0 else "—"
                rows_md.append(
                    f"| {j['label']} | {j['saved']} | {j['reviewed']} | {rate_str} |"
                )
            table = (
                "| Journal | Saved | Reviewed | Save rate |\n"
                "|:--------|------:|---------:|----------:|\n"
                + "\n".join(rows_md)
            )
            st.markdown(table)
        else:
            st.caption("*(none)*")

        st.markdown("")

