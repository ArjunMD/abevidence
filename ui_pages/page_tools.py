import math

import streamlit as st

from acid_base import interpret as interpret_acid_base
from extract import acid_base_ai_interpretation
from references_data import EMPIRIC_ABX_MD


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
            "Difficult laryngoscopy is assessed by LEMON (very crude)",
            "L = Look externally (simply gestalt)",
            "E = Evaluate 3-3-2. 3 fingers in the mouth, 3 fingers under the chin, "
            "2 fingers from base of chin to hyoid notch",
            f"M = [Mallampati]({_MALLAMPATI_IMAGE_URL})",
            "O = Obstruction/Obesity (muffled voice, stridor)",
            "N = Neck mobility",
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


def render() -> None:
    st.title("🧰 Tools")
    _render_acid_base()
    st.divider()
    _render_qtc()
    st.divider()
    _render_nihss()
    st.divider()
    _render_gcs()
    st.divider()
    _render_iron_deficit()
    st.divider()
    _render_corrected_sodium()
    st.divider()
    _render_apri()
    st.divider()
    _render_retic_index()
    st.divider()
    _render_empiric_abx()
    st.divider()
    _render_procedures_checklist()
