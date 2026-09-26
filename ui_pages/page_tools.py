import math

import streamlit as st

from acid_base import interpret as interpret_acid_base
from extract import acid_base_ai_interpretation
from pft import FLOW_LOOP_SHAPES, interpret as interpret_pft
from references_data import EMPIRIC_ABX_MD


# Session-state keys for every lab the acid-base walk can ask for. Values
# survive reruns even while a widget isn't rendered, so labs stay entered as
# the walk's requests come and go.
_AB_KEYS = {
    "na": "tools_ab_na", "k": "tools_ab_k", "cl": "tools_ab_cl",
    "hco3": "tools_ab_hco3", "glucose": "tools_ab_glu",
    "pH": "tools_ab_ph", "pco2": "tools_ab_pco2",
    "albumin": "tools_ab_alb", "lactate": "tools_ab_lac", "bhb": "tools_ab_bhb",
    "phos": "tools_ab_phos", "ca": "tools_ab_ca", "mg": "tools_ab_mg",
    "bun": "tools_ab_bun", "osm": "tools_ab_osm", "be": "tools_ab_be",
    "urine_cl": "tools_ab_ucl",
}


def _ab_kwargs() -> dict:
    """Current value of every walk lab from session state (None if unset)."""
    kw = {name: st.session_state.get(key) for name, key in _AB_KEYS.items()}
    kw["vbg"] = st.session_state.get("tools_ab_gassrc") == "VBG"
    return kw


def _render_steps(result: dict) -> None:
    """Live step-by-step interpretation shared by the acid-base and PFT tools.
    Each first-order value is a bullet with its plugged-in formula beneath it;
    corrections nest under it. Mechanism notes sit in a hover tooltip on the
    "?" badge. Ends with the conclusion, what would sharpen it, and the
    differential."""
    for w in result["warnings"]:
        st.warning(w)
    st.markdown(
        "<style>.ab-q{display:inline-block;width:1.1em;height:1.1em;"
        "line-height:1.1em;text-align:center;border-radius:50%;"
        "background:rgba(128,128,128,.25);font-size:.72em;font-weight:600;"
        "cursor:help;vertical-align:super;}"
        ".ab-calc{display:block;opacity:.65;font-size:.85em;"
        "font-family:ui-monospace,Menlo,monospace;}"
        ".ab ul{margin:0 0 .25rem 0;}</style>",
        unsafe_allow_html=True,
    )

    def _item(s: dict) -> str:
        text = s["text"]
        if s.get("note"):
            note = s["note"].replace('"', "'")
            text += f' <span class="ab-q" title="{note}">?</span>'
        if s.get("calc"):
            calc = s["calc"].replace("\n", "<br>")
            text += f'<span class="ab-calc">{calc}</span>'
        return text

    for sec in result["sections"]:
        if not sec["steps"]:
            continue
        if sec["title"]:
            st.markdown(f"**{sec['title']}**")
        html, open_sub = [], False
        for s in sec["steps"]:
            if s.get("level", 0) == 0:
                if open_sub:
                    html.append("</ul></li>")
                    open_sub = False
                elif html:
                    html.append("</li>")
                html.append(f"<li>{_item(s)}")
            else:
                if not html:        # a correction with no parent line
                    html.append("<li>")
                if not open_sub:
                    html.append("<ul>")
                    open_sub = True
                html.append(f"<li>{_item(s)}</li>")
        html.append("</ul></li>" if open_sub else "</li>")
        st.markdown(
            '<div class="ab"><ol style="margin-bottom:0.5rem">'
            + "".join(html) + "</ol></div>",
            unsafe_allow_html=True,
        )
    st.markdown(f"**Conclusion:** {result['headline']}")
    if result.get("next"):
        st.markdown(f"_{result['next']}_")
    if result["differential"]:
        st.markdown("\n".join(f"- {d}" for d in result["differential"]))


def _render_acid_base() -> None:
    st.subheader("Acid-base — Boston, Copenhagen & Stewart")
    st.caption("Boston, Copenhagen and Stewart all run on whatever you "
               "enter. Albumin and glucose are assumed normal if blank.")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    st.caption("Blood gas — pCO₂ is the respiratory determinant in every approach")
    g1, g2, g3, g4 = st.columns(4)
    _num(g1, "pH", "tools_ab_ph", 0.01, "%.2f")
    _num(g2, "pCO₂ (mmHg)", "tools_ab_pco2", 1.0)
    _num(g3, "Base excess (analyzer)", "tools_ab_be", 0.1, "%.1f")
    g4.selectbox("Gas source", ["ABG", "VBG"],
                 key="tools_ab_gassrc", label_visibility="collapsed")

    st.caption("Strong ions (SID) — Na⁺, K⁺, Cl⁻ mEq/L · lactate mmol/L · "
               "ionized Ca²⁺ mmol/L · Mg²⁺ mg/dL")
    c1, c2, c3, c4 = st.columns(4)
    _num(c1, "Na⁺", "tools_ab_na", 1.0)
    _num(c2, "K⁺", "tools_ab_k", 0.1, "%.1f")
    _num(c3, "Cl⁻", "tools_ab_cl", 1.0)
    _num(c4, "Lactate mmol/L", "tools_ab_lac", 0.1, "%.1f")
    c5, c6, _, _ = st.columns(4)
    _num(c5, "Ionized Ca²⁺ mmol/L", "tools_ab_ca", 0.01, "%.2f")
    _num(c6, "Mg²⁺ mg/dL", "tools_ab_mg", 0.1, "%.1f")

    st.caption("Bicarbonate & weak acids (Atot) — CO₂ mEq/L · albumin g/dL · "
               "phosphate mg/dL. If your lab reports in mmol/L: Mg × 2.43, "
               "phosphate × 3.1 → mg/dL.")
    c7, c8, c9, _ = st.columns(4)
    _num(c7, "CO₂ (HCO₃⁻)", "tools_ab_hco3", 1.0)
    _num(c8, "Albumin g/dL", "tools_ab_alb", 0.1, "%.1f")
    _num(c9, "Phosphate mg/dL", "tools_ab_phos", 0.1, "%.1f")

    st.caption("Accessory — differential tools, not framework variables: "
               "glucose mg/dL · β-hydroxybutyrate mmol/L · BUN mg/dL · "
               "osmolality mOsm/kg · urine Cl⁻ mEq/L")
    c10, c11, c12, c13 = st.columns(4)
    _num(c10, "Glucose mg/dL", "tools_ab_glu", 1.0)
    _num(c11, "β-hydroxybutyrate mmol/L", "tools_ab_bhb", 0.1, "%.1f")
    _num(c12, "BUN mg/dL", "tools_ab_bun", 1.0)
    _num(c13, "Measured osmolality mOsm/kg", "tools_ab_osm", 1.0)
    c14, _, _, _ = st.columns(4)
    _num(c14, "Urine Cl⁻ mEq/L", "tools_ab_ucl", 1.0)

    kw = _ab_kwargs()
    anything = any(v is not None for n, v in kw.items() if n != "vbg")

    result = None
    if anything:
        result = interpret_acid_base(**kw)
        _render_steps(result)

    context = st.text_input(
        "Clinical context (optional — adds an AI interpretation)",
        key="tools_ab_context",
        placeholder="Clinical context (optional) — e.g. septic, on metformin, vomiting",
        label_visibility="collapsed",
    )

    if st.button("AI interpretation", key="tools_ab_go"):
        if not context.strip():
            st.warning("Enter a clinical context for the AI layer.")
            st.session_state.pop("tools_ab_ai", None)
        else:
            try:
                with st.spinner("AI interpreting the clinical context…"):
                    st.session_state["tools_ab_ai"] = acid_base_ai_interpretation(
                        context, result["summary"] if result else ""
                    )
            except Exception as e:
                st.session_state["tools_ab_ai"] = {"error": str(e)}

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


# PFT rows by report section: (param key, row label with unit). Each row takes
# the report's measured value, % predicted, LLN and z-score — any subset.
_PFT_GROUPS = [
    ("Spirometry (pre-bronchodilator)", [
        ("fev1", "FEV1 (L)"), ("fvc", "FVC (L)"), ("ratio", "FEV1/FVC (%)"),
        ("fef2575", "FEF25–75 (L/s)"),
    ]),
    ("Lung volumes", [
        ("tlc", "TLC (L)"), ("rv", "RV (L)"), ("rv_tlc", "RV/TLC (%)"),
        ("frc", "FRC (L)"), ("ivc", "IVC (L)"),
    ]),
    ("Diffusion", [
        ("dlco", "DLCO"), ("dlco_adj", "DLCO Hb-adjusted"), ("va", "VA (L)"),
        ("kco", "KCO (DL/VA)"),
    ]),
]
_PFT_FIELDS = [("meas", "Measured"), ("pct", "% pred"), ("lln", "LLN"), ("z", "z-score")]
_PFT_COLS = [1.4, 1, 1, 1, 1]


