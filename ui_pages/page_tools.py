import streamlit as st

from acid_base import interpret as interpret_acid_base
from extract import acid_base_ai_interpretation


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
    st.caption("Score each item on the first attempt as observed; do not go back and change scores.")

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


def render() -> None:
    st.title("🧰 Tools")
    _render_acid_base()
    st.divider()
    _render_qtc()
    st.divider()
    _render_nihss()
    st.divider()
    _render_gcs()
