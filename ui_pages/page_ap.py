import time

import streamlit as st

from extract import related_saved_papers, review_assessment_and_plan

# Soft access gate — keeps casual public visitors out of this (pricier, clinical)
# tool. Not a real credential; it's a shared page password.
_AP_PASSWORD = "BeCareful"


def render() -> None:
    st.title("🧠 Assessment and Plan")

    if not st.session_state.get("ap_unlocked"):
        st.caption("Password-protected tool.")
        st.text_input("Password", type="password", key="ap_pw",
                      placeholder="Password", label_visibility="collapsed")
        if st.button("Unlock", key="ap_unlock"):
            if st.session_state.get("ap_pw") == _AP_PASSWORD:
                st.session_state["ap_unlocked"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        return

    st.caption(
        "Paste your entire **deidentified** note — HPI, vitals, exam, labs, imaging — "
        "including your own clearly labeled assessment and plan. It reviews YOUR A&P: "
        "edits to the main problem, additions to the rest, and anything the note's data "
        "raises that the A&P doesn't address. AI-generated — verify all reasoning, "
        "dosing, and orders. Do not paste PHI."
    )
    note = st.text_area(
        "Note",
        key="ap_note",
        height=340,
        placeholder="Entire deidentified note, with your own assessment and plan clearly labeled…",
        label_visibility="collapsed",
    )

    if st.button("Review A&P", type="primary", key="ap_go"):
        if not note.strip():
            st.warning("Paste a note first.")
            st.session_state.pop("ap_review", None)
        else:
            try:
                with st.spinner("Reviewing the A&P…"):
                    st.session_state["ap_review"] = review_assessment_and_plan(note)
            except Exception as e:
                st.session_state.pop("ap_review", None)
                st.error(f"Review failed: {e}")
            # The saved-papers match is a separate cheap call so a failure (or
            # slowness) there can never cost the review itself. Timed, and the
            # seconds are shown, so it's honest about what it adds.
            if st.session_state.get("ap_review"):
                t0 = time.perf_counter()
                try:
                    with st.spinner("Checking your saved papers…"):
                        st.session_state["ap_papers"] = related_saved_papers(note)
                    st.session_state["ap_papers_error"] = ""
                except Exception as e:
                    st.session_state["ap_papers"] = []
                    st.session_state["ap_papers_error"] = str(e)
                st.session_state["ap_papers_seconds"] = time.perf_counter() - t0

    result = st.session_state.get("ap_review")
    if not result:
        return

    main = result.get("main_problem") or {}
    if not (main.get("comments") or result.get("other_problems")):
        st.info("Nothing came back — make sure the note includes a labeled assessment and plan.")
        return

    _render_main_problem(main)
    _render_other_problems(result.get("other_problems") or [])
    _render_missed_problems(result.get("missed_problems") or [])
    _render_other_thoughts(result.get("other_thoughts") or [])
    _render_saved_papers(
        st.session_state.get("ap_papers") or [],
        st.session_state.get("ap_papers_seconds"),
        st.session_state.get("ap_papers_error") or "",
    )
    _render_hospitalization_reason(result.get("hospitalization_reason") or "")


def _render_main_problem(main: dict) -> None:
    name = (main.get("problem") or "").strip()
    st.subheader(f"1 · Main problem{f' — {name}' if name else ''}")

    comments = main.get("comments") or []
    if comments:
        st.markdown("**What you might have missed**")
        st.markdown("\n".join(f"- {c}" for c in comments))
    else:
        st.markdown("Nothing missed — discussion and plan look complete.")


def _render_other_problems(problems: list[dict]) -> None:
    if not problems:
        return
    st.subheader("2 · Remaining problems")
    for p in problems:
        name = (p.get("problem") or "").strip()
        suggestions = p.get("suggestions") or []
        if suggestions:
            lines = [f"**{name}**"] + [f"- {s}" for s in suggestions]
            st.markdown("\n".join(lines))
        else:
            st.markdown(f"**{name}** — nothing to add.")


def _render_missed_problems(missed: list[dict]) -> None:
    st.subheader("3 · Problems not addressed")
    if not missed:
        st.markdown("None found — the A&P covers everything the note's data raises.")
        return
    for p in missed:
        name = (p.get("problem") or "").strip()
        why = (p.get("why") or "").strip()
        st.markdown(f"- **{name}** — {why}" if why else f"- **{name}**")


def _render_other_thoughts(thoughts: list[str]) -> None:
    if not thoughts:
        return
    st.subheader("4 · Other thoughts")
    st.markdown("\n".join(f"- {t}" for t in thoughts))


def _render_saved_papers(papers: list[dict], seconds, error: str) -> None:
    st.subheader("5 · Related saved papers")
    if error:
        st.warning(f"Saved-papers check failed (the review above is unaffected): {error}")
        return
    if papers:
        for p in papers:
            pmid = p.get("pmid", "")
            title = p.get("title", "")
            year = p.get("year", "")
            journal = p.get("journal", "")
            why = (p.get("why") or "").strip()
            meta = ", ".join(x for x in [journal, year] if x)
            line = f"- [{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"
            if meta:
                line += f" ({meta})"
            if why:
                line += f" — {why}"
            st.markdown(line)
    else:
        st.markdown("None of your saved papers bear on this admission.")
    if seconds is not None:
        st.caption(f"Added {seconds:.1f}s to the analysis.")


def _render_hospitalization_reason(reason: str) -> None:
    reason = reason.strip()
    if not reason:
        return
    st.subheader("6 · Reason care requires hospitalization")
    # Plain text with a copy button — this line gets pasted back into the note.
    st.code(reason, language=None)