def _render_pft() -> None:
    st.subheader("PFTs")
    st.caption("Enter what the report shows — measured, % predicted, LLN and/or "
               "z-score for any row. Abnormal = beyond the LLN (z ±1.645, ATS/ERS "
               "2022); rows without LLN or z fall back to fixed % cutoffs.")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    rows: dict[str, dict] = {}
    for title, params in _PFT_GROUPS:
        st.caption(title)
        for key, label in params:
            cols = st.columns(_PFT_COLS, vertical_alignment="center")
            cols[0].markdown(label)
            rows[key] = {
                field: _num(col, ph, f"tools_pft_{key}_{field}",
                            0.1 if field == "z" else 0.01 if field == "meas" else 1.0,
                            "%.2f" if field in ("z", "meas") else None)
                for col, (field, ph) in zip(cols[1:], _PFT_FIELDS)
            }
        if title.startswith("Spirometry"):
            cols = st.columns(_PFT_COLS, vertical_alignment="center")
            cols[0].markdown("Post-bronchodilator")
            fev1_post = _num(cols[1], "FEV1 post (L)", "tools_pft_fev1_post", 0.01, "%.2f")
            fvc_post = _num(cols[2], "FVC post (L)", "tools_pft_fvc_post", 0.01, "%.2f")
        if title == "Diffusion":
            cols = st.columns(_PFT_COLS, vertical_alignment="center")
            cols[0].markdown("Hb adjustment")
            hb = _num(cols[1], "Hb g/dL", "tools_pft_hb", 0.1, "%.1f")
            sex = cols[2].selectbox("Sex", ["Male", "Female / <15 y"],
                                    key="tools_pft_sex", label_visibility="collapsed")

    st.caption("Flow-volume loop — shape as seen · flows in L/s")
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    shape = f1.selectbox("Loop shape", list(FLOW_LOOP_SHAPES), key="tools_pft_loop",
                         label_visibility="collapsed")
    pef = _num(f2, "PEF (L/s)", "tools_pft_pef", 0.1, "%.2f")
    fef50 = _num(f3, "FEF50 (L/s)", "tools_pft_fef50", 0.1, "%.2f")
    fif50 = _num(f4, "FIF50 (L/s)", "tools_pft_fif50", 0.1, "%.2f")

    entered = [v for r in rows.values() for v in r.values()]
    entered += [fev1_post, fvc_post, pef, fef50, fif50]
    if all(v is None for v in entered) and FLOW_LOOP_SHAPES.get(shape) is None:
        return
    _render_steps(interpret_pft(
        rows, fev1_post=fev1_post, fvc_post=fvc_post, hb=hb, male=sex == "Male",
        loop_shape=shape, pef=pef, fef50=fef50, fif50=fif50,
    ))


# At the standard 25 mm/s paper speed one small box is 1 mm = 0.04 s.
_SMALL_BOX_S = 0.04


def _render_qtc() -> None:
    st.subheader("QTc (Fridericia)")

    c1, c2 = st.columns(2)
    qt_boxes = c1.number_input(
        "QT (small boxes)", value=None, step=0.5,
        placeholder="QT — small boxes (assumes 25 mm/s)",
        label_visibility="collapsed", key="tools_qtc_qt_boxes",
    )
    hr = c2.number_input("Heart rate (bpm)", value=None, step=1.0,
                         placeholder="Heart rate (bpm)", label_visibility="collapsed",
                         key="tools_qtc_hr")

    if st.button("Compute", type="primary", key="tools_qtc_go"):
        if qt_boxes is None or hr is None:
            st.warning("Enter both the QT (in small boxes) and the heart rate.")
            st.session_state.pop("tools_qtc_result", None)
        elif qt_boxes <= 0 or hr <= 0:
            st.warning("QT and heart rate must be positive.")
            st.session_state.pop("tools_qtc_result", None)
        else:
            qt = qt_boxes * _SMALL_BOX_S * 1000.0
            # Fridericia: QTcF = QT / cube_root(RR), RR = 60 / HR (seconds).
            rr = 60.0 / hr
            qtcf = qt / (rr ** (1.0 / 3.0))
            st.session_state["tools_qtc_result"] = {"qtcf": qtcf, "qt": qt, "rr": rr}

    result = st.session_state.get("tools_qtc_result")
    if not result:
        return

    qtcf = result["qtcf"]
    st.markdown(
        f"**QTcF = {qtcf:.0f} ms** (Fridericia; QT {result['qt']:.0f} ms, "
        f"RR {result['rr']:.2f} s)"
    )
    if qtcf >= 500:
        st.error("High risk (≥500 ms) — markedly prolonged; risk of torsades de pointes.")
    elif qtcf >= 450:
        st.warning("Borderline (450–499 ms).")
    else:
        st.success("Normal (<450 ms).")


# Each item: (label, [(points, description), ...]). "UN" (untestable) choices
# score 0 — the standard scores them as not scored rather than as a deficit.
_NIHSS_ITEMS: list[tuple[str, list[tuple[int, str]]]] = [
    ("1a. Level of consciousness", [
        (0, "Alert, keenly responsive"),
        (1, "Not alert, arousable by minor stimulation"),
        (2, "Not alert, requires repeated stimulation"),
        (3, "Unresponsive, or reflex motor / autonomic responses only"),
    ]),
    ("1b. LOC questions (month, age)", [
        (0, "Both correct"),
        (1, "One correct"),
        (2, "Neither correct"),
    ]),
    ("1c. LOC commands (open/close eyes, grip/release)", [
        (0, "Both tasks performed"),
        (1, "One task performed"),
        (2, "Neither task performed"),
    ]),
    ("2. Best gaze", [
        (0, "Normal"),
        (1, "Partial gaze palsy"),
        (2, "Forced deviation / total gaze paresis"),
    ]),
    ("3. Visual fields", [
        (0, "No visual loss"),
        (1, "Partial hemianopia"),
        (2, "Complete hemianopia"),
        (3, "Bilateral hemianopia / cortically blind"),
    ]),
    ("4. Facial palsy", [
        (0, "Normal symmetric movement"),
        (1, "Minor paralysis (flattened nasolabial fold)"),
        (2, "Partial paralysis (total or near-total lower face)"),
        (3, "Complete paralysis of one or both sides"),
    ]),
    ("5a. Motor — left arm", [
        (0, "No drift for 10 s"),
        (1, "Drift, does not hit bed"),
        (2, "Some effort against gravity, cannot sustain"),
        (3, "No effort against gravity, falls"),
        (4, "No movement"),
        (0, "UN — amputation or joint fusion"),
    ]),
    ("5b. Motor — right arm", [
        (0, "No drift for 10 s"),
        (1, "Drift, does not hit bed"),
        (2, "Some effort against gravity, cannot sustain"),
        (3, "No effort against gravity, falls"),
        (4, "No movement"),
        (0, "UN — amputation or joint fusion"),
    ]),
    ("6a. Motor — left leg", [
        (0, "No drift for 5 s"),
        (1, "Drift, does not hit bed"),
        (2, "Some effort against gravity, cannot sustain"),
        (3, "No effort against gravity, falls"),
        (4, "No movement"),
        (0, "UN — amputation or joint fusion"),
    ]),
    ("6b. Motor — right leg", [
        (0, "No drift for 5 s"),
        (1, "Drift, does not hit bed"),
        (2, "Some effort against gravity, cannot sustain"),
        (3, "No effort against gravity, falls"),
        (4, "No movement"),
        (0, "UN — amputation or joint fusion"),
    ]),
    ("7. Limb ataxia", [
        (0, "Absent"),
        (1, "Present in one limb"),
        (2, "Present in two limbs"),
        (0, "UN — amputation or joint fusion"),
    ]),
    ("8. Sensory", [
        (0, "Normal"),
        (1, "Mild-to-moderate loss"),
        (2, "Severe to total loss"),
    ]),
    ("9. Best language", [
        (0, "No aphasia"),
        (1, "Mild-to-moderate aphasia"),
        (2, "Severe aphasia"),
        (3, "Mute, global aphasia"),
    ]),
    ("10. Dysarthria", [
        (0, "Normal"),
        (1, "Mild-to-moderate, slurred but intelligible"),
        (2, "Severe, unintelligible or mute"),
        (0, "UN — intubated or other physical barrier"),
    ]),
    ("11. Extinction / inattention", [
        (0, "No abnormality"),
        (1, "Inattention to one modality"),
        (2, "Profound hemi-inattention, more than one modality"),
    ]),
]


def _score_select(col, label: str, key: str, options: list[tuple[int, str]]) -> int:
    """Selectbox over (points, description) choices; returns the points. An 'UN'
    description is shown as-is rather than prefixed with its 0."""
    def _fmt(o: tuple[int, str]) -> str:
        pts, desc = o
        return desc if desc.startswith("UN") else f"{pts} — {desc}"

    return col.selectbox(label, options, key=key, format_func=_fmt)[0]


def _render_nihss() -> None:
    st.subheader("NIHSS")
    st.caption("Score each item on the first attempt as observed.")

    total = 0
    for i in range(0, len(_NIHSS_ITEMS), 2):
        cols = st.columns(2)
        for j, (label, options) in enumerate(_NIHSS_ITEMS[i:i + 2]):
            total += _score_select(cols[j], label, f"tools_nihss_{i + j}", options)

    if total == 0:
        band = "No stroke symptoms"
    elif total <= 4:
        band = "Minor stroke"
    elif total <= 15:
        band = "Moderate stroke"
    elif total <= 20:
        band = "Moderate-to-severe stroke"
    else:
        band = "Severe stroke"

    st.markdown(f"**NIHSS = {total} / 42** — {band}")


