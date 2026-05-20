import streamlit as st

from db import (
    get_guideline_recommendations_display,
    list_guidelines,
    save_guideline_pdf,
    update_guideline_metadata,
    update_guideline_recommendations_display,
)
from extract import (
    _parse_tag_list,
    _parse_year4,
    extract_and_store_guideline_metadata_azure,
    extract_and_store_guideline_recommendations_azure,
)
from pages_shared import GUIDELINES_MAX_LIST


def render() -> None:
    st.title("📄 Guidelines — Upload PDF")

    up = st.file_uploader("Upload a guideline PDF", type=["pdf"], accept_multiple_files=False)
    if up is not None:
        pdf_bytes = up.getvalue()

        if st.button("Upload + Extract", type="primary", width="stretch", key="guidelines_upload_extract_btn"):
            try:
                with st.spinner("Saving PDF…"):
                    rec = save_guideline_pdf(up.name, pdf_bytes)
                gid_saved = (rec.get("guideline_id") or "").strip()

                existing_disp = (get_guideline_recommendations_display(gid_saved) or "").strip()
                if existing_disp:
                    st.session_state["guidelines_last_saved"] = gid_saved
                    st.info("This PDF already exists in your database (final display already saved). Skipping extraction.")
                    st.rerun()

                if not gid_saved:
                    st.error("Save succeeded but returned no guideline_id.")
                    st.stop()

                try:
                    with st.spinner("Extracting metadata (name/year/specialty)…"):
                        extract_and_store_guideline_metadata_azure(gid_saved, pdf_bytes)
                except Exception as e:
                    st.warning(f"Metadata extraction failed/skipped: {e}")

                n_recs = 0
                disp_now = (get_guideline_recommendations_display(gid_saved) or "").strip()
                if disp_now:
                    st.info("This guideline already has a saved recommendations display; skipping extraction.")
                else:
                    phase_ph = st.empty()
                    detail_ph = st.empty()
                    prog_ph = st.empty()

                    def _cb(done, total, msg="Working…", detail=""):
                        m = (msg or "").strip()
                        d = (detail or "").strip()

                        if m:
                            phase_ph.caption(m)

                        if total and total > 0:
                            try:
                                frac = float(done) / float(total)
                            except Exception:
                                frac = 0.0
                            pct = int(max(0, min(100, round(frac * 100))))
                            prog_ph.progress(pct)

                            if d:
                                detail_ph.caption(f"{d} ({done}/{total})")
                            else:
                                detail_ph.caption(f"{done}/{total}")
                        else:
                            prog_ph.empty()
                            detail_ph.caption(d if d else "")

                    with st.spinner("Extracting recommendations + generating final display…"):
                        n_recs = extract_and_store_guideline_recommendations_azure(gid_saved, pdf_bytes, progress_cb=_cb)

                st.success(f"Done. Guideline ID: `{gid_saved}` • Extracted recommendations: {n_recs if n_recs else '—'}")
                st.rerun()
            except Exception as e:
                st.error(f"Upload/extract failed: {e}")

    st.divider()

    rows = list_guidelines(limit=GUIDELINES_MAX_LIST)
    if not rows:
        st.info("No guideline PDFs uploaded yet.")
        st.stop()

    def _fmt_g(g):
        name = (g.get("guideline_name") or "").strip() or (g.get("filename") or "")
        soc = (g.get("society") or "").strip()
        year = (g.get("pub_year") or "").strip()
        spec = (g.get("specialty") or "").strip()
        bits = [b for b in [soc, year, spec] if b]
        meta = (" • ".join(bits) + " — ") if bits else ""
        return f"{name} — {meta}{g.get('uploaded_at', '')}"

    default_gid = (st.session_state.get("guidelines_last_saved") or "").strip()
    default_idx = 0
    if default_gid:
        for i, r in enumerate(rows):
            if (r.get("guideline_id") or "") == default_gid:
                default_idx = i
                break

    chosen = st.selectbox("Choose a guideline", options=rows, format_func=_fmt_g, index=default_idx)
    gid = (chosen.get("guideline_id") or "").strip()

    if st.session_state.get("guideline_meta_loaded_gid") != gid:
        st.session_state["guideline_meta_loaded_gid"] = gid
        st.session_state["guideline_meta_name"] = (chosen.get("guideline_name") or "").strip()
        st.session_state["guideline_meta_society"] = (chosen.get("society") or "").strip()
        st.session_state["guideline_meta_year"] = (chosen.get("pub_year") or "").strip()
        st.session_state["guideline_meta_spec"] = (chosen.get("specialty") or "").strip()

    pending = st.session_state.pop("guideline_meta_pending", None)
    if isinstance(pending, dict) and (pending.get("gid") or "") == gid:
        st.session_state["guideline_meta_name"] = (pending.get("name") or "").strip()
        st.session_state["guideline_meta_society"] = (pending.get("society") or "").strip()
        st.session_state["guideline_meta_year"] = (pending.get("year") or "").strip()
        st.session_state["guideline_meta_spec"] = (pending.get("spec") or "").strip()

    st.divider()
    st.subheader("Guideline metadata")

    m1, m2, m3, m4, m5 = st.columns([2, 1, 1, 1, 1], gap="large")

    with m1:
        st.text_input("Name", key="guideline_meta_name", placeholder=chosen.get("filename") or "Guideline name")
    with m2:
        st.text_input("Society", key="guideline_meta_society", placeholder="e.g., ACG, AHA/ACC")
    with m3:
        st.text_input("Published year", key="guideline_meta_year", placeholder="e.g., 2023")
    with m4:
        st.text_input("Specialty", key="guideline_meta_spec", placeholder="e.g., Cardiology, Critical Care")

    with m5:
        if st.button("Save metadata (if changed)", type="primary", width="stretch", key="guideline_meta_save"):
            name_raw = (st.session_state.get("guideline_meta_name") or "").strip()
            society_raw = (st.session_state.get("guideline_meta_society") or "").strip()
            year_raw = (st.session_state.get("guideline_meta_year") or "").strip()
            spec_raw = (st.session_state.get("guideline_meta_spec") or "").strip()

            year_parsed = _parse_year4(year_raw) if year_raw else ""
            if year_raw and not year_parsed:
                st.error("Published year must be a 4-digit year (e.g., 2023) or blank.")
            else:
                try:
                    update_guideline_metadata(
                        guideline_id=gid,
                        guideline_name=name_raw or None,
                        pub_year=year_parsed or None,
                        specialty=_parse_tag_list(spec_raw) or None,
                        society=society_raw or None,
                    )
                    st.success("Metadata saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save metadata: {e}")

    st.divider()
    st.markdown("##### Clinician-friendly recommendations display (editable)")

    if st.session_state.get("guideline_display_loaded_gid") != gid:
        st.session_state["guideline_display_loaded_gid"] = gid
        st.session_state["guideline_display_md"] = get_guideline_recommendations_display(gid) or ""

    st.text_area(
        "Display (Markdown)",
        key="guideline_display_md",
        height=520,
        placeholder="Saved clinician-friendly display (Markdown). You can edit freely and click Save.",
    )

    c_a, c_c = st.columns([1, 2], gap="large")

    with c_a:
        if st.button("Save display", type="primary", width="stretch", key=f"guideline_disp_save_{gid}"):
            try:
                update_guideline_recommendations_display(gid, st.session_state.get("guideline_display_md") or "")
                st.success("Display saved.")
            except Exception as e:
                st.error(str(e))

    with c_c:
        with st.expander("Preview (read-only)", expanded=False):
            preview_md = (st.session_state.get("guideline_display_md") or "").strip()
            if preview_md:
                st.markdown(preview_md)
            else:
                st.markdown("—")
