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
    st.subheader("Acid-base interpreter")

    c1, c2, c3 = st.columns(3)
    ph = c1.number_input("pH", value=None, step=0.01, format="%.2f",
                         placeholder="7.40", key="tools_ab_ph")
    pco2 = c2.number_input("pCO₂ (mmHg)", value=None, step=1.0,
                           placeholder="40", key="tools_ab_pco2")
    hco3 = c3.number_input("HCO₃⁻ (mmol/L)", value=None, step=1.0,
                           placeholder="24", key="tools_ab_hco3")

    c4, c5, c6 = st.columns(3)
    na = c4.number_input("Na⁺", value=None, step=1.0,
                         placeholder="140", key="tools_ab_na")
    cl = c5.number_input("Cl⁻", value=None, step=1.0,
                         placeholder="104", key="tools_ab_cl")
    alb = c6.number_input("Albumin g/dL", value=None, step=0.1,
                          format="%.1f", placeholder="4.0", key="tools_ab_alb")

    c7, c8, c9 = st.columns(3)
    lactate = c7.number_input("Lactate mmol/L", value=None, step=0.1,
                              format="%.1f", placeholder="1.0", key="tools_ab_lac")
    bhb = c8.number_input("β-hydroxybutyrate mmol/L", value=None, step=0.1,
                          format="%.1f", placeholder="0.4", key="tools_ab_bhb")
    glucose = c9.number_input("Glucose mg/dL", value=None, step=1.0,
                              placeholder="120", key="tools_ab_glu")

    c10, c11, c12 = st.columns(3)
    bun = c10.number_input("BUN mg/dL", value=None, step=1.0,
                           placeholder="14", key="tools_ab_bun")
    creat = c11.number_input("Creatinine mg/dL", value=None, step=0.1,
                             format="%.1f", placeholder="1.0", key="tools_ab_cr")
    osm = c12.number_input("Measured osmolality mOsm/kg", value=None, step=1.0,
                           placeholder="290", key="tools_ab_osm")

    context = st.text_input(
        "Clinical context (optional — adds an AI interpretation)",
        key="tools_ab_context",
        placeholder="e.g. septic, on metformin, vomiting for 2 days",
    )

    st.caption("Everything is optional — enter a full gas, a BMP, or whatever you have.")

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