_GCS_EYE = [
    (4, "Spontaneous"),
    (3, "To sound"),
    (2, "To pressure"),
    (1, "None"),
]
_GCS_VERBAL = [
    (5, "Oriented"),
    (4, "Confused"),
    (3, "Words, not conversational"),
    (2, "Sounds only"),
    (1, "None"),
]
_GCS_MOTOR = [
    (6, "Obeys commands"),
    (5, "Localizing to pain"),
    (4, "Normal flexion / withdrawal"),
    (3, "Abnormal flexion (decorticate)"),
    (2, "Extension (decerebrate)"),
    (1, "None"),
]


def _render_gcs() -> None:
    st.subheader("GCS")

    intubated = st.checkbox("Intubated / verbal not testable", key="tools_gcs_intubated")

    c1, c2, c3 = st.columns(3)
    eye = _score_select(c1, "Eye opening", "tools_gcs_eye", _GCS_EYE)
    if intubated:
        c2.selectbox("Verbal response", ["1T — intubated"], disabled=True,
                     key="tools_gcs_verbal_t")
        verbal = 1
    else:
        verbal = _score_select(c2, "Verbal response", "tools_gcs_verbal", _GCS_VERBAL)
    motor = _score_select(c3, "Motor response", "tools_gcs_motor", _GCS_MOTOR)

    total = eye + verbal + motor
    suffix = "T" if intubated else ""
    breakdown = f"E{eye} V{verbal}{suffix} M{motor}"
    st.markdown(f"**GCS = {total}{suffix} / 15** ({breakdown})")

    if total <= 8:
        st.error("Severe (≤8) — consider a definitive airway.")
    elif total <= 12:
        st.warning("Moderate (9–12).")
    else:
        st.success("Mild (13–15).")


# Ganzoni: deficit (mg) = weight (kg) × (target − actual) Hb (g/dL) × 2.4 + stores.
# The 2.4 folds in Hb being 0.34% iron by weight, a 70 mL/kg blood volume, and the
# g/dL → g/L conversion (0.0034 × 70 × 10).
_GANZONI_FACTOR = 2.4
_GANZONI_DEFAULT_TARGET_HB = 15.0
# Iron stores to replace on top of the red-cell deficit. Adults only — the
# weight-based pediatric figure is deliberately not implemented here.
_IRON_STORES_MG = 500.0
# Sodium ferric gluconate complex (Ferrlecit): 62.5 mg elemental iron per 5 mL
# ampule, and no more than 125 mg (2 ampules) per session.
_FERRIC_GLUCONATE_DOSE_MG = 125.0
# Past roughly this many sessions the visit burden usually beats the drug cost,
# and a single-dose formulation is the more sensible choice.
_FERRIC_GLUCONATE_SESSION_NUDGE = 8


