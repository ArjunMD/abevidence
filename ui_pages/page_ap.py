import streamlit as st

from extract import assessment_and_plan

# Soft access gate — keeps casual public visitors out of this (pricier, clinical)
# tool. Not a real credential; it's a shared page password.
_AP_PASSWORD = "BeCareful"


def _one_line(lead: str, plan: list[str]) -> str:
    """Fold a problem's lead-in and its plan items into a single readable bullet."""
    body = ", ".join(plan)
    if not lead:
        return body
    if not body:
        return lead
    # A lead that already ends a sentence starts a new clause; otherwise the plan
    # flows on from it as another comma-separated fragment.
    if lead.endswith((".", ";", ":")):
        return f"{lead} {body}"
    return f"{lead.rstrip(',')}, {body}"


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

    problems = result.get("problems") or []
    if not problems:
        st.info("No problems came back — try adding more detail to the HPI.")
        return

    _render_problems(problems)

    # Utilization-review line: the inpatient-level services that justify the stay.
    reason = (result.get("hospitalization_reason") or "").strip()
    if reason:
        st.markdown(f"**Reason care requires hospitalization:** {reason}")

    _render_discussion(problems)


def _render_problems(problems: list[dict]) -> None:
    for i, p in enumerate(problems, 1):
        st.markdown(f"**{i}. {p.get('problem', '')}**")

        lead = (p.get("lead") or "").strip()
        plan = p.get("plan") or []
        if isinstance(plan, str):
            plan = [plan]
        plan = [str(x).strip() for x in plan if str(x).strip()]

        if i == 1:
            # Admitting diagnosis: narrative lead, then the plan as bullets.
            lines = ([lead] if lead else [])
            lines += [f"- {item}" for item in plan]
        else:
            # Everything else collapses to one bullet: "Due to X, <plan>".
            lines = [f"- {_one_line(lead, plan)}"] if (lead or plan) else []

        if lines:
            st.markdown("\n".join(lines))


def _render_discussion(problems: list[dict]) -> None:
    """The model's reasoning, pulled out of the problems and pooled here so the
    plans stay terse and the pontification can be skimmed in one pass at the end."""
    items = [
        (p.get("problem", ""), (p.get("discussion") or "").strip())
        for p in problems
    ]
    items = [(name, text) for name, text in items if text]
    if not items:
        return

    st.markdown("---")
    st.markdown("**Discussion**")
    for name, text in items:
        st.markdown(f"- **{name}** — {text}" if name else f"- {text}")
