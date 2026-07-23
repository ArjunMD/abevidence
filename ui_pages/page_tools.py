import streamlit as st

from acid_base import interpret as interpret_acid_base
from extract import acid_base_ai_interpretation, icd10_suggestions, medication_dosing


def _render_icd10_finder() -> None:
    st.subheader("ICD-10 code finder")

    description = st.text_input(
        "Presenting diagnosis",
        key="tools_icd10_input",
        placeholder="Describe the presenting diagnosis in your own words",
        label_visibility="collapsed",
    )

    if st.button("Find codes", type="primary", key="tools_icd10_go"):
        if not description.strip():
            st.warning("Describe the diagnosis first.")
        else:
            try:
                with st.spinner("Looking up codes…"):
                    st.session_state["tools_icd10_results"] = icd10_suggestions(description)
                st.session_state["tools_icd10_query"] = description.strip()
            except Exception as e:
                st.session_state.pop("tools_icd10_results", None)
                st.error(f"Lookup failed: {e}")

    results = st.session_state.get("tools_icd10_results")
    if results is None:
        return
    if not results:
        st.info("No codes came back — try rewording the description.")
        return

    rows = ["| Code | Diagnosis | Note |", "| --- | --- | --- |"]
    for r in results:
        rows.append(f"| `{r['code']}` | {r['name']} | {r['note'] or ''} |")
    st.markdown("\n".join(rows))


def _render_dosing_lookup() -> None:
    st.subheader("Medication dosing")

    drug = st.text_input(
        "Medicine",
        key="tools_dosing_input",
        placeholder="Type a medicine (generic or brand)",
        label_visibility="collapsed",
    )

    if st.button("Look up doses", type="primary", key="tools_dosing_go"):
        if not drug.strip():
            st.warning("Type a medicine first.")
        else:
            try:
                with st.spinner("Looking up dosing…"):
                    st.session_state["tools_dosing_results"] = medication_dosing(drug)
            except Exception as e:
                st.session_state.pop("tools_dosing_results", None)
                st.error(f"Lookup failed: {e}")

    results = st.session_state.get("tools_dosing_results")
    if results is None:
        return
    doses = results.get("doses") or []
    if not doses:
        st.info("Didn't recognize that as a medicine — check the spelling.")
        return

    generic = results.get("drug") or ""
    if generic and generic.lower() != drug.strip().lower():
        st.markdown(f"**{generic}**")
    rows = ["| Indication | Dose | Note |", "| --- | --- | --- |"]
    for d in doses:
        rows.append(f"| {d['indication']} | `{d['dose']}` | {d['note'] or ''} |")
    st.markdown("\n".join(rows))
    st.caption("AI-generated — verify before prescribing.")


def _render_acid_base() -> None:
    st.subheader("Acid-base")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2, c3 = st.columns(3)
    ph = _num(c1, "pH", "tools_ab_ph", 0.01, "%.2f")
    pco2 = _num(c2, "pCO₂ (mmHg)", "tools_ab_pco2", 1.0)
    hco3 = _num(c3, "HCO₃⁻ (mmol/L)", "tools_ab_hco3", 1.0)

    c4, c5, c6 = st.columns(3)
    na = _num(c4, "Na⁺", "tools_ab_na", 1.0)
    cl = _num(c5, "Cl⁻", "tools_ab_cl", 1.0)
    alb = _num(c6, "Albumin g/dL", "tools_ab_alb", 0.1, "%.1f")

    c7, c8, c9 = st.columns(3)
    lactate = _num(c7, "Lactate mmol/L", "tools_ab_lac", 0.1, "%.1f")
    bhb = _num(c8, "β-hydroxybutyrate mmol/L", "tools_ab_bhb", 0.1, "%.1f")
    glucose = _num(c9, "Glucose mg/dL", "tools_ab_glu", 1.0)

    c10, c11, c12 = st.columns(3)
    bun = _num(c10, "BUN mg/dL", "tools_ab_bun", 1.0)
    creat = _num(c11, "Creatinine mg/dL", "tools_ab_cr", 0.1, "%.1f")
    osm = _num(c12, "Measured osmolality mOsm/kg", "tools_ab_osm", 1.0)

    context = st.text_input(
        "Clinical context (optional — adds an AI interpretation)",
        key="tools_ab_context",
        placeholder="Clinical context (optional) — e.g. septic, on metformin, vomiting",
        label_visibility="collapsed",
    )

    if st.button("Interpret", type="primary", key="tools_ab_go"):
        anything = any(v is not None for v in (ph, pco2, hco3, na, cl, alb,
                                               lactate, bhb, glucose, bun, creat, osm))
        if not anything and not context.strip():
            st.warning("Enter at least a bicarbonate (or a clinical context).")
            st.session_state.pop("tools_ab_result", None)
            st.session_state.pop("tools_ab_ai", None)
        else:
            result = interpret_acid_base(ph, pco2, hco3, na, cl, alb,
                                         lactate, bhb, glucose, bun, creat, osm)
            st.session_state["tools_ab_result"] = result
            st.session_state.pop("tools_ab_ai", None)
            if context.strip():
                try:
                    with st.spinner("AI interpreting the clinical context…"):
                        st.session_state["tools_ab_ai"] = acid_base_ai_interpretation(
                            context, result["summary"]
                        )
                except Exception as e:
                    st.session_state["tools_ab_ai"] = {"error": str(e)}

    result = st.session_state.get("tools_ab_result")
    if not result:
        return
    for w in result["warnings"]:
        st.warning(w)
    st.markdown(f"**{result['headline']}**")
    st.markdown("\n".join(f"- {s}" for s in result["steps"]))
    if result["differential"]:
        st.markdown("\n".join(f"- {d}" for d in result["differential"]))

    ai = st.session_state.get("tools_ab_ai")
    if ai:
        st.markdown("**AI interpretation** (context-based — verify)")
        if ai.get("error"):
            st.error(f"AI interpretation failed: {ai['error']}")
        else:
            if ai.get("summary"):
                st.markdown(ai["summary"])
            for d in ai.get("differential", []):
                st.markdown(f"- {d}")


def render() -> None:
    st.title("🧰 Tools")
    _render_icd10_finder()
    st.divider()
    _render_dosing_lookup()
    st.divider()
    _render_acid_base()
