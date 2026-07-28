"""Static RRT / code-response dosing reference. No AI, no DB — just a pocket
card. Laid out for a phone: every section collapsed, tight line spacing."""

import re

import streamlit as st

# (section, [(subheading, [line, ...]), ...]). Bold with **…**; keep each line
# to roughly one phone-width line. Adult doses; a typical 70-80 kg figure is
# given in parentheses where the weight-based math is usually done in the head.
_SECTIONS: list[tuple[str, list[tuple[str, list[str]]]]] = [
    ("1. RSI", [
        ("Induction", [
            "**Etomidate** 0.3 mg/kg IV (20 mg) — HD-neutral, transient adrenal suppression",
            "**Ketamine** 1–2 mg/kg IV (100 mg) — bronchodilates; flat/↓BP if catecholamine-depleted",
            "**Propofol** 1.5–2.5 mg/kg IV — drops MAP, avoid if unstable",
            "**Midazolam** 0.2–0.3 mg/kg IV — slow onset, rarely first line",
        ]),
        ("Paralysis", [
            "**Succinylcholine** 1.5 mg/kg IV (100 mg) — onset 45 s, lasts 6–10 min",
            "↳ avoid: hyperK, burn/crush/denervation >48 h, MH hx, chronic NM disease",
            "**Rocuronium** 1.2 mg/kg IV (100 mg) — onset 45–60 s, lasts 45–70 min",
        ]),
        ("After the tube", [
            "Sedate immediately — roc outlasts every induction agent",
            "Confirm ETCO₂; push-dose pressor drawn up before you push induction",
        ]),
    ]),

    ("2. Ventricular tachycardia", [
        ("Stable, monomorphic", [
            "**Amiodarone** 150 mg IV over 10 min, repeat q10 min prn",
            "↳ then 1 mg/min ×6 h, then 0.5 mg/min ×18 h",
            "**Procainamide** 20–50 mg/min until suppressed, QRS +50%, ↓BP, or 17 mg/kg",
            "↳ then 1–4 mg/min",
            "**Lidocaine** 1–1.5 mg/kg IV, then 1–4 mg/min",
        ]),
        ("Unstable, with a pulse", [
            "Sync cardioversion **100 J** biphasic (↑ as needed)",
            "Sedate: etomidate 10 mg or ketamine 20 mg IV",
        ]),
        ("Polymorphic / torsades", [
            "**Magnesium** 2 g IV over 15 min, repeat ×1",
            "K⁺ >4, Mg >2; stop every QT-prolonging drug",
            "Unsynchronized defib if pulseless or unstable",
            "Refractory + bradycardia-dependent: overdrive pace, isoproterenol 2–10 mcg/min",
        ]),
    ]),

    ("3. ACLS / cardiac arrest", [
        ("Every rhythm", [
            "**Epinephrine** 1 mg IV/IO q3–5 min (10 mL of 1:10,000)",
            "High-quality CPR, 10 breaths/min once tubed, rhythm check q2 min",
        ]),
        ("Shockable (VF / pVT)", [
            "Defib **200 J** biphasic (or device max)",
            "**Amiodarone** 300 mg IV push → 150 mg ×1",
            "or **Lidocaine** 1–1.5 mg/kg → 0.5–0.75 mg/kg",
            "Refractory VF: dual sequential defib, esmolol 500 mcg/kg",
        ]),
        ("Situational", [
            "**CaCl₂** 1 g IV (or Ca gluconate 3 g) — hyperK, CCB OD, ↓Ca",
            "**Bicarb** 1 mEq/kg — hyperK, TCA OD, prolonged arrest",
            "**tPA** 50 mg IV push — arrest from suspected massive PE, then CPR 60 min",
        ]),
        ("H's & T's", [
            "Hypovolemia, hypoxia, H⁺, hypo/hyperK, hypothermia",
            "Tension PTX, tamponade, toxins, thrombosis (PE / MI)",
        ]),
    ]),

    ("4. SVT and atrial fibrillation", [
        ("SVT", [
            "Modified Valsalva first (blow, then supine + legs up) — ~43% conversion",
            "**Adenosine** 6 mg rapid IV push + 20 mL flush, arm up → 12 mg if no break",
            "↳ use 3 mg if central line, transplanted heart, or on dipyridamole/carbamazepine",
        ]),
        ("Rate control (AF/flutter, SVT)", [
            "**Diltiazem** 0.25 mg/kg over 2 min (20 mg) → 0.35 mg/kg (25 mg) at 15 min",
            "↳ then 5–15 mg/h; avoid in HFrEF",
            "**Metoprolol** 2.5–5 mg IV q5 min ×3",
        ]),
        ("HFrEF or borderline BP", [
            "**Amiodarone** 150 mg over 10 min → 1 mg/min",
            "**Digoxin** 0.25 mg IV q6h, max 1.5 mg/24 h — slow, add-on only",
        ]),
        ("Unstable / caveats", [
            "Sync cardioversion: **50–100 J** SVT, **120–200 J** AF",
            "Pre-excited AF (WPW, irregular + wide + fast): **procainamide**",
            "↳ NO adenosine, diltiazem, beta blocker, or digoxin — can precipitate VF",
        ]),
    ]),

    ("5. Bradycardia", [
        ("First moves", [
            "**Atropine** 1 mg IV q3–5 min, max 3 mg",
            "↳ won't work in high-grade AV block, transplanted heart",
            "**Transcutaneous pacing** — sedate, start 60–80 mA, confirm mechanical capture",
        ]),
        ("Drips", [
            "**Epinephrine** 2–10 mcg/min",
            "**Dopamine** 5–20 mcg/kg/min",
            "**Isoproterenol** 2–10 mcg/min",
        ]),
        ("Find the cause", [
            "**HyperK** → calcium first",
            "**Beta blocker OD** → glucagon 3–10 mg IV, then 3–5 mg/h",
            "**CCB OD** → CaCl₂ 1 g + high-dose insulin 1 U/kg bolus, then 0.5–1 U/kg/h w/ D10",
            "**Digoxin tox** → DigiFab; ischemia, hypothermia, ↑ICP, hypothyroid",
        ]),
    ]),

    ("6. Procedural sedation", [
        ("Agents", [
            "**Ketamine** 1 mg/kg IV over 1–2 min → 0.5 mg/kg q5–10 min",
            "↳ keeps airway and BP; emergence, secretions",
            "**Propofol** 0.5–1 mg/kg → 0.25 mg/kg q1–3 min — apnea, ↓BP",
            "**Etomidate** 0.1–0.15 mg/kg — myoclonus",
            "**Fentanyl** 25–50 mcg + **midazolam** 1–2 mg, titrate q3–5 min",
            "↳ stacking these two is the classic route to apnea",
        ]),
        ("Cardioversion", [
            "Etomidate 0.1 mg/kg or propofol 0.5 mg/kg — short, deep, done",
        ]),
        ("Rescue", [
            "**Naloxone** 0.04–0.4 mg IV; **flumazenil** 0.2 mg (not if chronic benzo — seizures)",
        ]),
    ]),

    ("7. Ventilator sedation", [
        ("Analgesia first", [
            "**Fentanyl** 25–100 mcg IV bolus → 25–200 mcg/h",
        ]),
        ("Sedation", [
            "**Propofol** 5–50 mcg/kg/min — ↓BP, triglycerides, PRIS if >4 mg/kg/h",
            "**Dexmedetomidine** 0.2–1.5 mcg/kg/h, no bolus — brady/↓BP, no resp depression",
            "**Midazolam** 1–5 mg bolus → 1–10 mg/h — accumulates, delirium",
            "**Ketamine** 0.1–0.5 mg/kg/h — adjunct, opioid-sparing",
        ]),
        ("Targets", [
            "RASS 0 to −2 unless a reason otherwise; daily SAT/SBT",
            "Paralysis only when deeply sedated: **cisatracurium** 0.1–0.2 mg/kg → 1–3 mcg/kg/min",
        ]),
    ]),

    ("8. Status epilepticus", [
        ("First line (0–5 min)", [
            "**Lorazepam** 4 mg IV, repeat ×1 at 5 min",
            "No IV: **midazolam** 10 mg IM (or intranasal/buccal)",
            "**Diazepam** 10 mg IV — underdosing benzos is the usual error",
        ]),
        ("Second line (20 min)", [
            "**Levetiracetam** 60 mg/kg IV, max 4500 mg",
            "**Fosphenytoin** 20 mg PE/kg, max 1500 mg PE",
            "**Valproate** 40 mg/kg IV, max 3000 mg",
        ]),
        ("Third line (40 min)", [
            "Repeat second agent, or intubate + infusion:",
            "**Midazolam** 0.2 mg/kg → 0.05–2 mg/kg/h; **propofol**; **ketamine**; pentobarb",
            "cEEG — nonconvulsive status after the shaking stops",
        ]),
        ("Always", [
            "Glucose, Na, Ca, Mg; **thiamine** 100 mg before dextrose",
            "**Pyridoxine** 5 g IV if INH ingestion",
            "Eclampsia: **MgSO₄** 4–6 g IV over 20 min → 1–2 g/h",
        ]),
    ]),

    ("9. Anaphylaxis", [
        ("Epinephrine — first, always", [
            "**0.3–0.5 mg IM** anterolateral thigh (1 mg/mL), repeat q5–15 min",
            "No ceiling on repeat doses; delay is what kills",
            "Refractory: infusion 2–10 mcg/min (0.05–0.1 mcg/kg/min)",
        ]),
        ("Support", [
            "Crystalloid 1–2 L bolus; supine with legs up (not sitting up)",
            "Albuterol neb for bronchospasm",
            "On a beta blocker and refractory: **glucagon** 1–5 mg IV over 5 min",
        ]),
        ("Adjuncts — never instead of epi", [
            "Diphenhydramine 25–50 mg IV, famotidine 20 mg IV",
            "Methylprednisolone 125 mg IV",
            "Observe 4–6 h — biphasic in ~5%",
        ]),
    ]),

    ("10. Push-dose pressors", [
        ("Phenylephrine 100 mcg/mL", [
            "**50–200 mcg (0.5–2 mL) q2–5 min**",
            "Mix: 1 mL of 10 mg/mL into 100 mL NS",
            "Pure alpha, reflex brady — good if tachycardic or AS",
        ]),
        ("Epinephrine 10 mcg/mL", [
            "**5–20 mcg (0.5–2 mL) q2–5 min**",
            "Mix: 1 mL of cardiac epi (100 mcg/mL) into 9 mL NS",
            "Inotropy + chronotropy — good if bradycardic or low output",
        ]),
        ("Rules", [
            "Onset <1 min, lasts 5–15 min — a bridge, not a plan; start the infusion",
            "Label the syringe. Wrong-concentration epi is a recurring sentinel event",
        ]),
    ]),

    ("11. Pressor and inotrope infusions", [
        ("", [
            "**Norepinephrine** 0.05–1 mcg/kg/min (2–80 mcg/min) — first line, most shock",
            "**Vasopressin** 0.03 U/min fixed — add-on, don't titrate",
            "**Epinephrine** 0.01–0.5 mcg/kg/min — 2nd line, anaphylaxis, cardiogenic",
            "**Phenylephrine** 25–200 mcg/min — when tachyarrhythmia limits you",
            "**Dobutamine** 2.5–20 mcg/kg/min — inotrope, drops SVR",
            "**Milrinone** 0.125–0.5 mcg/kg/min — renally cleared, ↓BP, long t½",
            "**Angiotensin II** 20 ng/kg/min — refractory vasoplegia",
        ]),
    ]),

    ("12. Hyperkalemia", [
        ("", [
            "**Ca gluconate** 1–3 g IV (CaCl₂ 1 g if central) — onset 1–3 min, repeat if ECG persists",
            "**Insulin** 10 U IV + **D50** 25–50 g — glucose q1h ×6 (use 5 U if CKD/frail)",
            "**Albuterol** 10–20 mg neb — 8–10× the usual dose",
            "**Bicarb** 50–150 mEq — only if acidemic",
            "**Furosemide** 40–80 mg IV if making urine",
            "**Lokelma/patiromer** 10 g PO — slow, not for the acute drop",
            "Dialysis if anuric or refractory — call early, not after the third insulin dose",
        ]),
    ]),

    ("13. Hypertensive emergency", [
        ("Target", [
            "↓MAP 20–25% in the first hour — except dissection, stroke, eclampsia",
        ]),
        ("Agents", [
            "**Nicardipine** 5 mg/h, ↑2.5 mg/h q5–15 min, max 15 mg/h — easiest to titrate",
            "**Labetalol** 10–20 mg IV q10 min, or 0.5–2 mg/min",
            "**Esmolol** 500 mcg/kg bolus → 50–200 mcg/kg/min",
            "**Nitroglycerin** 5–200 mcg/min — pulmonary edema, ACS",
            "**Hydralazine** 10–20 mg IV q4–6h — unpredictable, poor choice for a drip-worthy BP",
            "**Clevidipine** 1–2 mg/h → max 21 mg/h",
        ]),
        ("Special cases", [
            "**Dissection**: rate first — esmolol/labetalol to HR <60, then SBP 100–120",
            "**Cocaine / pheo**: phentolamine + benzos; no unopposed beta blockade",
            "**Eclampsia**: MgSO₄ + labetalol or hydralazine",
        ]),
    ]),

    ("14. Reversal and antidotes", [
        ("Anticoagulants", [
            "**Warfarin**: vit K 10 mg IV + 4F-PCC 25–50 U/kg",
            "**Xa inhibitor**: andexanet, or 4F-PCC 50 U/kg",
            "**Dabigatran**: idarucizumab 5 g IV",
            "**Heparin**: protamine 1 mg per 100 U given in last 2–3 h, max 50 mg",
        ]),
        ("Tox", [
            "**Opioid**: naloxone 0.04–0.4 mg IV, repeat — shorter t½ than most opioids",
            "**Benzo**: flumazenil 0.2 mg — rarely worth the seizure risk",
            "**APAP**: NAC 150 mg/kg → 50 → 100",
            "**Toxic alcohol**: fomepizole 15 mg/kg",
            "**Local anesthetic**: intralipid 20% 1.5 mL/kg → 0.25 mL/kg/min",
            "**Methemoglobinemia**: methylene blue 1–2 mg/kg",
            "**Sulfonylurea**: octreotide 50–100 mcg SC q6h",
        ]),
        ("Glucose", [
            "**D50** 25–50 mL IV; **glucagon** 1 mg IM if no access",
            "Recheck in 15 min and feed them — one amp is not a disposition",
        ]),
    ]),

    ("15. Elevated ICP / herniation", [
        ("", [
            "HOB 30°, neck midline, treat pain/fever/seizure/hypercarbia",
            "**23.4% NaCl** 30 mL IV over 10 min (central) — herniation",
            "**3% NaCl** 250 mL over 15–30 min; target Na 145–155",
            "**Mannitol** 0.5–1 g/kg IV — needs an adequate BP, watch osm gap",
            "Hyperventilate to PaCO₂ 30–35 — bridge to the OR only, minutes not hours",
            "Sedate ± paralyze; neurosurgery now",
        ]),
    ]),
]

