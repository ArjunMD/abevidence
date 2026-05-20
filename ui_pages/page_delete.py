from typing import Dict, List, Optional

import streamlit as st

from db import (
    delete_guideline,
    delete_record,
    get_guideline_meta,
    get_guideline_recommendations_display,
    get_record,
    list_guidelines,
    list_recent_records,
    search_guidelines,
    search_records,
    update_guideline_metadata,
    update_guideline_recommendations_display,
    update_record,
)
from extract import _parse_nonneg_int, _parse_tag_list, _parse_year4


def _clip_text(value: str, max_len: int = 90) -> str:
    s = (value or "").strip()
    if len(s) <= int(max_len):
        return s
    return s[: max(0, int(max_len) - 1)].rstrip() + "…"


def _init_edit_fields(rec: Dict[str, str], pmid: str) -> None:
    """Populate session-state edit keys from a record, only if not already set for this PMID."""
    marker = f"_manage_edit_loaded_{pmid}"
    if st.session_state.get(marker):
        return
    st.session_state[f"manage_patient_n_{pmid}"] = rec.get("patient_n") or ""
    st.session_state[f"manage_study_design_{pmid}"] = rec.get("study_design") or ""
    st.session_state[f"manage_patient_details_{pmid}"] = rec.get("patient_details") or ""
    st.session_state[f"manage_ic_{pmid}"] = rec.get("intervention_comparison") or ""
    st.session_state[f"manage_conclusions_{pmid}"] = rec.get("authors_conclusions") or ""
    st.session_state[f"manage_results_{pmid}"] = rec.get("results") or ""
    st.session_state[f"manage_specialty_{pmid}"] = rec.get("specialty") or ""
    st.session_state[marker] = True


