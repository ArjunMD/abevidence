import streamlit as st

from db import (
    delete_vbc_tag,
    list_browse_items,
    list_vbc_tags,
    set_vbc_tag,
    update_vbc_tag,
)
from pages_shared import is_public_mode
from ui_pages.page_db_browse import _render_browse_item

# The payment programs and their measures. Data-driven so new programs/measures
# can be added here with no schema change. `key` is stored in the DB; `label` is
# shown; `description` is a short blurb rendered under the program header.
VBC_PROGRAMS = [
    {
        "key": "readmissions",
        "label": "Readmissions (HRRP)",
        "description": (
            "The Hospital Readmissions Reduction Program (HRRP), was created by the Affordable Care "
            "Act and was launched in October, 2012. Penalties are based on a risk-adjusted readmission rates and can "
            "cost up to 3 percent of a hospital's Medicare payments. The program applies to six "
            "conditions: **acute myocardial infarction (AMI)**, **heart failure (HF)**, "
            "**COPD**, **pneumonia**, elective **total hip/knee arthroplasty**, and **CABG**. "
            "In this section, we highlight research focus on best practices of the first four conditions with an emphasis on how to "
            "reduce readmissions."
        ),
        "measures": ["General", "AMI", "HF", "COPD", "Pneumonia"],
    },
    {
        "key": "hac",
        "label": "Hospital-Acquired Conditions",
        "description": "",
        "measures": [
            "General",
            "CLABSI",
            "CAUTI",
            "SSI (Colon & Abdominal Hysterectomy)",
            "MRSA bacteremia",
            "CDI",
        ],
    },
]

# Predefined subsections under a specific (program_key, measure). They always
# render as sub-headers under that measure; the user can also create new ones on
# the fly when tagging (the subsection field accepts new options).
VBC_SUBSECTIONS: dict[tuple[str, str], list[str]] = {
    ("readmissions", "HF"): [
        "Adequate Initial Diuresis",
        "Salt Restriction",
        "Daily monitoring including Braking phenomenon and Rising Creatinine",
        "Continuing GDMT During Decompensation",
        "Decongestion Before Discharge",
        "IV-to-Oral Diuretic Transition",
        "Discharge Education & Early Follow-up",
    ],
}

_PROG_BY_KEY = {p["key"]: p for p in VBC_PROGRAMS}
_KEY_BY_LABEL = {p["label"]: p["key"] for p in VBC_PROGRAMS}

# Big enough to include every saved abstract; the picker and the display both
# read from this one snapshot so a paper is only looked up once.
_PAPERS_LIMIT = 30000


def _slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in (text or "")]
    s = "".join(keep).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s or "section"


def _paper_label(p: dict[str, str]) -> str:
    title = (p.get("title") or "").strip() or f"PMID {p.get('pmid', '')}"
    journal = (p.get("journal") or "").strip()
    year = (p.get("year") or "").strip()
    bits = [b for b in [journal, year] if b]
    return f"{title} — {' · '.join(bits)}" if bits else title


def _pub_date_key(p: dict[str, str]) -> tuple[int, int]:
    """(year, month) as ints for newest-first sorting; missing parts sort oldest."""
    y = (p.get("year") or "").strip()
    m = (p.get("pub_month") or "").strip()
    yi = int(y) if y.isdigit() else 0
    mi = int(m) if (m.isdigit() and 1 <= int(m) <= 12) else 0
    return (yi, mi)


