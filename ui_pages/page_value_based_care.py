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
# (e.g. Value-Based Purchasing → mortality, PSI-90) can be added here with no
# schema or query changes. `key` is stored in the DB; `label` is shown.
VBC_PROGRAMS = [
    {
        "key": "readmissions",
        "label": "Readmissions (HRRP)",
        "measures": ["General", "AMI", "HF", "COPD", "Pneumonia"],
    },
    {
        "key": "hac",
        "label": "Hospital-Acquired Conditions",
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

_PROG_BY_KEY = {p["key"]: p for p in VBC_PROGRAMS}
_KEY_BY_LABEL = {p["label"]: p["key"] for p in VBC_PROGRAMS}

# Big enough to include every saved abstract; the picker and the display both
# read from this one snapshot so a paper is only looked up once.
_PAPERS_LIMIT = 30000


def _split_csv(raw: str) -> list[str]:
    out: list[str] = []
    seen = set()
    for tok in (raw or "").split(","):
        t = tok.strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out


def _slug(text: str) -> str:
    keep = [c.lower() if (c.isalnum()) else "-" for c in (text or "")]
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


def _render_tag_form(pmap: dict[str, dict[str, str]]) -> None:
    with st.expander("+ Tag an article", expanded=False):
        if not pmap:
            st.info("No saved abstracts yet. Add papers on the Upload Abstract page first.")
            return

        options = sorted(pmap.keys(), key=lambda pid: (pmap[pid].get("title") or "").lower())
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

        measures = st.multiselect(
            "Measure(s)",
            options=_PROG_BY_KEY[program]["measures"],
            key=f"vbc_add_measures_{program}",
        )

        if st.button("Tag article", type="primary", key="vbc_add_btn"):
            if not pmid:
                st.error("Choose a paper from your database.")
            elif not measures:
                st.error("Choose at least one measure.")
            else:
                set_vbc_tag(pmid, program, ", ".join(measures))
                st.session_state.pop("vbc_add_pmid", None)
                st.session_state.pop(f"vbc_add_measures_{program}", None)
                st.toast("Article tagged.")
                st.rerun()


def _render_manage(pmap: dict[str, dict[str, str]], tags: list[dict[str, str]]) -> None:
    if not tags:
        return
    with st.expander(f"Manage tagged articles ({len(tags)})", expanded=False):
        # Group by program so the management list mirrors the reading view.
        for program in VBC_PROGRAMS:
            prog_tags = [t for t in tags if t["program"] == program["key"]]
            if not prog_tags:
                continue
            st.markdown(f"**{program['label']}**")
            for t in prog_tags:
                tid = t["tag_id"]
                title = (pmap.get(t["pmid"], {}).get("title") or "").strip() or f"PMID {t['pmid']}"
                st.caption(title)
                c_edit, c_save, c_rm = st.columns([5, 1, 1])
                with c_edit:
                    new_measures = st.multiselect(
                        "Measures",
                        options=sorted(set(program["measures"]) | set(_split_csv(t["measures"]))),
                        default=_split_csv(t["measures"]),
                        key=f"vbc_edit_{tid}",
                        label_visibility="collapsed",
                    )
                with c_save:
                    if st.button("Save", key=f"vbc_save_{tid}", use_container_width=True):
                        update_vbc_tag(tid, ", ".join(new_measures))
                        st.toast("Updated.")
                        st.rerun()
                with c_rm:
                    if st.button("Remove", key=f"vbc_rm_{tid}", use_container_width=True):
                        delete_vbc_tag(tid)
                        st.toast("Removed.")
                        st.rerun()
            st.markdown("")


def render() -> None:
    st.title("💵 Value-Based Care")
    st.markdown(
        "Curated studies relevant to hospital **value-based payment programs** — where "
        "reimbursement rises with lower readmissions and fewer hospital-acquired conditions. "
        "Articles are drawn from the library and grouped by program and measure."
    )

    read_only = is_public_mode()
    pmap = {p["pmid"]: p for p in list_browse_items(_PAPERS_LIMIT)}
    tags = list_vbc_tags()

    if not read_only:
        _render_tag_form(pmap)
        _render_manage(pmap, tags)

    st.divider()

    for program in VBC_PROGRAMS:
        st.header(program["label"], anchor=program["key"])
        prog_tags = [t for t in tags if t["program"] == program["key"]]

        shown = False
        for measure in program["measures"]:
            arts = [t for t in prog_tags if measure in _split_csv(t["measures"])]
            if not arts:
                continue
            shown = True
            st.subheader(measure, anchor=f"{program['key']}-{_slug(measure)}")
            for t in sorted(arts, key=lambda x: (pmap.get(x["pmid"], {}).get("title") or "").lower()):
                it = pmap.get(t["pmid"])
                if it:
                    _render_browse_item(it, show_pub_date=True, allow_delete=False)
                else:
                    st.markdown(f"- *[Removed from database — PMID {t['pmid']}]*")

        if not shown:
            st.caption("No articles tagged yet.")