def render() -> None:
    st.title("Manage")
    manage_flash = (st.session_state.pop("manage_paper_flash", "") or "").strip()
    if manage_flash:
        st.toast(manage_flash)

    tab_papers, tab_guidelines = st.tabs(["Abstracts", "Guidelines"])

    with tab_papers:
        st.subheader("Edit or delete a saved abstract")

        q = st.text_input(
            "Filter papers",
            placeholder="Search title/journal/specialty/PMID… (default is most recent)",
            key="delete_paper_filter",
        )

        paper_rows = search_records(limit=200, q=q) if (q or "").strip() else list_recent_records(limit=200)

        if not paper_rows:
            st.info("No saved papers found.")
        else:

            def _paper_label(r: Dict[str, str]) -> str:
                title = (r.get("title") or "").strip()
                year = (r.get("year") or "").strip()
                journal = (r.get("journal") or "").strip()
                bits = [title]
                if year:
                    bits.append(f"({year})")
                if journal:
                    bits.append(f"— {journal}")
                return " ".join([b for b in bits if b]).strip()

            sel_i = st.selectbox(
                "Select a paper",
                list(range(len(paper_rows))),
                format_func=lambda i: _paper_label(paper_rows[i]),
                key="delete_paper_select_idx",
            )

            sel_pmid = (paper_rows[sel_i].get("pmid") or "").strip()
            rec = get_record(sel_pmid) or {}

            _init_edit_fields(rec, sel_pmid)

            st.write(f"**PMID:** {sel_pmid}")

            with st.expander("Show abstract", expanded=False):
                abs_txt = (rec.get("abstract") or "").strip()
                if abs_txt:
                    st.write(abs_txt)

            # --- Editable extracted fields ---
            col_left, col_right = st.columns([1, 1], gap="large")

            with col_left:
                st.text_area(
                    "Authors' conclusions",
                    key=f"manage_conclusions_{sel_pmid}",
                    placeholder="Near-verbatim conclusion statement.",
                    height=110,
                )

                st.text_area(
                    "Patient details",
                    key=f"manage_patient_details_{sel_pmid}",
                    placeholder="- Adults >=18 years with ...\n- Excluded if ...\n- Mean age ...\n- % male ...",
                    height=160,
                )

                st.text_area(
                    "Results",
                    key=f"manage_results_{sel_pmid}",
                    placeholder="- Primary outcome: ... (effect estimate, CI)\n- Secondary outcome: ...",
                    height=160,
                )

            with col_right:
                st.text_input(
                    "Specialty",
                    key=f"manage_specialty_{sel_pmid}",
                    placeholder="e.g., Infectious Disease, Critical Care",
                )

                st.text_input(
                    "Total patients",
                    key=f"manage_patient_n_{sel_pmid}",
                    placeholder="e.g., 250",
                )

                st.text_area(
                    "Study design tags",
                    key=f"manage_study_design_{sel_pmid}",
                    placeholder="e.g., Randomized controlled trial, Double-blind, Multicenter, USA",
                    height=110,
                )

                st.text_area(
                    "Intervention / comparison",
                    key=f"manage_ic_{sel_pmid}",
                    placeholder="- Intervention: ...\n- Comparator: ...\n- Dose/duration: ...",
                    height=140,
                )

            # --- Save / Delete buttons ---
            btn_left, btn_right = st.columns([3, 1], gap="large")

            with btn_left:
                if st.button("Save changes", type="primary", width="stretch", key=f"btn_save_paper_{sel_pmid}"):
                    raw_n = (st.session_state.get(f"manage_patient_n_{sel_pmid}") or "").strip()
                    parsed_n: Optional[int] = _parse_nonneg_int(raw_n)

                    raw_design = (st.session_state.get(f"manage_study_design_{sel_pmid}") or "").strip()
                    parsed_design = raw_design if raw_design else None

                    raw_details = (st.session_state.get(f"manage_patient_details_{sel_pmid}") or "").strip()
                    parsed_details = raw_details if raw_details else None

                    raw_ic = (st.session_state.get(f"manage_ic_{sel_pmid}") or "").strip()
                    parsed_ic = raw_ic if raw_ic else None

                    raw_concl = (st.session_state.get(f"manage_conclusions_{sel_pmid}") or "").strip()
                    parsed_concl = raw_concl if raw_concl else None

                    raw_results = (st.session_state.get(f"manage_results_{sel_pmid}") or "").strip()
                    parsed_results = raw_results if raw_results else None

                    raw_spec = (st.session_state.get(f"manage_specialty_{sel_pmid}") or "").strip()
                    parsed_spec = _parse_tag_list(raw_spec) or None

                    if raw_n and parsed_n is None:
                        st.error("Patient count must be a single integer (or leave blank).")
                    else:
                        try:
                            update_record(
                                pmid=sel_pmid,
                                patient_n=parsed_n,
                                study_design=parsed_design,
                                patient_details=parsed_details,
                                intervention_comparison=parsed_ic,
                                authors_conclusions=parsed_concl,
                                results=parsed_results,
                                specialty=parsed_spec,
                            )
                            # Reset the loaded marker so next rerun picks up fresh DB values
                            st.session_state.pop(f"_manage_edit_loaded_{sel_pmid}", None)
                            st.session_state["manage_paper_flash"] = f"Saved changes to PMID {sel_pmid}."
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save: {e}")

            with btn_right:
                confirm = st.checkbox("Confirm delete", key=f"confirm_delete_paper_{sel_pmid}")
                if st.button(
                    "Delete paper",
                    width="stretch",
                    disabled=not confirm,
                    key=f"btn_delete_paper_{sel_pmid}",
                ):
                    try:
                        delete_record(sel_pmid)
                        st.session_state.pop(f"_manage_edit_loaded_{sel_pmid}", None)
                        st.session_state["manage_paper_flash"] = "Deleted paper."
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    with tab_guidelines:
        st.subheader("Edit or delete a saved guideline")

        gq = st.text_input(
            "Filter guidelines",
            placeholder="Search name/filename/year/specialty… (leave blank for recent)",
            key="delete_guideline_filter",
        )

        raw_rows = search_guidelines(limit=200, q=gq) if (gq or "").strip() else list_guidelines(limit=200)

        guidelines: List[Dict[str, str]] = []
        for r in raw_rows:
            gid = (r.get("guideline_id") or "").strip()
            if not gid:
                continue
            title = (r.get("title") or r.get("guideline_name") or r.get("filename") or "").strip()
            society = (r.get("society") or "").strip()
            year = (r.get("year") or r.get("pub_year") or "").strip()
            specialty = (r.get("specialty") or "").strip()
            guidelines.append({"guideline_id": gid, "title": title, "society": society, "year": year, "specialty": specialty})

        def _guideline_label(r: Dict[str, str]) -> str:
            title = (r.get("title") or "").strip()
            soc = (r.get("society") or "").strip()
            year = (r.get("year") or "").strip()
            spec = (r.get("specialty") or "").strip()
            bits = [title]
            if soc:
                bits.append(f"[{soc}]")
            if year:
                bits.append(f"({year})")
            if spec:
                bits.append(f"— {spec}")
            return " ".join([b for b in bits if b]).strip()

        gid_options = [g["guideline_id"] for g in guidelines if (g.get("guideline_id") or "").strip()]
        gid_to_row = {g["guideline_id"]: g for g in guidelines if (g.get("guideline_id") or "").strip()}

        if not gid_options:
            st.info("No saved guidelines found.")
        else:
            _state_key = "delete_guideline_selected_gid"

            prev = st.session_state.get(_state_key)
            if prev and prev not in gid_options:
                st.session_state.pop(_state_key, None)

            sel_gid = st.selectbox(
                "Select a guideline",
                options=gid_options,
                format_func=lambda gid: _guideline_label(
                    gid_to_row.get(gid, {"guideline_id": gid, "title": gid, "year": "", "specialty": ""})
                ),
                key=_state_key,
            )

            meta = get_guideline_meta(sel_gid) or {}

            # --- Init guideline edit fields ---
            _gid_marker = f"_manage_guideline_loaded_{sel_gid}"
            if not st.session_state.get(_gid_marker):
                st.session_state[f"manage_gname_{sel_gid}"] = meta.get("guideline_name") or ""
                st.session_state[f"manage_gsociety_{sel_gid}"] = meta.get("society") or ""
                st.session_state[f"manage_gyear_{sel_gid}"] = meta.get("pub_year") or ""
                st.session_state[f"manage_gspec_{sel_gid}"] = meta.get("specialty") or ""
                st.session_state[f"manage_gdisplay_{sel_gid}"] = get_guideline_recommendations_display(sel_gid) or ""
                st.session_state[_gid_marker] = True

            # --- Editable metadata fields ---
            gm1, gm2, gm3, gm4 = st.columns([2, 1, 1, 1], gap="medium")
            with gm1:
                st.text_input("Name", key=f"manage_gname_{sel_gid}", placeholder=meta.get("filename") or "Guideline name")
            with gm2:
                st.text_input("Society", key=f"manage_gsociety_{sel_gid}", placeholder="e.g., ACG, AHA/ACC")
            with gm3:
                st.text_input("Published year", key=f"manage_gyear_{sel_gid}", placeholder="e.g., 2023")
            with gm4:
                st.text_input("Specialty", key=f"manage_gspec_{sel_gid}", placeholder="e.g., Cardiology, Critical Care")

            # --- Editable recommendations display ---
            st.text_area(
                "Recommendations display (Markdown)",
                key=f"manage_gdisplay_{sel_gid}",
                height=320,
                placeholder="Clinician-friendly recommendations (Markdown). Edit freely.",
            )

            # --- Save / Delete buttons ---
            gbtn_left, gbtn_right = st.columns([3, 1], gap="large")

            with gbtn_left:
                if st.button("Save changes", type="primary", width="stretch", key=f"btn_save_guideline_{sel_gid}"):
                    name_raw = (st.session_state.get(f"manage_gname_{sel_gid}") or "").strip()
                    society_raw = (st.session_state.get(f"manage_gsociety_{sel_gid}") or "").strip()
                    year_raw = (st.session_state.get(f"manage_gyear_{sel_gid}") or "").strip()
                    spec_raw = (st.session_state.get(f"manage_gspec_{sel_gid}") or "").strip()
                    disp_raw = (st.session_state.get(f"manage_gdisplay_{sel_gid}") or "").strip()

                    year_parsed = _parse_year4(year_raw) if year_raw else ""
                    if year_raw and not year_parsed:
                        st.error("Published year must be a 4-digit year (e.g., 2023) or blank.")
                    else:
                        try:
                            update_guideline_metadata(
                                guideline_id=sel_gid,
                                guideline_name=name_raw or None,
                                pub_year=year_parsed or None,
                                specialty=_parse_tag_list(spec_raw) or None,
                                society=society_raw or None,
                            )
                            update_guideline_recommendations_display(sel_gid, disp_raw)
                            st.session_state.pop(_gid_marker, None)
                            st.session_state["manage_paper_flash"] = "Saved guideline changes."
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save: {e}")

            with gbtn_right:
                gconfirm = st.checkbox("Confirm delete", key=f"confirm_delete_guideline_{sel_gid}")
                if st.button(
                    "Delete guideline",
                    width="stretch",
                    disabled=not gconfirm,
                    key=f"btn_delete_guideline_{sel_gid}",
                ):
                    try:
                        delete_guideline(sel_gid)
                        st.session_state.pop(_gid_marker, None)
                        st.session_state["manage_paper_flash"] = "Deleted guideline."
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