def _subsections_for(program_key: str, measure: str, tags: list[dict[str, str]]) -> list[str]:
    """Predefined subsections for a measure (in config order) plus any others that
    already appear in the data, so nothing gets orphaned."""
    predefined = list(VBC_SUBSECTIONS.get((program_key, measure), []))
    seen = {s.lower() for s in predefined}
    extra: list[str] = []
    for t in tags:
        if t["program"] != program_key or t["measure"] != measure:
            continue
        s = (t.get("subsection") or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            extra.append(s)
    return predefined + sorted(extra, key=str.lower)


def _render_article_list(tag_list: list[dict[str, str]], pmap: dict[str, dict[str, str]]) -> None:
    for t in sorted(tag_list, key=lambda x: _pub_date_key(pmap.get(x["pmid"], {})), reverse=True):
        it = pmap.get(t["pmid"])
        if it:
            _render_browse_item(it, show_pub_date=True, allow_delete=False)
        else:
            st.markdown(f"- *[Removed from database — PMID {t['pmid']}]*")


def _render_tag_form(pmap: dict[str, dict[str, str]], tags: list[dict[str, str]]) -> None:
    with st.expander("+ Tag an article", expanded=False):
        if not pmap:
            st.info("No saved abstracts yet. Add papers on the Upload Abstract page first.")
            return

        # Hide articles that already carry any Metrics tag — this picker is for
        # bringing new articles in. (Already-tagged articles can still gain more
        # tags via the 🏷️ tagger in the Single-study view / Upload Abstract.)
        tagged_pmids = {t["pmid"] for t in tags}
        options = sorted(
            (pid for pid in pmap.keys() if pid not in tagged_pmids),
            key=lambda pid: (pmap[pid].get("uploaded_at") or ""),
            reverse=True,
        )
        if not options:
            st.caption("All saved articles are already tagged.")
        pmid = st.selectbox(
            "Article (type to search your saved abstracts)",
            options=options,
            index=None,
            placeholder="Choose a saved paper…",
            key="vbc_add_pmid",
            format_func=lambda pid: _paper_label(pmap[pid]),
        )

        prog_label = st.radio(
            "Program",
            options=[p["label"] for p in VBC_PROGRAMS],
            key="vbc_add_program",
            horizontal=True,
        )
        program = _KEY_BY_LABEL[prog_label]

        measure = st.selectbox(
            "Measure",
            options=_PROG_BY_KEY[program]["measures"],
            index=None,
            placeholder="Choose a measure…",
            key=f"vbc_add_measure_{program}",
        )

        subsection = st.selectbox(
            "Subsection (optional — type to add a new one)",
            options=_subsections_for(program, measure, tags) if measure else [],
            index=None,
            placeholder="— none (directly under the measure) —",
            key=f"vbc_add_sub_{program}_{measure or 'x'}",
            accept_new_options=True,
        )

        if st.button("Tag article", type="primary", key="vbc_add_btn"):
            if not pmid:
                st.error("Choose a paper from your database.")
            elif not measure:
                st.error("Choose a measure.")
            else:
                set_vbc_tag(pmid, program, measure, subsection or "")
                st.session_state.pop("vbc_add_pmid", None)
                st.session_state.pop(f"vbc_add_measure_{program}", None)
                st.session_state.pop(f"vbc_add_sub_{program}_{measure or 'x'}", None)
                st.toast("Article tagged.")
                st.rerun()


def _prog_label(program_key: str) -> str:
    return (_PROG_BY_KEY.get(program_key) or {}).get("label", program_key)


def render_metrics_tagger(pmid: str, key_prefix: str, expanded: bool = False) -> None:
    """Compact form to tag ONE article (by pmid) for the Metrics page. Reusable
    from the Single-study view and Upload Abstract pages. Owner-only — callers
    should not render it in public mode."""
    pid = (pmid or "").strip()
    if not pid:
        return

    tags = list_vbc_tags()
    existing = [t for t in tags if t["pmid"] == pid]

    title = f"🏷️ Metrics tags ({len(existing)})" if existing else "🏷️ Add to Metrics"
    with st.expander(title, expanded=expanded):
        for t in existing:
            sub = (t.get("subsection") or "").strip()
            path = f"{_prog_label(t['program'])} › {t['measure']}" + (f" › {sub}" if sub else "")
            st.caption(f"• {path}")

        prog_label = st.radio(
            "Program",
            options=[p["label"] for p in VBC_PROGRAMS],
            key=f"{key_prefix}_prog",
            horizontal=True,
        )
        program = _KEY_BY_LABEL[prog_label]

        measure = st.selectbox(
            "Measure",
            options=_PROG_BY_KEY[program]["measures"],
            index=None,
            placeholder="Choose a measure…",
            key=f"{key_prefix}_measure_{program}",
        )

        subsection = st.selectbox(
            "Subsection (optional — type to add a new one)",
            options=_subsections_for(program, measure, tags) if measure else [],
            index=None,
            placeholder="— none (directly under the measure) —",
            key=f"{key_prefix}_sub_{program}_{measure or 'x'}",
            accept_new_options=True,
        )

        if st.button("Tag article", type="primary", key=f"{key_prefix}_btn"):
            if not measure:
                st.error("Choose a measure.")
            else:
                set_vbc_tag(pid, program, measure, subsection or "")
                st.toast("Tagged for Metrics.")
                st.rerun()


def _render_manage(pmap: dict[str, dict[str, str]], tags: list[dict[str, str]]) -> None:
    if not tags:
        return
    with st.expander(f"Manage tagged articles ({len(tags)})", expanded=False):
        for program in VBC_PROGRAMS:
            prog_tags = [t for t in tags if t["program"] == program["key"]]
            if not prog_tags:
                continue
            st.markdown(f"**{program['label']}**")
            for t in sorted(prog_tags, key=lambda x: (x["measure"], (x.get("subsection") or ""))):
                tid = t["tag_id"]
                title = (pmap.get(t["pmid"], {}).get("title") or "").strip() or f"PMID {t['pmid']}"
                st.caption(f"{title} — _{t['measure']}_")
                sub_opts = _subsections_for(program["key"], t["measure"], tags)
                cur = (t.get("subsection") or "").strip()
                c_edit, c_save, c_rm = st.columns([5, 1, 1])
                with c_edit:
                    new_sub = st.selectbox(
                        "Subsection",
                        options=sub_opts,
                        index=sub_opts.index(cur) if cur in sub_opts else None,
                        placeholder="— none (directly under the measure) —",
                        key=f"vbc_edit_{tid}",
                        accept_new_options=True,
                        label_visibility="collapsed",
                    )
                with c_save:
                    if st.button("Save", key=f"vbc_save_{tid}", use_container_width=True):
                        update_vbc_tag(tid, new_sub or "")
                        st.toast("Updated.")
                        st.rerun()
                with c_rm:
                    if st.button("Remove", key=f"vbc_rm_{tid}", use_container_width=True):
                        delete_vbc_tag(tid)
                        st.toast("Removed.")
                        st.rerun()
            st.markdown("")


def render() -> None:
    st.title("📊 Metrics")
    st.markdown("Studies relevant to hospital quality metrics.")

    read_only = is_public_mode()
    pmap = {p["pmid"]: p for p in list_browse_items(_PAPERS_LIMIT)}
    tags = list_vbc_tags()

    if not read_only:
        _render_tag_form(pmap, tags)
        _render_manage(pmap, tags)

    st.divider()

    for program in VBC_PROGRAMS:
        st.header(program["label"], anchor=program["key"])
        desc = (program.get("description") or "").strip()
        if desc:
            st.markdown(desc)

        prog_tags = [t for t in tags if t["program"] == program["key"]]
        shown_any = False

        for measure in program["measures"]:
            measure_tags = [t for t in prog_tags if t["measure"] == measure]
            subsections = _subsections_for(program["key"], measure, tags)

            # Show the measure if it has articles OR any (predefined/known) subsection.
            if not measure_tags and not subsections:
                continue
            shown_any = True
            st.subheader(measure, anchor=f"{program['key']}-{_slug(measure)}")

            # Articles filed directly under the measure (no subsection).
            direct = [t for t in measure_tags if not (t.get("subsection") or "").strip()]
            _render_article_list(direct, pmap)

            # Then each subsection (predefined first, then any extra from the data).
            for sub in subsections:
                sub_tags = [
                    t for t in measure_tags
                    if (t.get("subsection") or "").strip().lower() == sub.lower()
                ]
                st.markdown(f"#### {sub}")
                if sub_tags:
                    _render_article_list(sub_tags, pmap)
                else:
                    st.caption("_No articles yet._")

        if not shown_any:
            st.caption("No articles tagged yet.")