_CSS = """
<style>
[data-testid="stExpander"] summary {padding: .3rem .6rem; font-size: .95rem;}
[data-testid="stExpander"] summary p {font-weight: 600; margin: 0;}
[data-testid="stExpander"] details > div {padding-top: .1rem;}
.rrt {font-size: .88rem; line-height: 1.35;}
.rrt .sub {font-weight: 600; opacity: .75; margin: .45rem 0 .1rem; font-size: .8rem;
           text-transform: uppercase; letter-spacing: .03em;}
.rrt .sub:first-child {margin-top: 0;}
.rrt ul {margin: 0; padding-left: 1.05rem;}
.rrt li {margin: 0 0 .12rem 0;}
</style>
"""


_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _html(groups: list[tuple[str, list[str]]]) -> str:
    """One HTML blob per section — a single st.markdown call, tight spacing."""
    out = ['<div class="rrt">']
    for sub, lines in groups:
        if sub:
            out.append(f'<div class="sub">{sub}</div>')
        items = "".join(f"<li>{_BOLD.sub(r'<b>\1</b>', line)}</li>" for line in lines)
        out.append(f"<ul>{items}</ul>")
    out.append("</div>")
    return "".join(out)


def render() -> None:
    st.title("🚨 RRT meds")
    st.caption("Adult doses. Reference only — verify before you push anything.")
    st.markdown(_CSS, unsafe_allow_html=True)

    for title, groups in _SECTIONS:
        with st.expander(title):
            st.markdown(_html(groups), unsafe_allow_html=True)
