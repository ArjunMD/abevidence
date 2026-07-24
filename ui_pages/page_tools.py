import streamlit as st

from acid_base import interpret as interpret_acid_base
from extract import acid_base_ai_interpretation, medication_adverse_effects


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


def _render_med_result(result: dict) -> None:
    """Render one drug's result — either a list of adverse effects or a
    yes/possible/no check against a specific effect."""
    if result.get("mode") == "list":
        effects = result.get("effects") or []
        if not effects:
            st.info(
                f"No adverse effects came back for “{result.get('medication')}” "
                "— check the spelling."
            )
            return
        st.markdown(f"**Common / important adverse effects of {result['medication']}:**")
        for e in effects:
            detail = f" — {e['detail']}" if e.get("detail") else ""
            st.markdown(f"- **{e['effect']}**{detail}")
    else:
        verdict = result.get("verdict")
        header = f"**{result.get('medication')} → {result.get('side_effect')}:**"
        if verdict == "yes":
            st.success(f"{header} reported adverse effect.")
        elif verdict == "no":
            st.error(f"{header} not a recognized adverse effect.")
        else:
            st.warning(f"{header} possible — limited / uncertain association.")
        if result.get("explanation"):
            st.markdown(result["explanation"])


def _render_med_adverse_effects() -> None:
    st.subheader("Medication adverse effects")

    c1, c2 = st.columns(2)
    med = c1.text_input(
        "Medication",
        key="tools_adv_med",
        placeholder="Medication(s), comma-separated — e.g. amiodarone, sertraline",
        label_visibility="collapsed",
    )
    effect = c2.text_input(
        "Side effect (optional)",
        key="tools_adv_effect",
        placeholder="Side effect to check (optional) — e.g. pulmonary fibrosis",
        label_visibility="collapsed",
    )

    if st.button("Look up", type="primary", key="tools_adv_go"):
        # Split on commas; de-dupe case-insensitively while preserving order.
        seen: set[str] = set()
        meds = []
        for m in (part.strip() for part in med.split(",")):
            if m and m.lower() not in seen:
                seen.add(m.lower())
                meds.append(m)
        if not meds:
            st.warning("Enter a medication.")
            st.session_state.pop("tools_adv_results", None)
        else:
            try:
                with st.spinner("Looking up adverse effects…"):
                    st.session_state["tools_adv_results"] = [
                        medication_adverse_effects(m, effect) for m in meds
                    ]
            except Exception as e:
                st.session_state.pop("tools_adv_results", None)
                st.error(f"Lookup failed: {e}")

    results = st.session_state.get("tools_adv_results")
    if not results:
        return

    multi = len([r for r in results if r]) > 1
    first = True
    for result in results:
        if not result:
            continue
        if multi and not first:
            st.divider()
        _render_med_result(result)
        first = False


def render() -> None:
    st.title("🧰 Tools")
    _render_acid_base()
    st.divider()
    _render_med_adverse_effects()
