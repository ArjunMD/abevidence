import html

import streamlit as st

from pages_shared import gated_lock, is_public_mode, render_gate
from readmissions_data import SECTIONS


def _slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in (text or "")]
    s = "".join(keep).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s or "section"


def _render_answer(a: dict) -> None:
    pmid = (a.get("pmid") or "").strip()
    url = (a.get("url") or "").strip() or (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "")
    title = html.escape((a.get("title") or "").strip() or "(untitled)")
    cite = html.escape((a.get("citation") or "").strip())
    design = html.escape((a.get("design") or "").strip())

    st.markdown(f"**Answer:** {(a.get('answer') or '').strip()}")
    link = f"<a href='{url}' target='_blank'>{title}</a>" if url else title
    meta = " · ".join(b for b in [cite, design] if b)
    st.markdown(
        f"<div style='opacity:0.8;font-size:0.9em;'>{link}"
        f"{f'<br>{meta}' if meta else ''}</div>",
        unsafe_allow_html=True,
    )
    details = (a.get("details") or "").strip()
    if details:
        with st.expander("Details"):
            st.markdown(details)


def render() -> None:
    # Listed on the public site but behind the shared password gate; open locally.
    public = is_public_mode()
    if public and not render_gate("Readmissions"):
        return

    c_title, c_lock = st.columns([6, 1])
    with c_title:
        st.title("📊 Readmissions")
    if public:
        with c_lock:
            if st.button("Lock", use_container_width=True):
                gated_lock()
                st.rerun()

    if not SECTIONS:
        st.caption("No papers yet.")
        return

    # Jump links to each section.
    st.markdown(" · ".join(f"[{s['title']}](#{_slug(s['title'])})" for s in SECTIONS))
    st.divider()

    for sec in SECTIONS:
        st.header(sec["title"], anchor=_slug(sec["title"]))
        intro = (sec.get("intro") or "").strip()
        if intro:
            st.markdown(intro)
        for q in sec.get("questions", []):
            st.subheader(q["q"], anchor=_slug(q["q"]))
            answers = q.get("answers", [])
            for i, a in enumerate(answers):
                if i:
                    st.markdown("")
                _render_answer(a)
        st.divider()