def _render_iron_deficit() -> None:
    st.subheader("Iron deficit (Ganzoni)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2, c3 = st.columns(3)
    weight = _num(c1, "Actual body weight (kg)", "tools_iron_weight", 1.0)
    hb = _num(c2, "Current Hb (g/dL)", "tools_iron_hb", 0.1, "%.1f")
    target = _num(c3, "Target Hb (g/dL) — default 15", "tools_iron_target", 0.1, "%.1f")

    if st.button("Compute", type="primary", key="tools_iron_go"):
        if weight is None or hb is None:
            st.warning("Enter at least a weight and the current hemoglobin.")
            st.session_state.pop("tools_iron_result", None)
        elif weight <= 0 or hb <= 0 or (target is not None and target <= 0):
            st.warning("Weight and hemoglobin must be positive.")
            st.session_state.pop("tools_iron_result", None)
        else:
            tgt = _GANZONI_DEFAULT_TARGET_HB if target is None else target
            stores = _IRON_STORES_MG
            # Already at or above target: nothing to replace in the red-cell mass,
            # but the stores still need filling. Clamp so a high Hb can't subtract.
            red_cell = max(0.0, weight * (tgt - hb) * _GANZONI_FACTOR)
            deficit = red_cell + stores
            st.session_state["tools_iron_result"] = {
                "deficit": deficit, "red_cell": red_cell, "stores": stores,
                "weight": weight, "hb": hb, "target": tgt,
                "doses": math.ceil(deficit / _FERRIC_GLUCONATE_DOSE_MG),
            }

    result = st.session_state.get("tools_iron_result")
    if not result:
        return

    doses = result["doses"]
    st.markdown(f"**Total iron deficit ≈ {result['deficit']:.0f} mg elemental iron**")
    st.markdown("\n".join([
        f"- Red-cell deficit: {result['weight']:.0f} kg × "
        f"({result['target']:.1f} − {result['hb']:.1f} g/dL) × {_GANZONI_FACTOR} "
        f"= **{result['red_cell']:.0f} mg**",
        f"- Iron stores: **{result['stores']:.0f} mg** (adult repletion)",
    ]))

    if result["red_cell"] == 0:
        st.info("Hb is already at or above target — this is store repletion only.")

    st.markdown(
        f"**Sodium ferric gluconate (Ferrlecit): {doses} × 125 mg** "
        f"= {doses * _FERRIC_GLUCONATE_DOSE_MG:.0f} mg cumulative"
    )
    st.markdown("\n".join([
        "- 125 mg (two 5 mL ampules, 62.5 mg each) in 100 mL NS over ~1 h, or "
        "undiluted at ≤12.5 mg/min",
        "- 125 mg is the ceiling for a single session — larger deficits mean more visits, "
        "not a bigger dose",
        "- Recheck Hb, ferritin, and TSAT ~4 weeks after the last dose rather than between doses",
    ]))

    if doses >= _FERRIC_GLUCONATE_SESSION_NUDGE:
        st.warning(
            f"{doses} separate infusions — at this deficit a single-dose formulation "
            "(ferric carboxymaltose or ferric derisomaltose) is usually the better call "
            "unless the patient is already coming in for hemodialysis."
        )


# Corrected Na = measured Na + factor × (glucose − 100) / 100.
_NA_GLUCOSE_BASELINE = 100.0
_KATZ_FACTOR = 1.6      # Katz 1973 — theoretical, dilutional; the classic teaching number.
_HILLIER_FACTOR = 2.4   # Hillier 1999 — measured in volunteers; fits the data better.
# Above this glucose Hillier found the relationship steepens (closer to 4 mmol/L per
# 100 mg/dL), so both factors under-correct and the tool says so rather than guessing.
_NA_NONLINEAR_GLUCOSE = 400.0


def _render_corrected_sodium() -> None:
    st.subheader("Corrected Na (hyperglycemia)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2 = st.columns(2)
    na = _num(c1, "Measured Na⁺ (mmol/L)", "tools_cna_na", 1.0)
    glucose = _num(c2, "Glucose (mg/dL)", "tools_cna_glu", 1.0)

    if st.button("Compute", type="primary", key="tools_cna_go"):
        if na is None or glucose is None:
            st.warning("Enter both the measured sodium and the glucose.")
            st.session_state.pop("tools_cna_result", None)
        elif na <= 0 or glucose <= 0:
            st.warning("Sodium and glucose must be positive.")
            st.session_state.pop("tools_cna_result", None)
        else:
            # Below the baseline there is no osmotic pull to undo; correcting would
            # push the sodium the wrong way, so clamp the excess at zero.
            excess = max(0.0, glucose - _NA_GLUCOSE_BASELINE) / 100.0
            st.session_state["tools_cna_result"] = {
                "na": na, "glucose": glucose, "excess": excess,
                "katz": na + _KATZ_FACTOR * excess,
                "hillier": na + _HILLIER_FACTOR * excess,
            }

    result = st.session_state.get("tools_cna_result")
    if not result:
        return

    katz, hillier = result["katz"], result["hillier"]
    if result["excess"] == 0:
        st.info(
            f"Glucose {result['glucose']:.0f} mg/dL is at or below 100 — no correction "
            f"applies. Sodium stands at {result['na']:.0f} mmol/L."
        )
        return

    # Katz is the guideline-supported factor; Hillier is preferred once the glucose
    # is high enough that the relationship has steepened. Mark whichever applies to
    # the glucose actually entered.
    hillier_preferred = result["glucose"] > _NA_NONLINEAR_GLUCOSE
    katz_tag = "" if hillier_preferred else " ← use this"
    hillier_tag = " ← use this" if hillier_preferred else ""

    # Headline and verdict both follow whichever factor applies, so the tool never
    # tells you to use one number while banding on the other.
    corrected = hillier if hillier_preferred else katz
    pref_name = "Hillier, 2.4" if hillier_preferred else "Katz, 1.6"
    other_name = "Katz" if hillier_preferred else "Hillier"

    st.markdown(f"**Corrected Na⁺ ≈ {corrected:.1f} mmol/L** ({pref_name})")
    st.markdown("\n".join([
        f"- Hillier (2.4), preferred above 400 mg/dL: {result['na']:.0f} + 2.4 × "
        f"({result['glucose']:.0f} − 100)/100 = **{hillier:.1f} mmol/L**{hillier_tag}",
        f"- Katz (1.6), guideline-supported: {result['na']:.0f} + 1.6 × "
        f"({result['glucose']:.0f} − 100)/100 = **{katz:.1f} mmol/L**{katz_tag}",
        f"- Correction adds {katz - result['na']:.1f}–{hillier - result['na']:.1f} mmol/L "
        f"to the measured {result['na']:.0f}",
    ]))

    if corrected < 135:
        st.error(
            f"True hyponatremia — still {corrected:.1f} mmol/L after correcting. "
            "The low sodium is not just a glucose artifact; work it up on its own."
        )
    elif corrected > 145:
        st.warning(
            f"Corrected Na {corrected:.1f} mmol/L is hypernatremic — a substantial free-water "
            "deficit is hiding behind the dilutional reading. Typical of HHS/DKA, and it "
            "argues for hypotonic fluid once the patient is volume-resuscitated."
        )
    elif result["na"] < 135:
        st.success(
            f"Translocational (dilutional) hyponatremia — measured {result['na']:.0f} "
            f"corrects into the normal range at {corrected:.1f} mmol/L. Treat the glucose, "
            "not the sodium."
        )
    else:
        st.success(f"Corrected Na {corrected:.1f} mmol/L is within the normal range.")

    # The two factors can land in different bands, in which case the verdict above is
    # an artifact of which one applies. Say so rather than showing one confident answer.
    if any((katz < cut) != (hillier < cut) for cut in (135.0, 145.0)):
        st.caption(
            f"The two formulas disagree here — Katz gives {katz:.1f} and Hillier "
            f"{hillier:.1f}, which fall either side of a cutoff. The verdict above follows "
            f"{pref_name.split(',')[0]}; {other_name} would band it differently, so recheck "
            "the sodium as the glucose comes down."
        )

    if result["glucose"] > _NA_NONLINEAR_GLUCOSE:
        st.caption(
            f"Glucose is above {_NA_NONLINEAR_GLUCOSE:.0f} mg/dL, where the relationship "
            "steepens (Hillier suggests nearer 4 mmol/L per 100 mg/dL). Both factors "
            "likely under-correct here — read the number as a lower bound."
        )


# APRI = (AST / AST ULN) × 100 / platelets (×10⁹/L). Wai 2003, derived in chronic
# hepatitis C; the lab's own AST upper limit of normal is what the ratio is built
# on, so it is an input rather than a fixed number.
_APRI_DEFAULT_AST_ULN = 40.0
# Wai's two-cutoff scheme: below the low cutoff significant fibrosis (F2+) is
# effectively ruled out, above the high cutoff it is ruled in, and the span
# between them is the indeterminate zone the score cannot resolve. WHO's 2015
# hepatitis B guidance uses >2 for cirrhosis.
_APRI_FIBROSIS_RULE_OUT = 0.5
_APRI_FIBROSIS_RULE_IN = 1.5
_APRI_CIRRHOSIS = 2.0


def _render_apri() -> None:
    st.subheader("APRI (AST-to-platelet ratio index)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2, c3 = st.columns(3)
    ast = _num(c1, "AST (U/L)", "tools_apri_ast", 1.0)
    uln = _num(c2, "AST upper limit of normal (default 40)", "tools_apri_uln", 1.0)
    plt = _num(c3, "Platelets (×10⁹/L)", "tools_apri_plt", 1.0)

    if st.button("Compute", type="primary", key="tools_apri_go"):
        if ast is None or plt is None:
            st.warning("Enter at least an AST and a platelet count.")
            st.session_state.pop("tools_apri_result", None)
        elif ast <= 0 or plt <= 0 or (uln is not None and uln <= 0):
            st.warning("AST, platelets, and the upper limit of normal must be positive.")
            st.session_state.pop("tools_apri_result", None)
        else:
            limit = _APRI_DEFAULT_AST_ULN if uln is None else uln
            st.session_state["tools_apri_result"] = {
                "ast": ast, "uln": limit, "plt": plt,
                "apri": (ast / limit) * 100.0 / plt,
            }

    result = st.session_state.get("tools_apri_result")
    if not result:
        return

    apri = result["apri"]
    st.markdown(f"**APRI = {apri:.2f}**")
    st.markdown(
        f"- ({result['ast']:.0f} / {result['uln']:.0f}) × 100 / "
        f"{result['plt']:.0f} = **{apri:.2f}**"
    )

    if apri >= _APRI_CIRRHOSIS:
        st.error(
            f"≥{_APRI_CIRRHOSIS:.0f} — cirrhosis likely (WHO cutoff in chronic hepatitis B). "
            "Specific but not sensitive: a lower score does not clear the liver."
        )
    elif apri >= _APRI_FIBROSIS_RULE_IN:
        st.warning(
            f"≥{_APRI_FIBROSIS_RULE_IN} — significant fibrosis (F2+) likely. "
            "Confirm with elastography or a validated panel before acting on it."
        )
    elif apri > _APRI_FIBROSIS_RULE_OUT:
        st.info(
            f"Between {_APRI_FIBROSIS_RULE_OUT} and {_APRI_FIBROSIS_RULE_IN} — indeterminate. "
            "This is the band APRI cannot resolve; it neither rules fibrosis in nor out."
        )
    else:
        st.success(
            f"≤{_APRI_FIBROSIS_RULE_OUT} — significant fibrosis unlikely. This is where the "
            "score performs best (high negative predictive value)."
        )

    st.caption(
        "Derived and validated in chronic viral hepatitis. Anything else that moves either "
        "term — acute hepatitis, alcoholic hepatitis, hemolysis or muscle injury raising AST, "
        "ITP or splenic sequestration dropping platelets — distorts the ratio, so read it "
        "alongside the clinical picture rather than as a standalone stage."
    )


# R factor = (ALT / ALT ULN) / (ALP / ALP ULN). Classifies the pattern of liver
# injury (Hy's law / RUCAM convention, adopted in the ACG DILI guideline). ULNs
# default to Arjun's lab (ALT 65, ALP 116) but stay editable inputs since the
# ratio is built on the reporting lab's own limits.
_R_DEFAULT_ALT_ULN = 65.0
_R_DEFAULT_ALP_ULN = 116.0
# ≥5 hepatocellular, ≤2 cholestatic, in between mixed.
_R_HEPATOCELLULAR = 5.0
_R_CHOLESTATIC = 2.0


def _render_r_factor() -> None:
    st.subheader("R factor (pattern of liver injury)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2 = st.columns(2)
    alt = _num(c1, "ALT (U/L)", "tools_rf_alt", 1.0)
    alt_uln = _num(c2, f"ALT upper limit of normal (default {_R_DEFAULT_ALT_ULN:.0f})",
                   "tools_rf_alt_uln", 1.0)

    c3, c4 = st.columns(2)
    alp = _num(c3, "ALP (U/L)", "tools_rf_alp", 1.0)
    alp_uln = _num(c4, f"ALP upper limit of normal (default {_R_DEFAULT_ALP_ULN:.0f})",
                   "tools_rf_alp_uln", 1.0)

    if st.button("Compute", type="primary", key="tools_rf_go"):
        if alt is None or alp is None:
            st.warning("Enter both the ALT and the ALP.")
            st.session_state.pop("tools_rf_result", None)
        elif alt <= 0 or alp <= 0 or (alt_uln is not None and alt_uln <= 0) \
                or (alp_uln is not None and alp_uln <= 0):
            st.warning("ALT, ALP, and the upper limits of normal must be positive.")
            st.session_state.pop("tools_rf_result", None)
        else:
            alt_limit = _R_DEFAULT_ALT_ULN if alt_uln is None else alt_uln
            alp_limit = _R_DEFAULT_ALP_ULN if alp_uln is None else alp_uln
            st.session_state["tools_rf_result"] = {
                "alt": alt, "alt_uln": alt_limit, "alp": alp, "alp_uln": alp_limit,
                "r": (alt / alt_limit) / (alp / alp_limit),
            }

    result = st.session_state.get("tools_rf_result")
    if not result:
        return

    r = result["r"]
    st.markdown(f"**R = {r:.1f}**")
    st.markdown(
        f"- ({result['alt']:.0f} / {result['alt_uln']:.0f}) ÷ "
        f"({result['alp']:.0f} / {result['alp_uln']:.0f}) = **{r:.1f}**"
    )

    if r >= _R_HEPATOCELLULAR:
        st.error(
            f"≥{_R_HEPATOCELLULAR:.0f} — hepatocellular pattern. If the bilirubin is also "
            "≥2× ULN without significant cholestasis, that is Hy's law territory "
            "(~10% mortality in drug-induced cases)."
        )
    elif r <= _R_CHOLESTATIC:
        st.warning(
            f"≤{_R_CHOLESTATIC:.0f} — cholestatic pattern. Image the biliary tree before "
            "pinning it on a drug; obstruction and infiltration produce the same ratio."
        )
    else:
        st.info(
            f"Between {_R_CHOLESTATIC:.0f} and {_R_HEPATOCELLULAR:.0f} — mixed pattern."
        )

    st.caption(
        "Compute R from the first labs at presentation — the pattern drifts cholestatic as "
        "the injury evolves. It classifies the injury pattern (and steers the differential "
        "and workup); it is not a severity score."
    )


# Retic % is corrected for the degree of anemia against a normal hematocrit, then
# divided by a maturation factor: the more anemic the marrow, the earlier retics
# are released and the longer they persist in blood, which otherwise inflates the
# count. Factors are the standard Hct-banded table.
_RETIC_NORMAL_HCT = 45.0
_RETIC_MATURATION_FACTORS = [
    (40.0, 1.0),
    (35.0, 1.5),
    (25.0, 2.0),
    (20.0, 2.5),
]
_RETIC_MATURATION_FLOOR = 3.0
# An RPI at or above this means the marrow is answering the anemia (blood loss,
# hemolysis); below it the response is inadequate for the degree of anemia.
_RPI_ADEQUATE = 2.0


def _retic_maturation_factor(hct: float) -> float:
    for floor, factor in _RETIC_MATURATION_FACTORS:
        if hct >= floor:
            return factor
    return _RETIC_MATURATION_FLOOR


def _render_retic_index() -> None:
    st.subheader("Reticulocyte production index")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2 = st.columns(2)
    retic = _num(c1, "Reticulocytes (%)", "tools_rpi_retic", 0.1, "%.1f")
    hct = _num(c2, "Hematocrit (%)", "tools_rpi_hct", 0.1, "%.1f")

    if st.button("Compute", type="primary", key="tools_rpi_go"):
        if retic is None or hct is None:
            st.warning("Enter both the reticulocyte percentage and the hematocrit.")
            st.session_state.pop("tools_rpi_result", None)
        elif retic < 0 or hct <= 0:
            st.warning("Reticulocytes cannot be negative and hematocrit must be positive.")
            st.session_state.pop("tools_rpi_result", None)
        else:
            corrected = retic * (hct / _RETIC_NORMAL_HCT)
            factor = _retic_maturation_factor(hct)
            st.session_state["tools_rpi_result"] = {
                "retic": retic, "hct": hct, "corrected": corrected,
                "factor": factor, "rpi": corrected / factor,
            }

    result = st.session_state.get("tools_rpi_result")
    if not result:
        return

    rpi = result["rpi"]
    st.markdown(f"**RPI = {rpi:.1f}**")
    st.markdown("\n".join([
        f"- Corrected retic: {result['retic']:.1f}% × ({result['hct']:.0f} / "
        f"{_RETIC_NORMAL_HCT:.0f}) = **{result['corrected']:.1f}%**",
        f"- Maturation factor at Hct {result['hct']:.0f}: **{result['factor']:.1f}** "
        f"→ RPI = {result['corrected']:.1f} / {result['factor']:.1f} = **{rpi:.1f}**",
    ]))

    # Banding the index against a normal hematocrit would report a marrow failing
    # to answer an anemia the patient does not have, so say that instead.
    if result["hct"] >= _RETIC_NORMAL_HCT:
        st.info(
            "The index only means something in anemia — at a normal hematocrit there is "
            "nothing to correct for and the raw retic percentage is the number to read."
        )
        return

    if rpi >= _RPI_ADEQUATE:
        st.success(
            f"≥{_RPI_ADEQUATE:.0f} — appropriate marrow response. Points to blood loss or "
            "hemolysis rather than a production problem; check LDH, haptoglobin, bilirubin, "
            "smear, and look for bleeding."
        )
    else:
        st.warning(
            f"<{_RPI_ADEQUATE:.0f} — hypoproliferative for this degree of anemia. Work up "
            "production: iron studies, B12/folate, renal function, TSH, marrow infiltration "
            "or suppression."
        )


def _render_empiric_abx() -> None:
    st.subheader("Empiric antibiotics")

    shown = st.session_state.get("tools_abx_shown", False)
    # Rerun on toggle so the button's own label updates in the same click rather
    # than lagging a step behind the reference it controls.
    if st.button("Hide reference" if shown else "See reference",
                 type="primary", key="tools_abx_toggle"):
        st.session_state["tools_abx_shown"] = not shown
        st.rerun()

    if shown:
        st.markdown(EMPIRIC_ABX_MD)


# Acute ischemic stroke only, per AHA/ASA 2019.
_THROMBOLYTIC_CI_MD = """\
#### Acute ischemic stroke (alteplase / tenecteplase) — AHA/ASA 2019

Within 4.5 h of last known well, disabling deficit.

**Contraindicated**
- Intracranial hemorrhage on CT, or extensive clear hypodensity
- Symptoms suggestive of subarachnoid hemorrhage
- Prior intracranial hemorrhage
- Ischemic stroke or significant head trauma within 3 months
- Intracranial or intraspinal surgery within 3 months
- Intra-axial intracranial neoplasm
- GI malignancy, or GI bleed within 21 days
- Infective endocarditis
- Known or suspected aortic arch dissection
- Platelets < 100,000, INR > 1.7, aPTT > 40 s, or PT > 15 s
- Treatment-dose LMWH within 24 h
- DOAC within 48 h, unless drug-specific labs are normal
- Concurrent glycoprotein IIb/IIIa inhibitor
- BP > 185/110 that cannot be brought below it
- Glucose < 50 mg/dL (recheck — hypoglycemia mimics stroke)

**Relative — weigh bleeding risk against deficit**
- Major surgery or serious trauma within 14 days
- GU bleeding within 21 days
- Arterial puncture at a non-compressible site, or lumbar puncture, within 7 days
- MI within 3 months; acute pericarditis; LV/LA thrombus
- Pregnancy or early postpartum
- Seizure at onset with residual deficit (possible postictal Todd paralysis)
- Unruptured aneurysm ≥ 10 mm, untreated AVM, > 10 cerebral microbleeds
- Mild non-disabling deficit (NIHSS 0–5) — no benefit shown
- Pre-existing dementia or severe disability; limited life expectancy
"""


def _render_thrombolytic_ci(tab: str) -> None:
    st.subheader("Thrombolytic contraindications (stroke)")

    # Rendered under more than one tab, so keys carry the tab to stay unique.
    shown_key = f"tools_lysis_shown_{tab}"
    shown = st.session_state.get(shown_key, False)
    # Same toggle as the antibiotics reference: rerun so the label keeps up.
    if st.button("Hide reference" if shown else "See reference",
                 type="primary", key=f"tools_lysis_toggle_{tab}"):
        st.session_state[shown_key] = not shown
        st.rerun()

    if shown:
        st.markdown(_THROMBOLYTIC_CI_MD)


# OMI (occlusion MI) paradigm: ECG patterns of acute coronary occlusion that
# STEMI millimeter criteria miss. Diagnostic findings only.
_OMI_MD = """\
#### The paradigm

Classify MI by whether the culprit artery is **occluded (OMI)** or not (NOMI),
rather than by whether ST elevation meets millimeter criteria.
- About 25% of "NSTEMIs" have a totally occluded culprit artery, mostly
  circumflex or RCA, with higher mortality (Khan 2017 meta-analysis)
- OMI ECG findings identify occlusion with about twice the sensitivity of
  STEMI criteria, and earlier (Meyers 2021, DIFOCCULT)
- Serial ECGs matter: evolution, or T waves pseudonormalizing, is itself a finding

**STEMI criteria, for contrast (4th UDMI):** new J-point elevation ≥ 1 mm in
2 contiguous leads, except V2–V3: ≥ 2 mm men ≥ 40, ≥ 2.5 mm men < 40,
≥ 1.5 mm women.

#### Anterior / LAD

- **Hyperacute T waves:** broad-based, bulky, symmetric T waves, large
  relative to the QRS; often the earliest sign
- **De Winter pattern:** upsloping ST depression at the J point in V1–V6
  running into tall, symmetric T waves, often with slight STE in aVR
- **Wellens syndrome:** biphasic (type A) or deep symmetric inverted (type B)
  T waves in V2–V3, in a now pain-free patient, with preserved R waves.
  A *reperfused* LAD lesion at high risk of reocclusion
- **Terminal QRS distortion:** absence of *both* an S wave and a J wave in
  V2 or V3. Favors anterior OMI over benign early repolarization
- **Smith 4-variable formula** (subtle LAD OMI vs early repolarization):
  0.052 × QTc(Bazett) − 0.151 × QRS amplitude V2 − 0.268 × R amplitude V4
  + 1.062 × STE 60 ms after J in V3. **≥ 18.2 favors LAD occlusion**
- **LV aneurysm vs acute anterior MI:** T/QRS ratio > 0.36 in any of V1–V4,
  or ΣT / ΣQRS in V1–V4 > 0.22, favors acute MI (Smith)

#### Posterior

- **ST depression maximal in V1–V4**, often with tall R waves and upright T
  waves in V2–V3. That's posterior STE seen in the mirror
- Posterior leads **V7–V9: STE ≥ 0.5 mm** (≥ 1 mm in men < 40) confirms,
  but a normal V7–V9 does not exclude it

#### Inferior, lateral and RV

- **Reciprocal ST depression or T inversion in aVL:** very sensitive for
  subtle inferior OMI, and argues against pericarditis
- **South African flag sign:** STE in I, aVL and V2 with reciprocal ST
  depression in III (and often II, aVF). High lateral OMI, typically D1
- **Aslanger pattern:** STE in III only (not II or aVF), ST depression in
  V4–V6 with a positive or terminally positive T, and ST in V1 > V2.
  Inferior OMI with multivessel disease
- **RV involvement:** STE in V1 with inferior STE, STE in III > II;
  right-sided leads **V3R–V4R STE ≥ 0.5 mm** (≥ 1 mm in men < 30)

#### LBBB or ventricular pacing — Smith-modified Sgarbossa

Any one is positive:
- Concordant STE ≥ 1 mm in any lead
- Concordant ST depression ≥ 1 mm in any of V1–V3
- Excessively discordant STE: ST/S ratio ≤ −0.25 (STE ≥ 25% of the depth
  of the preceding S wave) in any lead with ≥ 1 mm STE

Sensitivity about 80–90% with specificity about 99%, versus about 20% for the
original weighted Sgarbossa score.

#### Not OMI on its own

- **Diffuse ST depression with STE in aVR (± V1):** subendocardial ischemia,
  from left main or 3-vessel disease, or supply–demand. Usually not an
  acute occlusion, though high risk

#### ECG territory → POCUS walls and views

| ECG pattern | Usual artery | Walls to look at | Views that show them |
|---|---|---|---|
| Anterior STE V1–V4, hyperacute T, de Winter, Wellens | LAD | Anterior, anteroseptal, apex | PLAX (anteroseptum, top wall) · PSAX mid (anterior, anteroseptal) · A2C (anterior) · A3C (anteroseptal) · all apical views for the apex |
| Septal STE V1–V2 | LAD (septal perforators) | Anteroseptal, inferoseptal | PLAX (anteroseptum) · PSAX (both septal segments) · A4C (inferoseptum) |
| Inferior STE II, III, aVF | RCA (most, ~65–80%) or LCx | Inferior, basal inferoseptal | A2C (bottom wall) · PSAX (inferior, 6 o'clock) |
| Lateral STE I, aVL, V5–V6 | LCx or diagonal | Anterolateral, inferolateral | A4C (lateral wall) · PSAX (anterolateral, inferolateral) · A3C (inferolateral) |
| High lateral: I, aVL (South African flag) | First diagonal | Basal–mid anterolateral, basal anterior | PSAX basal and mid (anterolateral) · A4C basal lateral · A2C basal anterior |
| Posterior: ST depression maximal V1–V4 | LCx, or RCA via PDA/posterolateral | Inferolateral (old term: posterior) | PLAX (bottom wall) · A3C · PSAX (inferolateral, 4–5 o'clock) |
| RV: STE V1 with inferior STE, V3R–V4R | Proximal RCA | RV free wall | A4C (RV free wall, TAPSE) · subcostal 4-chamber · PSAX (RV size) |
| Aslanger pattern | RCA or LCx plus multivessel disease | Inferior, plus possible global hypokinesis | A2C · PSAX |
| Diffuse STD with STE aVR | LM or 3-vessel (subendocardial) | Often no single regional abnormality; may be global | All views |

**Which walls each view shows**
- **PLAX:** anteroseptum (top) and inferolateral wall (bottom)
- **PSAX (basal, mid, apical):** all six segments at each level: anterior,
  anteroseptal, inferoseptal, inferior, inferolateral, anterolateral
- **A4C:** inferoseptum and anterolateral wall, apex, RV free wall
- **A2C:** anterior and inferior walls
- **A3C (apical long axis):** anteroseptal and inferolateral walls
- **Subcostal 4-chamber:** RV free wall and septum

**Reading it**
- Wall motion abnormalities appear within seconds of occlusion, before ECG
  changes, in the ischemic cascade. A normal study during active pain argues
  against a large OMI but does not exclude a small one
- An old infarct also moves abnormally, but looks thinned and bright (scar).
  Acute ischemia has normal wall thickness that fails to thicken
- Posterior (inferolateral) OMI is where echo adds most, since the standard
  ECG has no leads facing that wall
- Coronary anatomy varies: a wrap-around LAD can supply the inferior apex,
  and dominance decides whether the RCA or LCx owns the inferior wall
- Regional hypokinesis that doesn't fit one coronary territory (e.g. apical
  ballooning with basal hyperkinesis) suggests takotsubo
"""

def _render_omi() -> None:
    st.subheader("OMI / STEMI equivalents")

    shown = st.session_state.get("tools_omi_shown", False)
    # Same toggle as the other references: rerun so the label keeps up.
    if st.button("Hide reference" if shown else "See reference",
                 type="primary", key="tools_omi_toggle"):
        st.session_state["tools_omi_shown"] = not shown
        st.rerun()

    if shown:
        st.markdown(_OMI_MD)


# Class I-IV figure on Wikimedia Commons (Jmarchn, CC BY-SA 3.0) — the file the
# Mallampati score article itself uses. Points at the original SVG so tapping it
# opens the figure directly rather than a description page.
_MALLAMPATI_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/0/09/Mallampati.svg"

# Procedure → [(section, [bullet, ...]), ...], in reading order. One entry per
# procedure; sections are filled in as they're written.
_PROCEDURE_CHECKLISTS: dict[str, list[tuple[str, list[str]]]] = {
    "Tracheal intubation": [
        ("Airway evaluation", [
            "Assess 4 aspects: Difficult laryngoscopy, Difficult BVM, Difficult "
            "extraglottic device, and Difficult cricothyrotomy",
            "Difficult laryngoscopy is assessed by LEMONS (very crude)",
            "L = Look externally (simply gestalt)",
            "E = Evaluate 3-3-2. 3 fingers in the mouth, 3 fingers under the chin, "
            "2 fingers from base of chin to hyoid notch",
            f"M = [Mallampati]({_MALLAMPATI_IMAGE_URL})",
            "O = Obstruction/Obesity (muffled voice, stridor)",
            "N = Neck mobility",
            "S = Soiled airway (blood, vomit, secretions)",
            "A single test that is the best is the upper lip bite test",
            "Difficult BVM is assessed by ROMAN",
            "R = Radiation therapy/Resistance (such as COPD/asthma, ARDS)",
            "O = Obesity/Obstruction/OSA",
            "M = Mask seal/Mallampati/Male sex (beard, trauma)",
            "A = Age (> 55)",
            "N = No teeth. (Teeth support the mask. Leave dentures in if possible)",
            "Difficult EGD is assessed by RODS",
            "R = Restriction again (high resistance means high pressures are needed)",
            "O = Obstruction/Obesity",
            "D = Disrupted or distorted airway",
            "S = Short thyromental distance",
            "Difficult cricothyrotomy (skip for now)",
        ]),
        ("Hemodynamics", [
            "Shock index > 0.8 means high risk of post-intubation hypotension",
            "Step 1: Replete volume loss",
            "Fluid resuscitation that does not lead to increased cardiac output or blood "
            "pressure is either because volume is too low, because at least one ventricle "
            "is on the flat part of the FS curve, or significant vasoplegia",
            "Step 2: Reduce unstressed volume and vasoplegia",
            "Underlying vasoplegic states include cirrhosis, hypothyroidism, adrenal "
            "insufficiency, postcardioplegia, and gram-negative sepsis",
            "Start vasopressors before intubation rather than using them as a rescue",
            "Phenylephrine is contraindicated in RHF",
            "Step 3: Augment LV performance",
            "Later — there is a concept (and quantification) of VA (ventriculo-arterial) "
            "uncoupling",
            "If LVEF is < 30% they need an inotrope",
            "Check LVEF after norepinephrine though, as LVEF changes",
            "In patients with HFpEF and LVH, preload optimization is needed",
            "Step 4: Mitigate effect of the induction agent",
            "Consider reduced dose in patients with hemodynamic instability",
            "Step 5: Protect the right ventricle",
            "Measure TAPSE",
            "Always remember the RV spiral of death",
            "Starts with managing LV function though",
            "Fluids dependent on IVC ultrasound",
        ]),
        ("POCUS assessment", [
            "PLAX: LV function, wall thickness (augment preload), pericardial effusion "
            "(diastolic collapse), large RV",
            "PSAX: septal flattening",
            "Apical: VTI variation (volume responsiveness), e' and E/A (restrictive "
            "physiology), "
            "TAPSE, RV dilation, septal flattening",
        ]),
        ("Preoxygenation", [
            "Optimal preoxygenation increases the safe apnea time (when O₂ > 90%)",
            "The process is also called denitrogenation",
            "Upright (or at least reverse Trendelenburg) position maximizes the FRC",
            "Tidal breathing 100% O₂ for 3–5 minutes will adequately "
            "preoxygenate/denitrogenate",
            "Preoxygenation device should be left in place until the laryngoscope blade "
            "enters the mouth",
            "Options if not apneic: NRB at flush flow rate (>40 L/min), NIPPV, HFNO",
            "If patient is apneic or nearly apneic, BVM with PEEP valve must be used",
            "When using NIPPV, start with inspiratory pressure of 10–15 and PEEP of 5",
            "After paralytic is administered, NIPPV should stay in place and jaw thrust "
            "should be performed to maintain a patent airway",
            "DSI is delayed sequence intubation, and is a form of procedural sedation to "
            "facilitate compliance with preoxygenation that is otherwise limited by "
            "agitation. Basically it means low-dose ketamine before RSI. It is not well "
            "studied.",
            "Apneic oxygenation refers to the oxygen delivery during the process of "
            "intubation. It is either NC (placed under the O₂ delivery device initially) "
            "or HFNO.",
            "Rescue oxygenation refers to BVM after a failed intubation attempt or when "
            "O₂ < 93%. If it is difficult, use an extraglottic device.",
        ]),
        ("Metabolic acidosis, induction drugs, and PPV", [
            "Severe metabolic acidosis causes myocardial depression and a blunted "
            "response to catecholamines",
            "Be confident that you can match the active spontaneous ventilation with your "
            "ventilator (start at a TV of 8 cc/kg and RR in the 30s)",
            "Propofol and midazolam cause venodilation and reduce preload",
            "Etomidate is considered hemodynamically neutral",
            "Ketamine can be sympathomimetic but can cause myocardial depression in a "
            "different patient",
            "I don't see why etomidate isn't just standard",
            "PPV reduces venous return",
        ]),
    ],
}

# Sits first in the dropdown so nothing renders until a procedure is picked.
_PROCEDURE_PLACEHOLDER = "Select a procedure…"


def _render_procedures_checklist() -> None:
    st.subheader("Procedures checklist")

    choice = st.selectbox(
        "Procedure",
        options=[_PROCEDURE_PLACEHOLDER, *_PROCEDURE_CHECKLISTS],
        key="tools_proc_choice",
        label_visibility="collapsed",
    )
    if choice == _PROCEDURE_PLACEHOLDER:
        return

    sections = _PROCEDURE_CHECKLISTS.get(choice) or []
    if not sections:
        st.caption("No items yet for this procedure.")
        return

    for name, items in sections:
        st.markdown(f"**{name}**")
        st.markdown("\n".join(f"- {item}" for item in items))


def _temp_c(value: float | None, unit: str) -> float | None:
    """Temperature in °C to one decimal — the resolution the published score
    bands are written at, so a converted °F reading lands in the right band."""
    if value is None:
        return None
    return round((value - 32.0) * 5.0 / 9.0 if unit == "°F" else value, 1)


# Glasgow-Blatchford (Blatchford 2000). Urea bands converted from mmol/L to BUN
# mg/dL (× 2.8): 6.5 / 8 / 10 / 25 mmol/L → 18.2 / 22.4 / 28 / 70 mg/dL.
_GBS_BUN = [(70.0, 6), (28.0, 4), (22.4, 3), (18.2, 2)]
_GBS_HB_MALE = [(13.0, 0), (12.0, 1), (10.0, 3)]
_GBS_HB_FEMALE = [(12.0, 0), (10.0, 1)]
_GBS_HB_FLOOR = 6
_GBS_SBP = [(110.0, 0), (100.0, 1), (90.0, 2)]
_GBS_SBP_FLOOR = 3
_GBS_FLAGS = [
    ("melena", "Melena", 1),
    ("syncope", "Presented with syncope", 2),
    ("liver", "Hepatic disease (known, or clinical/lab evidence)", 2),
    ("hf", "Cardiac failure (known, or clinical/echo evidence)", 2),
]
# Stanley 2017 (BMJ): ≤1 is the cutoff that best identifies patients who will
# need no intervention and survive; ≥7 best predicts need for endoscopic therapy.
_GBS_VERY_LOW = 1
_GBS_ENDOSCOPIC = 7


def _band_down(value: float, bands: list[tuple[float, int]], floor: int) -> int:
    """Points for the first band whose lower bound the value reaches."""
    for lower, pts in bands:
        if value >= lower:
            return pts
    return floor


def _render_glasgow_blatchford() -> None:
    st.subheader("Glasgow-Blatchford (upper GI bleed)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2, c3 = st.columns(3)
    bun = _num(c1, "BUN mg/dL", "tools_gbs_bun", 1.0)
    hb = _num(c2, "Hb g/dL", "tools_gbs_hb", 0.1, "%.1f")
    sex = c3.selectbox("Sex", ["Male", "Female"], key="tools_gbs_sex",
                       label_visibility="collapsed")
    c4, c5, _ = st.columns(3)
    sbp = _num(c4, "Systolic BP mmHg", "tools_gbs_sbp", 1.0)
    hr = _num(c5, "Heart rate bpm", "tools_gbs_hr", 1.0)
    flags = {key: st.checkbox(f"{label} (+{pts})", key=f"tools_gbs_{key}")
             for key, label, pts in _GBS_FLAGS}

    if None in (bun, hb, sbp, hr):
        st.caption("Enter BUN, Hb, systolic BP and heart rate to score.")
        return

    hb_bands = _GBS_HB_MALE if sex == "Male" else _GBS_HB_FEMALE
    parts = [
        (f"BUN {bun:.0f}", _band_down(bun, _GBS_BUN, 0)),
        (f"Hb {hb:.1f} ({sex.lower()})", _band_down(hb, hb_bands, _GBS_HB_FLOOR)),
        (f"SBP {sbp:.0f}", _band_down(sbp, _GBS_SBP, _GBS_SBP_FLOOR)),
        (f"HR {hr:.0f}", 1 if hr >= 100 else 0),
    ]
    parts += [(label.split(" (")[0], pts) for key, label, pts in _GBS_FLAGS if flags[key]]
    total = sum(p for _, p in parts)

    st.markdown(f"**GBS = {total} / 23**")
    st.markdown("\n".join(f"- {name}: +{pts}" for name, pts in parts if pts))

    if total <= _GBS_VERY_LOW:
        st.success(f"≤{_GBS_VERY_LOW} — very low risk of needing transfusion, endoscopic "
                   "therapy or surgery, or of death (Stanley 2017; ACG 2021 cutoff).")
    elif total >= _GBS_ENDOSCOPIC:
        st.error(f"≥{_GBS_ENDOSCOPIC} — the threshold that best predicted need for "
                 "endoscopic therapy (Stanley 2017).")
    else:
        st.warning(f"{_GBS_VERY_LOW + 1}–{_GBS_ENDOSCOPIC - 1} — not low risk; the "
                   "chance of needing intervention rises with the score.")


# Hestia (Zondag 2011): any "yes" excludes the patient from the low-risk group.
_HESTIA_CRITERIA = [
    "Hemodynamically unstable (e.g. SBP < 100 with HR > 100, or needing ICU care)",
    "Thrombolysis or embolectomy necessary",
    "Active bleeding or high bleeding risk (GI bleed < 14 d, stroke < 4 wk, "
    "surgery < 2 wk, bleeding disorder, platelets < 75, BP > 180/110)",
    "Supplemental O₂ needed > 24 h to keep SaO₂ > 90%",
    "PE diagnosed while already on anticoagulation",
    "Severe pain needing IV analgesia > 24 h",
    "Medical or social reason for admission > 24 h (infection, malignancy, "
    "no support system)",
    "CrCl < 30 mL/min (Cockcroft-Gault)",
    "Severe liver impairment",
    "Pregnant",
    "Documented history of HIT",
]


def _render_hestia() -> None:
    st.subheader("Hestia (PE)")
    st.caption("Tick any that apply.")

    present = [c for i, c in enumerate(_HESTIA_CRITERIA)
               if st.checkbox(c, key=f"tools_hestia_{i}")]

    st.markdown(f"**Hestia: {len(present)} of {len(_HESTIA_CRITERIA)} criteria present**")
    if present:
        st.warning("Hestia positive — not low risk.")
    else:
        st.success("Hestia negative — low risk. Derivation cohort (Zondag 2011): 3-month "
                   "recurrent VTE 2.0%, mortality 1.0%, major bleeding 0.7%.")


# PESI (Aujesky 2005): age in years plus fixed points; class I–V with the 30-day
# mortality ranges from the ESC 2019 PE guideline.
_PESI_FLAGS = [
    ("cancer", "Cancer", 30),
    ("hf", "Chronic heart failure", 10),
    ("lung", "Chronic lung disease", 10),
    ("ams", "Altered mental status", 60),
]
_PESI_CLASSES = [
    (65, "I", "0–1.6%"),
    (85, "II", "1.7–3.5%"),
    (105, "III", "3.2–7.1%"),
    (125, "IV", "4.0–11.4%"),
]
_PESI_CLASS_V = ("V", "10.0–24.5%")


def _render_pesi() -> None:
    st.subheader("PESI & sPESI (PE)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2, c3, c4 = st.columns(4)
    age = _num(c1, "Age (years)", "tools_pesi_age", 1.0)
    sex = c2.selectbox("Sex", ["Male", "Female"], key="tools_pesi_sex",
                       label_visibility="collapsed")
    hr = _num(c3, "Heart rate bpm", "tools_pesi_hr", 1.0)
    sbp = _num(c4, "Systolic BP mmHg", "tools_pesi_sbp", 1.0)
    c5, c6, c7, c8 = st.columns(4)
    sao2 = _num(c5, "SaO₂ %", "tools_pesi_sao2", 1.0)
    rr = _num(c6, "Resp rate /min", "tools_pesi_rr", 1.0)
    temp = _num(c7, "Temperature", "tools_pesi_temp", 0.1, "%.1f")
    unit = c8.selectbox("Unit", ["°F", "°C"], key="tools_pesi_unit",
                        label_visibility="collapsed")
    flags = {key: st.checkbox(label, key=f"tools_pesi_{key}")
             for key, label, _ in _PESI_FLAGS}

    # sPESI needs only age, HR, SBP and SaO₂; full PESI also needs RR and temp.
    if None in (age, hr, sbp, sao2):
        st.caption("Enter age, heart rate, systolic BP and SaO₂ for sPESI; add "
                   "respiratory rate and temperature for PESI.")
        return

    spesi = [
        (age > 80, "Age > 80"),
        (flags["cancer"], "Cancer"),
        (flags["hf"] or flags["lung"], "Chronic cardiopulmonary disease"),
        (hr >= 110, "HR ≥ 110"),
        (sbp < 100, "SBP < 100"),
        (sao2 < 90, "SaO₂ < 90%"),
    ]
    s_total = sum(hit for hit, _ in spesi)
    st.markdown(f"**sPESI = {s_total}**")
    if s_total:
        st.markdown("\n".join(f"- {name}: +1" for hit, name in spesi if hit))
        st.warning("≥1 — not low risk. 30-day mortality 10.9% (Jiménez 2010).")
    else:
        st.success("0 — low risk. 30-day mortality 1.0% (Jiménez 2010).")

    t = _temp_c(temp, unit)
    if rr is None or t is None:
        st.caption("Add respiratory rate and temperature for full PESI.")
        return

    parts = [(f"Age {age:.0f}", round(age)), ("Male sex", 10 if sex == "Male" else 0)]
    parts += [(label, pts) for key, label, pts in _PESI_FLAGS if flags[key]]
    parts += [
        ("HR ≥ 110", 20 if hr >= 110 else 0),
        ("SBP < 100", 30 if sbp < 100 else 0),
        ("RR ≥ 30", 20 if rr >= 30 else 0),
        ("Temp < 36 °C", 20 if t < 36.0 else 0),
        ("SaO₂ < 90%", 20 if sao2 < 90 else 0),
    ]
    total = sum(p for _, p in parts)
    cls, mort = next(((c, m) for top, c, m in _PESI_CLASSES if total <= top), _PESI_CLASS_V)

    st.markdown(f"**PESI = {total} — class {cls}** (30-day mortality {mort})")
    st.markdown("\n".join(f"- {name}: +{pts}" for name, pts in parts if pts))
    if cls in ("I", "II"):
        st.success(f"Class {cls} — low risk.")
    elif cls == "III":
        st.warning("Class III — intermediate risk.")
    else:
        st.error(f"Class {cls} — high risk.")


# Bova (Bova 2014): normotensive PE only. Stages by points, with 30-day
# PE-related complication rates (death, hemodynamic collapse, recurrent PE)
# from the derivation cohort.
_BOVA_STAGES = [
    (2, "I", "4.2%"),
    (4, "II", "10.8%"),
]
_BOVA_STAGE_III = ("III", "29.2%")


def _render_bova() -> None:
    st.subheader("Bova (normotensive PE)")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2 = st.columns(2)
    sbp = _num(c1, "Systolic BP mmHg", "tools_bova_sbp", 1.0)
    hr = _num(c2, "Heart rate bpm", "tools_bova_hr", 1.0)
    trop = st.checkbox("Elevated cardiac troponin", key="tools_bova_trop")
    rv = st.checkbox("RV dysfunction on echo or CT", key="tools_bova_rv")

    if sbp is None or hr is None:
        st.caption("Enter systolic BP and heart rate to score.")
        return
    if sbp < 90:
        st.error("SBP < 90 — hemodynamically unstable (high-risk PE). Bova applies "
                 "only to normotensive patients.")
        return

    parts = [
        ("SBP 90–100", 2 if sbp <= 100 else 0),
        ("Elevated troponin", 2 if trop else 0),
        ("RV dysfunction", 2 if rv else 0),
        ("HR ≥ 110", 1 if hr >= 110 else 0),
    ]
    total = sum(p for _, p in parts)
    stage, rate = next(((s, r) for top, s, r in _BOVA_STAGES if total <= top),
                       _BOVA_STAGE_III)

    st.markdown(f"**Bova = {total} / 7 — stage {stage}** "
                f"(30-day PE-related complications {rate})")
    st.markdown("\n".join(f"- {name}: +{pts}" for name, pts in parts if pts))
    if stage == "I":
        st.success("Stage I — low risk.")
    elif stage == "II":
        st.warning("Stage II — intermediate risk.")
    else:
        st.error("Stage III — high risk.")


# NEWS (RCP 2012) and NEWS2 (RCP 2017) share every band except SpO₂ scale 2
# (hypercapnic respiratory failure) and NEWS2 scoring new confusion as 3.
# Each list is (upper bound inclusive, points), checked in order.
_NEWS_RR = [(8, 3), (11, 1), (20, 0), (24, 2)]
_NEWS_RR_TOP = 3
_NEWS_SPO2_1 = [(91, 3), (93, 2), (95, 1)]
_NEWS_TEMP = [(35.0, 3), (36.0, 1), (38.0, 0), (39.0, 1)]
_NEWS_TEMP_TOP = 2
_NEWS_SBP = [(90, 3), (100, 2), (110, 1), (219, 0)]
_NEWS_SBP_TOP = 3
_NEWS_HR = [(40, 3), (50, 1), (90, 0), (110, 1), (130, 2)]
_NEWS_HR_TOP = 3
_NEWS_LOC = ["Alert", "New confusion", "Voice", "Pain", "Unresponsive"]
_NEWS_MEDIUM = 5
_NEWS_HIGH = 7


def _band_up(value: float, bands: list[tuple[float, int]], top: int) -> int:
    """Points for the first band whose upper bound (inclusive) holds the value."""
    for upper, pts in bands:
        if value <= upper:
            return pts
    return top


def _news2_spo2_scale2(spo2: float, on_o2: bool) -> int:
    if spo2 <= 83:
        return 3
    if spo2 <= 85:
        return 2
    if spo2 <= 87:
        return 1
    if spo2 <= 92 or not on_o2:
        return 0
    return 1 if spo2 <= 94 else 2 if spo2 <= 96 else 3


def _news_band(total: int, red: bool, low_medium: str) -> str:
    if total >= _NEWS_HIGH:
        return "High"
    if total >= _NEWS_MEDIUM:
        return "Medium"
    return low_medium if red else "Low"


def _render_news() -> None:
    st.subheader("NEWS & NEWS2")

    def _num(col, label, key, step, fmt=None):
        return col.number_input(label, value=None, step=step, format=fmt,
                                placeholder=label, label_visibility="collapsed",
                                key=key)

    c1, c2, c3, c4 = st.columns(4)
    rr = _num(c1, "Resp rate /min", "tools_news_rr", 1.0)
    spo2 = _num(c2, "SpO₂ %", "tools_news_spo2", 1.0)
    sbp = _num(c3, "Systolic BP mmHg", "tools_news_sbp", 1.0)
    hr = _num(c4, "Heart rate bpm", "tools_news_hr", 1.0)
    c5, c6, c7, c8 = st.columns(4)
    temp = _num(c5, "Temperature", "tools_news_temp", 0.1, "%.1f")
    unit = c6.selectbox("Unit", ["°F", "°C"], key="tools_news_unit",
                        label_visibility="collapsed")
    loc = c7.selectbox("Consciousness", _NEWS_LOC, key="tools_news_loc",
                       label_visibility="collapsed")
    on_o2 = c8.checkbox("On supplemental O₂", key="tools_news_o2")
    scale2 = st.checkbox("NEWS2 SpO₂ scale 2 — hypercapnic respiratory failure "
                         "with a prescribed 88–92% target", key="tools_news_scale2")

    t = _temp_c(temp, unit)
    if None in (rr, spo2, sbp, hr, t):
        st.caption("Enter respiratory rate, SpO₂, systolic BP, heart rate and "
                   "temperature to score.")
        return

    shared = {
        "RR": _band_up(rr, _NEWS_RR, _NEWS_RR_TOP),
        "Supplemental O₂": 2 if on_o2 else 0,
        "Temp": _band_up(t, _NEWS_TEMP, _NEWS_TEMP_TOP),
        "SBP": _band_up(sbp, _NEWS_SBP, _NEWS_SBP_TOP),
        "HR": _band_up(hr, _NEWS_HR, _NEWS_HR_TOP),
    }
    spo2_1 = _band_up(spo2, _NEWS_SPO2_1, 0)
    news = {**shared, "SpO₂": spo2_1,
            # NEWS 2012 scores AVPU only; new confusion in an alert patient is 0.
            "Consciousness": 3 if loc in ("Voice", "Pain", "Unresponsive") else 0}
    news2 = {**shared,
             "SpO₂" + (" (scale 2)" if scale2 else ""):
                 _news2_spo2_scale2(spo2, on_o2) if scale2 else spo2_1,
             "Consciousness": 0 if loc == "Alert" else 3}

    for name, parts, low_medium in (("NEWS2", news2, "Low–medium"),
                                    ("NEWS", news, "Low, with a red score")):
        total = sum(parts.values())
        red = 3 in parts.values()
        band = _news_band(total, red, low_medium)
        st.markdown(f"**{name} = {total}** — {band} clinical risk")
        detail = [f"{k}: +{v}" for k, v in parts.items() if v]
        if detail:
            st.markdown("- " + " · ".join(detail))
        if red and total < _NEWS_MEDIUM:
            st.caption("A single parameter scores 3 (red score).")

    if loc == "New confusion":
        st.caption("New confusion scores 3 in NEWS2 but nothing in NEWS 2012, "
                   "which scored AVPU only.")


# Tab → tools, in display order. A tool may sit under more than one tab; if it
# owns widgets, give it a per-tab key suffix (see _render_thrombolytic_ci).
_TOOL_TABS = {
    "Labs": [
        _render_acid_base,
        _render_corrected_sodium,
    ],
    "Neuro": [
        _render_nihss,
        _render_gcs,
        lambda: _render_thrombolytic_ci("neuro"),
    ],
    "Cardiology": [_render_qtc, _render_omi],
    "Pulmonary": [_render_pft, _render_pesi, _render_bova, _render_hestia],
    "GI & Hepatology": [
        _render_glasgow_blatchford,
        _render_apri,
        _render_r_factor,
    ],
    "Heme": [_render_retic_index, _render_iron_deficit],
    "General": [_render_news],
    "Reference": [
        _render_empiric_abx,
        lambda: _render_thrombolytic_ci("reference"),
        _render_procedures_checklist,
    ],
}


def render() -> None:
    st.title("🧰 Tools")
    # Tabs (not a selector) so every tool's widgets stay rendered and entered
    # values survive switching tabs.
    for tab, tools in zip(st.tabs(list(_TOOL_TABS)), _TOOL_TABS.values()):
        with tab:
            for i, tool in enumerate(tools):
                if i:
                    st.divider()
                tool()
