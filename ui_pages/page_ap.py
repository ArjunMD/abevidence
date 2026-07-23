import streamlit as st

from extract import assessment_and_plan

# Soft access gate — keeps casual public visitors out of this (pricier, clinical)
# tool. Not a real credential; it's a shared page password.
_AP_PASSWORD = "BeCareful"


def render() -> None:
    st.title("🧠 Assessment & Plan")

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
        "Paste a **deidentified** HPI in prose (include the notable vitals, exam, labs, "
        "and imaging). It drafts a problem-based A&P. AI-generated — verify all reasoning, "
        "dosing, and orders. Do not paste PHI."
    )
    hpi = st.text_area(
        "HPI",
        key="ap_hpi",
        height=240,
        placeholder="Deidentified HPI including the notable VS, exam, labs, and imaging…",
        label_visibility="collapsed",
    )
    considerations = st.text_area(
        "Considerations",
        key="ap_considerations",
        height=90,
        placeholder="Optional — elements, differentials, or thoughts the AI should be sure to address…",
        label_visibility="collapsed",
    )

    if st.button("Generate A&P", type="primary", key="ap_go"):
        if not hpi.strip():
            st.warning("Paste an HPI first.")
            st.session_state.pop("ap_result", None)
        else:
            try:
                with st.spinner("Thinking through the case…"):
                    st.session_state["ap_result"] = assessment_and_plan(hpi, considerations)
            except Exception as e:
                st.session_state.pop("ap_result", None)
                st.error(f"Generation failed: {e}")

    result = st.session_state.get("ap_result")
    if not result:
        return

    if result.get("summary"):
        st.markdown(f"**{result['summary']}**")

    problems = result.get("problems") or []
    if not problems:
        st.info("No problems came back — try adding more detail to the HPI.")
        return

    for i, p in enumerate(problems, 1):
        st.markdown(f"**{i}. {p['problem']}**")
        if p.get("assessment"):
            st.markdown(p["assessment"])
        if p.get("plan"):
            st.markdown("\n".join(f"- {item}" for item in p["plan"]))
