import html

import streamlit as st

from db import (
    get_guideline_acronyms,
    get_guideline_meta,
    get_guideline_rec_labels,
    get_guideline_recommendations_display,
    get_record,
    list_browse_guideline_items,
    list_browse_items,
    update_guideline_recommendations_display,
)
from extract import get_s2_similar_papers, get_top_neighbors
from pages_shared import (
    BROWSE_MAX_ROWS,
    _delete_recs_from_guideline_md,
    _fmt_search_item,
    _parse_rec_nums,
    _render_bullets,
    _render_plain_text,
    _render_related_item_row,
    _render_related_tray,
    _tags_to_md,
    clear_public_study_overlay,
    display_journal,
    guideline_has_evidence,
    is_public_mode,
    render_guideline_display,
)


def render() -> None:
    if is_public_mode() and st.session_state.get("public_study_overlay"):
        if st.button("← Back to studies", key="db_search_back"):
            clear_public_study_overlay()
            st.rerun()

    st.title("📚 Single-study view")

    forced_selected: dict[str, str] | None = None
    open_pmid = (st.session_state.get("db_search_open_pmid") or "").strip()
    open_gid = (st.session_state.get("db_search_open_gid") or "").strip()

    if open_pmid:
        forced_selected = {"type": "paper", "pmid": open_pmid}
    elif open_gid:
        forced_selected = {"type": "guideline", "guideline_id": open_gid}

    # All saved studies (papers + guidelines), most-recently-added first, in one
    # searchable dropdown — like the Metrics picker. Typing filters by title/meta.
    items = list_browse_items(BROWSE_MAX_ROWS) + list_browse_guideline_items(BROWSE_MAX_ROWS)
    items.sort(key=lambda it: (it.get("uploaded_at") or ""), reverse=True)

    if not items:
        st.info("No saved studies yet.")
        st.stop()

    def _item_id(it: dict[str, str]) -> str:
        gid = (it.get("guideline_id") or "").strip()
        if gid or (it.get("type") or "") == "guideline":
            return f"g:{gid}"
        return f"p:{(it.get('pmid') or '').strip()}"

    id_to_item = {_item_id(it): it for it in items}
    options = list(id_to_item.keys())

    # A deep-link (?pmid= / ?gid= from Browse) preselects that study, then is
    # consumed so the dropdown can be freely changed afterward.
    if forced_selected:
        forced_id = _item_id(forced_selected)
        if forced_id in id_to_item:
            st.session_state["db_study_pick"] = forced_id
        st.session_state.pop("db_search_open_pmid", None)
        st.session_state.pop("db_search_open_gid", None)

    picked_id = st.selectbox(
        "Study",
        options=options,
        index=None,
        placeholder="Choose a study… (most recently added first)",
        format_func=lambda i: _fmt_search_item(id_to_item[i]),
        key="db_study_pick",
    )

    if not picked_id or picked_id not in id_to_item:
        st.info("Choose a study to view.")
        st.stop()

    selected: dict[str, str] = id_to_item[picked_id]

    if (selected.get("type") or "") != "guideline":
        selected_pmid = selected["pmid"]
        rec = get_record(selected_pmid)
        if not rec:
            st.error("Could not load that record.")
            st.stop()

        st.markdown(f"[Open in PubMed](https://pubmed.ncbi.nlm.nih.gov/{selected_pmid}/) — `{selected_pmid}`")

        title = (rec.get("title") or "").strip()
        if title:
            st.subheader(title)

        # ----- Evidence-quality banner: Journal / N / Study design -----
        journal = display_journal(rec.get("journal") or "")
        year_str = (rec.get("year") or "").strip()
        pub_month = (rec.get("pub_month") or "").strip()
        if year_str and pub_month:
            year_str = f"{year_str}-{pub_month}"

        n_raw = (rec.get("patient_n") or "").strip()
        try:
            n_display = f"{int(n_raw):,}" if n_raw else "—"
        except (TypeError, ValueError):
            n_display = n_raw or "—"

        tags_md = _tags_to_md(rec.get("study_design") or "")

        ev1, ev2, ev3 = st.columns([3, 2, 3], gap="large")
        with ev1:
            if journal or year_str:
                journal_line = html.escape(journal) if journal else "—"
                year_line = (
                    f"<br><span style='opacity:0.65;font-size:0.85rem;'>{html.escape(year_str)}</span>"
                    if year_str
                    else ""
                )
                st.markdown(
                    f"**Journal**<br><span style='font-size:1.05rem;'>{journal_line}</span>{year_line}",
                    unsafe_allow_html=True,
                )
        with ev2:
            st.markdown(
                f"**Patients (N)**<br><span style='font-size:1.5rem;font-weight:600;'>{html.escape(n_display)}</span>",
                unsafe_allow_html=True,
            )
        with ev3:
            st.markdown(
                "**Study design**<br>" + (tags_md if tags_md else "—"),
                unsafe_allow_html=True,
            )

        st.divider()

        # ----- PICO drill-down -----
        st.markdown("### P — Population")
        _render_bullets(rec.get("patient_details") or "", empty_hint="—")

        st.markdown("### I/C — Intervention / Comparison")
        _render_bullets(rec.get("intervention_comparison") or "", empty_hint="—")

        st.markdown("### O — Outcomes / Results")
        _render_bullets(rec.get("outcomes") or "", empty_hint="—")

        evidence_base = (rec.get("evidence_base") or "").strip()
        if evidence_base:
            st.markdown("### Evidence base")
            _render_bullets(evidence_base, empty_hint="—")

        # ----- Authors' conclusion at the bottom, under outcomes -----
        concl = (rec.get("authors_conclusions") or "").strip()
        if concl:
            st.divider()
            st.markdown("### Authors’ conclusion")
            st.markdown(concl)

        abstract = (rec.get("abstract") or "").strip()
        if abstract:
            with st.expander("Original abstract"):
                _render_plain_text(abstract)

        # The related-paper clipboard is an owner curation aid (collect PMIDs to add
        # via Upload Abstract), so the 📋 buttons and tray are hidden in public mode.
        allow_clip = not is_public_mode()

        with st.expander("PubMed Related articles (top 5)"):
            try:
                neighbors = get_top_neighbors(selected_pmid, top_n=5)
                if not neighbors:
                    st.caption("No related articles found.")
                else:
                    for n in neighbors:
                        _render_related_item_row(
                            n.get("pmid") or "",
                            n.get("title") or n.get("pmid") or "",
                            source="PubMed related",
                            allow_add=allow_clip,
                        )
            except Exception:
                # NCBI's elink endpoint is intermittently unavailable. Never surface
                # the raw exception — it contains the request URL, which includes the
                # NCBI api_key. Show a clean, generic message instead.
                st.caption("PubMed related articles are temporarily unavailable — try again later.")

        with st.expander("Semantic Scholar similar papers (top 5)"):
            try:
                s2_papers = get_s2_similar_papers(selected_pmid, top_n=5)
                if not s2_papers:
                    st.caption("No similar papers found.")
                else:
                    for p in s2_papers:
                        title = (p.get("title") or "").strip() or (
                            p.get("pmid") or p.get("paperId") or "(no title)"
                        )
                        pmid = (p.get("pmid") or "").strip()
                        url = (p.get("url") or "").strip()
                        if pmid:
                            # Prefer a PubMed link (and clipboard) when we have a PMID.
                            _render_related_item_row(
                                pmid,
                                title,
                                source="Semantic Scholar related",
                                allow_add=allow_clip,
                            )
                        elif url:
                            paper_id = (p.get("paperId") or "").strip()
                            tag = f" — `{paper_id}`" if paper_id else ""
                            st.markdown(f"- [{title}]({url}){tag}")
                        else:
                            st.markdown(f"- {title}")
            except Exception:
                # Same precaution: don't leak request details (and the S2 config-hint
                # message isn't useful to a public visitor).
                st.caption("Semantic Scholar recommendations are temporarily unavailable — try again later.")

        # Same shared clipboard as the Upload Abstract page (where it's always
        # visible); shown here too for convenience while browsing related papers.
        if allow_clip:
            _render_related_tray()

    else:
        gid = (selected.get("guideline_id") or "").strip()
        meta = get_guideline_meta(gid) or {}
        title = (meta.get("guideline_name") or "").strip() or (meta.get("filename") or "").strip() or (
            selected.get("title") or ""
        )
        st.subheader(f"📘 {title}")

        bits = []
        soc = (meta.get("society") or "").strip()
        y = (meta.get("pub_year") or "").strip()
        s = (meta.get("specialty") or "").strip()
        if soc:
            bits.append(soc)
        if y:
            bits.append(y)
        if s:
            bits.append(s)
        if bits:
            st.caption(" • ".join(bits))

        st.divider()

        public = is_public_mode()

        if not public:
            pending_del = (st.session_state.pop("db_search_delete_rec", "") or "").strip()
            if pending_del:
                nums = _parse_rec_nums(pending_del)
                if nums:
                    cur = (get_guideline_recommendations_display(gid) or "").strip()
                    new_md, removed = _delete_recs_from_guideline_md(cur, nums)
                    if removed:
                        update_guideline_recommendations_display(gid, new_md)
                        st.session_state[f"dbs_guideline_edit_{gid}"] = True
                        st.success(f"Deleted: {', '.join([f'#{n}' for n in removed])}")
                    else:
                        st.info("No matching recommendation numbers found.")

        disp = (get_guideline_recommendations_display(gid) or "").strip()

        c_l, c_r = st.columns([6, 1], gap="small")
        with c_r:
            if public:
                edit_mode = False
            else:
                edit_mode = st.toggle(
                    "Quick Delete",
                    value=False,
                    key=f"dbs_guideline_edit_{gid}",
                )
            # Level of evidence is hidden by default (kept in storage); this reveals it.
            # Visible in both public and personal mode; sits below Quick Delete. Only
            # shown when this guideline actually carries evidence grading — guidelines
            # like anaphylaxis have nothing to reveal, so the toggle is omitted.
            if guideline_has_evidence(disp):
                show_evidence = st.toggle(
                    "Show level of evidence",
                    value=False,
                    key="dbs_guideline_show_loe",
                )
            else:
                show_evidence = False
        with c_l:
            if edit_mode:
                st.caption(
                    "Click 🗑️ to delete a recommendation permanently. Recommendations can also be edited in the Guidelines page."
                )

        render_guideline_display(
            disp,
            gid,
            edit_mode=edit_mode,
            rec_labels=get_guideline_rec_labels(gid),
            acronyms=get_guideline_acronyms(gid),
            show_evidence=show_evidence,
        )

    if is_public_mode() and st.session_state.get("public_study_overlay"):
        st.divider()
        if st.button("← Back to studies", key="db_search_back_bottom"):
            clear_public_study_overlay()
            st.rerun()
