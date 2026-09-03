"""Deterministic acid-base interpretation for the Tools page.

Pure arithmetic — no AI, no network. Every input is optional; the engine
computes whatever the supplied values support and says what's missing:

  * Full gas (pH + pCO₂ + HCO₃⁻) → primary disorder + compensation check.
  * BMP only (Na + Cl + HCO₃⁻, no gas) → anion gap, delta ratio, and the
    metabolic direction from the bicarbonate (respiratory component can't be
    assessed without a gas).
  * Na + Cl alone → strong ion difference (Stewart view): chloride read
    relative to sodium, which gives the acidifying/alkalinizing direction
    even with no bicarbonate in hand.
  * Optional lactate, β-hydroxybutyrate, and glucose → "explain the gap":
    severity flags plus a quantitative check of whether the measured anions
    account for the gap excess (each mmol/L ≈ 1 of anion gap).

Formulas are the standard bedside ones: Winter's for metabolic acidosis, the
expected-pCO₂ rule for metabolic alkalosis, the acute/chronic HCO₃⁻ rules for
respiratory disorders, and the delta ratio for mixed metabolic pictures.

The strong ion difference here is the bedside simplification Na⁺−Cl⁻, not a
full Stewart calculation: potassium, calcium and magnesium are left out of the
cation side, and the weak acids (albumin, phosphate) are handled separately by
the albumin-corrected anion gap. It reads the direction and rough size of the
chloride force, not an exact strong ion gap.

Reference values: pH 7.40, pCO2 40 mmHg, HCO3 24 mmol/L, anion gap 12,
SID (Na−Cl) 38-42, lactate ≤2 mmol/L, β-hydroxybutyrate <0.6 mmol/L.
"""

NORMAL_HCO3 = 24.0
NORMAL_AG = 12.0
LACTATE_UPPER = 2.0   # upper normal lactate (mmol/L)
BHB_UPPER = 0.6       # upper normal β-hydroxybutyrate (mmol/L)

# Strong ion difference bands on the (Na⁺+K⁺)−Cl⁻ scale, normalised to a sodium
# of 140. Below SID_LOW chloride is exerting an acidifying force; below
# SID_MARKED_LOW it is large enough to call a hyperchloremic non-gap acidosis on
# its own. Mirror-image thresholds apply on the alkalinizing side.
#
# The anchor is electroneutrality: Na⁺+K⁺ = Cl⁻ + HCO₃⁻ + anion gap, so a normal
# SID is just a normal HCO₃⁻ plus a normal gap plus the potassium, 24+12+4 = 40.
# Without a potassium the whole band shifts down by ASSUMED_K, which is why a
# bare Na⁻Cl of 36 is normal while an (Na+K)−Cl of 36 is not.
SID_LOW = 38.0
SID_HIGH = 42.0
SID_MARKED_LOW = 34.0
SID_MARKED_HIGH = 46.0
ASSUMED_K = 4.0

# One-line differentials keyed by disorder. Kept short on purpose.
_DIFFERENTIALS = {
    "hagma": "High anion gap (GOLDMARK): glycols, oxoproline, L-/D-lactate, "
             "methanol, aspirin, renal failure, ketoacidosis.",
    "nagma": "Non-gap: diarrhea, renal tubular acidosis, saline/TPN, "
             "acetazolamide, ureteral diversion.",
    "met_alk": "Metabolic alkalosis: vomiting/NG suction, diuretics, "
               "hypokalemia, hyperaldosteronism, contraction, milk-alkali.",
    "resp_ac": "Respiratory acidosis: sedation/opioids, COPD/asthma, "
               "neuromuscular weakness, chest-wall/obesity hypoventilation.",
    "resp_alk": "Respiratory alkalosis: anxiety/pain, hypoxia, PE, sepsis, "
                "salicylates, pregnancy, hepatic failure.",
    "lactic": "Lactic acidosis: type A (sepsis, hypoperfusion, ischemia) or "
              "type B (metformin, liver failure, malignancy, thiamine deficiency).",
    "keto": "Ketoacidosis: diabetic, alcoholic, or starvation.",
    "unexplained": "Unexplained gap: toxic alcohols (methanol/ethylene glycol — "
                   "check osmolar gap), salicylates, uremia, 5-oxoproline.",
    "osm": "Elevated osmolar gap: methanol, ethylene glycol, isopropanol "
           "(also ethanol, mannitol, propylene glycol).",
}


def _fmt(x: float) -> str:
    """Whole numbers without a trailing '.0', one decimal otherwise."""
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def _standard_base_excess(pH: float, hco3: float) -> float:
    """Standard base excess (mEq/L), Siggaard-Andersen / Van Slyke approximation.
    Negative values are a base deficit. Estimated from a full gas — the analyzer
    computes the same quantity from pH and HCO₃⁻."""
    return 0.9287 * (hco3 - 24.4 + 14.83 * (pH - 7.4))


def interpret(pH=None, pco2=None, hco3=None, na=None, cl=None, albumin=None,
              lactate=None, bhb=None, glucose=None, bun=None, creatinine=None,
              osm=None, k=None) -> dict:
    """Interpret whatever blood-gas / lab values are supplied (all optional).
    Returns {headline, steps, differential, warnings, summary} where summary is
    a compact one-line recap of the entered values (used to prime the optional
    AI layer)."""
    steps: list[str] = []
    warnings: list[str] = []
    extras: list[str] = []      # superimposed / concurrent disorders
    diff_keys: list[str] = []   # which differentials to show

    has_gas = pH is not None and pco2 is not None and hco3 is not None

    # --- input sanity (only for values actually provided) ----------------
    if pH is not None and (pH < 6.8 or pH > 7.8):
        warnings.append("pH outside 6.8–7.8 — recheck the value entered.")
    if pco2 is not None and pco2 <= 0:
        warnings.append("pCO₂ should be positive — recheck the value.")
    if hco3 is not None and hco3 <= 0:
        warnings.append("HCO₃⁻ should be positive — recheck the value.")

    primary = None          # full disorder name when a gas is present
    metabolic_dir = None    # "metabolic acidosis"/"alkalosis" when gas absent

    # --- full interpretation when a gas is present -----------------------
    if has_gas:
        if pH < 7.35:
            status = "acidemia"
        elif pH > 7.45:
            status = "alkalemia"
        else:
            status = "normal pH"
        steps.append(f"pH {_fmt(pH)} → {status}.")

        hco3_low, hco3_high = hco3 < 22, hco3 > 26
        pco2_low, pco2_high = pco2 < 35, pco2 > 45

        if status == "acidemia":
            if hco3_low and pco2_high:
                primary = "combined metabolic and respiratory acidosis"
            elif pco2_high:
                primary = "respiratory acidosis"
            else:
                primary = "metabolic acidosis"
        elif status == "alkalemia":
            if hco3_high and pco2_low:
                primary = "combined metabolic and respiratory alkalosis"
            elif pco2_low:
                primary = "respiratory alkalosis"
            else:
                primary = "metabolic alkalosis"
        else:  # normal pH — normal, fully compensated, or mixed
            if not (hco3_low or hco3_high or pco2_low or pco2_high):
                primary = "normal acid-base status"
            elif hco3_low and pco2_low:
                primary = "mixed: metabolic acidosis with respiratory alkalosis (normal pH)"
            elif hco3_high and pco2_high:
                primary = "mixed: metabolic alkalosis with respiratory acidosis (normal pH)"
            else:
                primary = "mixed disorder (normal pH with abnormal pCO₂/HCO₃⁻)"

        # compensation
        if primary == "metabolic acidosis":
            expected = 1.5 * hco3 + 8  # Winter's formula
            steps.append(
                f"Winter's expected pCO₂ = 1.5×{_fmt(hco3)}+8 = {_fmt(expected)} ±2 "
                f"(actual {_fmt(pco2)})."
            )
            if pco2 > expected + 2:
                steps.append("→ pCO₂ higher than expected: superimposed respiratory acidosis.")
                extras.append("superimposed respiratory acidosis")
                diff_keys.append("resp_ac")
            elif pco2 < expected - 2:
                steps.append("→ pCO₂ lower than expected: superimposed respiratory alkalosis.")
                extras.append("superimposed respiratory alkalosis")
                diff_keys.append("resp_alk")
            else:
                steps.append("→ appropriate respiratory compensation.")

        elif primary == "metabolic alkalosis":
            expected = 0.7 * hco3 + 21  # expected pCO2 for metabolic alkalosis
            steps.append(
                f"Expected pCO₂ = 0.7×{_fmt(hco3)}+21 = {_fmt(expected)} ±2 "
                f"(actual {_fmt(pco2)})."
            )
            if pco2 > expected + 2:
                steps.append("→ pCO₂ higher than expected: superimposed respiratory acidosis.")
                extras.append("superimposed respiratory acidosis")
                diff_keys.append("resp_ac")
            elif pco2 < expected - 2:
                steps.append("→ pCO₂ lower than expected: superimposed respiratory alkalosis.")
                extras.append("superimposed respiratory alkalosis")
                diff_keys.append("resp_alk")
            else:
                steps.append("→ appropriate respiratory compensation.")
            diff_keys.append("met_alk")

        elif primary == "respiratory acidosis":
            acute = NORMAL_HCO3 + 0.1 * (pco2 - 40)     # HCO3 rises 1 per 10 mmHg
            chronic = NORMAL_HCO3 + 0.35 * (pco2 - 40)  # rises 3.5 per 10 mmHg
            steps.append(
                f"Expected HCO₃⁻: acute ≈ {_fmt(acute)}, chronic ≈ {_fmt(chronic)} "
                f"(actual {_fmt(hco3)})."
            )
            if hco3 < acute - 2:
                steps.append("→ HCO₃⁻ below acute expected: superimposed metabolic acidosis.")
                extras.append("superimposed metabolic acidosis")
            elif hco3 > chronic + 2:
                steps.append("→ HCO₃⁻ above chronic expected: superimposed metabolic alkalosis.")
                extras.append("superimposed metabolic alkalosis")
                diff_keys.append("met_alk")
            elif hco3 <= acute + 2:
                steps.append("→ consistent with acute respiratory acidosis.")
            else:
                steps.append("→ consistent with chronic (or partly compensated) respiratory acidosis.")
            diff_keys.append("resp_ac")

        elif primary == "respiratory alkalosis":
            acute = NORMAL_HCO3 - 0.2 * (40 - pco2)     # HCO3 falls 2 per 10 mmHg
            chronic = NORMAL_HCO3 - 0.4 * (40 - pco2)   # falls 4 per 10 mmHg
            steps.append(
                f"Expected HCO₃⁻: acute ≈ {_fmt(acute)}, chronic ≈ {_fmt(chronic)} "
                f"(actual {_fmt(hco3)})."
            )
            if hco3 > acute + 2:
                steps.append("→ HCO₃⁻ above acute expected: superimposed metabolic alkalosis.")
                extras.append("superimposed metabolic alkalosis")
                diff_keys.append("met_alk")
            elif hco3 < chronic - 2:
                steps.append("→ HCO₃⁻ below chronic expected: superimposed metabolic acidosis.")
                extras.append("superimposed metabolic acidosis")
            elif hco3 >= acute - 2:
                steps.append("→ consistent with acute respiratory alkalosis.")
            else:
                steps.append("→ consistent with chronic (or partly compensated) respiratory alkalosis.")
            diff_keys.append("resp_alk")

        # base excess / deficit — the base-excess ("Copenhagen") counterpart to
        # the bicarbonate/gap method, useful as a severity readout.
        sbe = _standard_base_excess(pH, hco3)
        if sbe < -2:
            bd = -sbe
            sev = "severe" if bd > 10 else "moderate" if bd > 6 else "mild"
            steps.append(
                f"Base deficit ≈ {_fmt(bd)} mEq/L ({sev}) — estimated metabolic acid load."
            )
            if lactate is not None and lactate > LACTATE_UPPER:
                if lactate >= 0.7 * bd:
                    steps.append(f"→ lactate {_fmt(lactate)} accounts for most of the base deficit.")
                else:
                    steps.append(f"→ base deficit exceeds lactate {_fmt(lactate)} — other acids contributing.")
        elif sbe > 2:
            steps.append(
                f"Base excess ≈ +{_fmt(sbe)} mEq/L — metabolic alkalosis by the base-excess method."
            )

    # --- no gas: metabolic direction from the bicarbonate ----------------
    elif hco3 is not None:
        if hco3 < 22:
            metabolic_dir = "metabolic acidosis"
            steps.append(
                f"HCO₃⁻ {_fmt(hco3)} (low) → metabolic acidosis, or renal "
                "compensation for a respiratory alkalosis."
            )
            steps.append("No gas entered: add pH and pCO₂ to confirm the primary disorder and compensation.")
        elif hco3 > 26:
            metabolic_dir = "metabolic alkalosis"
            steps.append(
                f"HCO₃⁻ {_fmt(hco3)} (high) → metabolic alkalosis, or renal "
                "compensation for a respiratory acidosis."
            )
            steps.append("No gas entered: add pH and pCO₂ to confirm the primary disorder and compensation.")
            diff_keys.append("met_alk")
        else:
            steps.append(f"HCO₃⁻ {_fmt(hco3)} — within normal range (no gas for respiratory assessment).")

    # --- anion gap (whenever Na, Cl, HCO₃⁻ are all present) --------------
    high_ag = False
    corrected = None
    delta_ratio = None
    metabolic_acidosis_present = (
        (primary is not None and "metabolic acidosis" in primary)
        or metabolic_dir == "metabolic acidosis"
    )
    metabolic_alkalosis_present = (
        (primary is not None and "metabolic alkalosis" in primary)
        or metabolic_dir == "metabolic alkalosis"
    )
    if na is not None and cl is not None and hco3 is not None:
        ag = na - cl - hco3
        line = f"Anion gap = {_fmt(na)}−{_fmt(cl)}−{_fmt(hco3)} = {_fmt(ag)}"
        corrected = ag
        if albumin is not None:
            corrected = ag + 2.5 * (4.0 - albumin)
            line += f"; albumin-corrected = {_fmt(corrected)} (normal ≈ 12)."
        else:
            line += " (normal ≈ 12)."
        steps.append(line)

        if albumin is not None:
            if corrected > 12 and ag <= 12:
                steps.append(
                    f"→ raw gap {_fmt(ag)} looks normal, but the albumin-corrected gap "
                    f"{_fmt(corrected)} is elevated — hypoalbuminemia was masking a high "
                    "anion gap acidosis."
                )
            elif corrected <= 12 and ag > 12:
                steps.append(
                    f"→ raw gap {_fmt(ag)} looks elevated, but correcting for albumin "
                    f"brings it to {_fmt(corrected)} (not truly elevated)."
                )

        if corrected > 12:
            high_ag = True
            denom = NORMAL_HCO3 - hco3
            if denom > 0.5:
                delta_ratio = (corrected - NORMAL_AG) / denom
                steps.append(
                    f"Delta ratio = ({_fmt(corrected)}−12)/(24−{_fmt(hco3)}) = {delta_ratio:.1f}."
                )
                if delta_ratio < 1:
                    steps.append("→ mixed high-gap and non-gap metabolic acidosis.")
                    extras.append("concurrent non-gap metabolic acidosis")
                    diff_keys.append("nagma")
                elif delta_ratio <= 2:
                    steps.append("→ pure high anion gap metabolic acidosis.")
                else:
                    steps.append(
                        "→ the gap has risen further than the HCO₃⁻ has fallen: the high "
                        "anion gap acidosis is real, with a concurrent metabolic alkalosis "
                        "(or chronic respiratory acidosis) propping the HCO₃⁻ up."
                    )
                    extras.append("concurrent metabolic alkalosis")
                    diff_keys.append("met_alk")
            elif metabolic_alkalosis_present:
                steps.append(
                    "→ an elevated gap with a HCO₃⁻ that is not low still means a high "
                    "anion gap metabolic acidosis is present — superimposed on the "
                    "metabolic alkalosis, which is holding the HCO₃⁻ up."
                )
                extras.append("metabolic alkalosis")
            else:
                steps.append(
                    f"→ HCO₃⁻ {_fmt(hco3)} is not low, but the elevated gap still means a "
                    "high anion gap metabolic acidosis is present: a second, alkalinizing "
                    "process (metabolic alkalosis, or chronic respiratory acidosis) is "
                    "masking it by keeping the HCO₃⁻ up."
                )
                extras.append("concurrent metabolic alkalosis")
                diff_keys.append("met_alk")
        else:
            steps.append("→ anion gap not elevated.")
            if metabolic_acidosis_present:
                diff_keys.append("nagma")
    elif metabolic_acidosis_present:
        steps.append("Enter Na⁺ and Cl⁻ to classify the anion gap.")

    # --- explain the gap: lactate / ketones / glucose magnitude ----------
    if high_ag and corrected is not None:
        delta_gap = corrected - NORMAL_AG
        explained = 0.0
        lac_elevated = lactate is not None and lactate > LACTATE_UPPER
        keto_elevated = bhb is not None and bhb >= BHB_UPPER

        if lactate is not None:
            if lactate > 4:
                steps.append(f"Lactate {_fmt(lactate)} — significant lactic acidosis (≥4; sepsis/shock range).")
            elif lactate > LACTATE_UPPER:
                steps.append(f"Lactate {_fmt(lactate)} — mildly elevated.")
            else:
                steps.append(f"Lactate {_fmt(lactate)} — within normal range.")
            explained += max(0.0, lactate - LACTATE_UPPER)

        if bhb is not None:
            if bhb >= 3:
                kmsg = f"β-hydroxybutyrate {_fmt(bhb)} — ketoacidosis range (≥3)."
            elif bhb >= BHB_UPPER:
                kmsg = f"β-hydroxybutyrate {_fmt(bhb)} — ketosis (mildly elevated)."
            else:
                kmsg = f"β-hydroxybutyrate {_fmt(bhb)} — within normal range."
            if keto_elevated and glucose is not None:
                if glucose > 250:
                    kmsg += f" With glucose {_fmt(glucose)} → consistent with DKA."
                elif glucose < 200:
                    kmsg += (f" With glucose {_fmt(glucose)} → euglycemic ketoacidosis "
                             "(SGLT2 inhibitor, starvation, alcohol, pregnancy).")
            steps.append(kmsg)
            explained += max(0.0, bhb - BHB_UPPER)

        if bhb is None and glucose is not None and glucose > 250:
            steps.append(f"Glucose {_fmt(glucose)} elevated — check β-hydroxybutyrate to assess for DKA.")

        if lactate is not None or bhb is not None:
            if lac_elevated:
                diff_keys.append("lactic")
            if keto_elevated:
                diff_keys.append("keto")
            residual = delta_gap - explained
            both_measured = lactate is not None and bhb is not None
            if residual > 5:
                if both_measured:
                    steps.append(
                        f"Measured anions explain ≈{_fmt(explained)} of the "
                        f"{_fmt(delta_gap)} gap excess; ≈{_fmt(residual)} unexplained → "
                        "consider toxic alcohols (osmolar gap), salicylates, uremia."
                    )
                    diff_keys.append("unexplained")
                else:
                    missing = "β-hydroxybutyrate" if bhb is None else "lactate"
                    steps.append(
                        f"Measured anions leave ≈{_fmt(residual)} of the {_fmt(delta_gap)} "
                        f"gap excess unexplained — check {missing}; if still unexplained, "
                        "consider toxic alcohols, salicylates, uremia."
                    )
                    diff_keys.append("unexplained")
            elif lac_elevated or keto_elevated:
                steps.append(
                    f"Measured anions (≈{_fmt(explained)}) account for most of the "
                    f"{_fmt(delta_gap)} gap excess."
                )
        else:
            diff_keys.insert(0, "hagma")
            steps.append("Enter lactate and β-hydroxybutyrate to narrow the cause.")

        if creatinine is not None:
            if creatinine >= 4:
                steps.append(f"Creatinine {_fmt(creatinine)} — advanced renal failure; uremic acidosis a likely contributor.")
            elif creatinine >= 2:
                steps.append(f"Creatinine {_fmt(creatinine)} — renal impairment; may contribute to the gap.")
            else:
                steps.append(f"Creatinine {_fmt(creatinine)} — not significantly elevated; uremia unlikely to explain the gap.")

    # --- chloride / strong ion difference (Stewart view) ------------------
    # SID = Na⁺ − Cl⁻. Electroneutrality forces HCO₃⁻ to track it: chloride
    # gained relative to sodium narrows the SID and drives HCO₃⁻ down (the
    # force behind saline-induced hyperchloremic non-gap acidosis), chloride
    # lost relative to sodium widens it and pulls HCO₃⁻ up (the chloride
    # depletion of vomiting, NG suction and diuretics). Needs no bicarbonate,
    # so it reads out on a sodium and chloride alone.
    sid_core = None
    if na is not None and cl is not None and na > 0:
        if k is not None:
            sid = na + k - cl
            expr = f"(Na⁺+K⁺)−Cl⁻ = {_fmt(na)}+{_fmt(k)}−{_fmt(cl)}"
            shift = 0.0
        else:
            sid = na - cl
            expr = f"Na⁺−Cl⁻ = {_fmt(na)}−{_fmt(cl)}"
            shift = -ASSUMED_K   # no potassium: whole band drops by a typical K⁺
        low, high = SID_LOW + shift, SID_HIGH + shift
        marked_low, marked_high = SID_MARKED_LOW + shift, SID_MARKED_HIGH + shift

        sid_n = sid * 140.0 / na    # normalised to a sodium of 140
        cl_corr = cl * 140.0 / na   # the "corrected chloride"
        line = (f"Strong ion difference {expr} = {_fmt(sid)} "
                f"(normal ≈ {_fmt(low)}–{_fmt(high)}{'' if k is not None else ', no K⁺ entered'})")
        if abs(na - 140) >= 3:
            line += (f"; corrected to Na 140 → SID {_fmt(sid_n)}, "
                     f"chloride {_fmt(cl_corr)}.")
        else:
            line += "."
        steps.append(line)

        if sid_n < low:
            marked = sid_n < marked_low
            # the delta ratio splits the same acidosis a different way — don't name a
            # second diagnosis it contradicts
            if high_ag and delta_ratio is not None and delta_ratio >= 1:
                marked = False
            steps.append(
                f"→ chloride is high relative to sodium (corrected Cl⁻ {_fmt(cl_corr)}): "
                f"{'markedly ' if marked else ''}low SID, which forces HCO₃⁻ down — "
                f"{'a hyperchloremic non-gap metabolic acidosis' if marked else 'a mild chloride-mediated acidifying force'}. "
                "Sources: normal saline or other chloride-rich fluids, diarrhea, renal "
                "tubular acidosis, TPN, acetazolamide."
            )
            if marked:
                diff_keys.append("nagma")
            if high_ag:
                # the delta ratio measures the same split a different way; where the
                # two disagree, defer to it rather than asserting both readings
                if delta_ratio is not None and delta_ratio >= 1:
                    steps.append(
                        f"→ the delta ratio of {delta_ratio:.1f} still reads as a "
                        "predominantly high-gap acidosis, so take the low SID as a minor "
                        "hyperchloremic contribution rather than a second diagnosis."
                    )
                else:
                    cross = ("→ alongside the elevated gap this is a mixed high-gap and "
                             "hyperchloremic non-gap acidosis")
                    if delta_ratio is not None:
                        cross += f" — which is what the delta ratio of {delta_ratio:.1f} (<1) already showed."
                    else:
                        cross += "; the chloride is a second acid load on top of the unmeasured anions."
                    steps.append(cross)
                    if marked and "concurrent non-gap metabolic acidosis" not in extras:
                        extras.append("hyperchloremic non-gap component")
            elif metabolic_acidosis_present:
                steps.append("→ with a normal gap, the chloride is the acidosis.")
            elif marked and hco3 is not None and hco3 >= 22:
                steps.append(
                    "→ HCO₃⁻ is holding up despite the low SID: an alkalinizing process "
                    "is offsetting the chloride load."
                )
            if marked and not metabolic_acidosis_present and not high_ag:
                sid_core = "hyperchloremic (low SID) acidifying pattern"

        elif sid_n > high:
            marked = sid_n > marked_high
            if high_ag and delta_ratio is not None and delta_ratio <= 2:
                marked = False
            steps.append(
                f"→ chloride is low relative to sodium (corrected Cl⁻ {_fmt(cl_corr)}): "
                f"{'markedly ' if marked else ''}high SID, which pulls HCO₃⁻ up — "
                f"{'a chloride-depletion metabolic alkalosis' if marked else 'a mild chloride-depletion alkalinizing force'}. "
                "Sources: vomiting or NG suction, loop and thiazide diuretics, "
                "chloride-poor intake."
            )
            if marked:
                diff_keys.append("met_alk")
            if high_ag:
                # a pure high-gap acidosis replaces HCO₃⁻ with unmeasured anion and
                # leaves the SID untouched, so a raised SID here is a second process
                if delta_ratio is not None and delta_ratio <= 2:
                    steps.append(
                        f"→ the delta ratio of {delta_ratio:.1f} still reads as a "
                        "predominantly high-gap acidosis, so take the raised SID as a "
                        "minor chloride-depletion contribution rather than a second "
                        "diagnosis."
                    )
                else:
                    cross = ("→ a pure high-gap acidosis would leave the SID unchanged, so "
                             "the raised SID is a separate chloride-depletion force holding "
                             "the HCO₃⁻ up and masking part of the acidosis")
                    if delta_ratio is not None:
                        cross += f" — consistent with the delta ratio of {delta_ratio:.1f} (>2)."
                    else:
                        cross += "."
                    steps.append(cross)
                    if (marked and not metabolic_alkalosis_present
                            and "concurrent metabolic alkalosis" not in extras):
                        extras.append("concurrent metabolic alkalosis")
            if marked and not metabolic_alkalosis_present and not high_ag:
                sid_core = "chloride-depletion (high SID) alkalinizing pattern"
        else:
            steps.append(
                "→ SID normal: chloride is not exerting a meaningful acidifying or "
                "alkalinizing force here."
            )

    # --- osmolar gap (toxic-alcohol screen) ------------------------------
    if osm is not None:
        if na is not None and glucose is not None and bun is not None:
            calc = 2 * na + glucose / 18.0 + bun / 2.8
            og = osm - calc
            steps.append(
                f"Calculated osmolality = 2×{_fmt(na)} + {_fmt(glucose)}/18 + {_fmt(bun)}/2.8 = "
                f"{_fmt(calc)}; osmolar gap = {_fmt(osm)}−{_fmt(calc)} = {_fmt(og)}."
            )
            if og > 10:
                steps.append(
                    "→ elevated osmolar gap (>10): unmeasured osmoles — toxic alcohols "
                    "(methanol, ethylene glycol, isopropanol); also ethanol, mannitol."
                )
                diff_keys.append("osm")
            else:
                steps.append("→ osmolar gap not elevated (<10): toxic alcohols less likely.")
        else:
            steps.append("Enter Na⁺, glucose, and BUN to compute the osmolar gap.")

    # --- assemble headline ------------------------------------------------
    if high_ag and has_gas and primary is not None and "metabolic acidosis" not in primary:
        # a high gap alongside a non-acidosis primary is its own finding
        extras.insert(0, "high anion gap metabolic acidosis")

    if has_gas:
        core = primary
        if high_ag and "metabolic acidosis" in (primary or "") and "high anion gap" not in primary:
            core = primary.replace("metabolic acidosis", "high anion gap metabolic acidosis", 1)
        elif high_ag and primary == "normal acid-base status":
            # an elevated gap is a metabolic acidosis whatever the pH says
            core = "mixed disorder: high anion gap metabolic acidosis with a normal pH"
    elif high_ag:
        core = "high anion gap metabolic acidosis (from BMP; no gas)"
    elif metabolic_dir:
        core = metabolic_dir + " (gas needed to confirm)"
    elif sid_core:
        core = sid_core
        if hco3 is None:
            core += " (bicarbonate needed to confirm)"
    elif hco3 is not None:
        core = "no metabolic derangement on these values (gas needed for respiratory assessment)"
    else:
        core = None

    if core is None:
        headline = "Not enough data for a deterministic read"
        if not steps:
            steps.append(
                "Enter a bicarbonate (BMP) or a full gas (pH, pCO₂, HCO₃⁻). "
                "A clinical context alone is interpreted by the AI layer."
            )
    else:
        headline = core[0].upper() + core[1:]
        # "superimposed X" and "concurrent X" are the same claim about the same
        # disorder — keep whichever was found first, drop the rest
        cands = []
        for e in dict.fromkeys(extras):
            base = e.replace("superimposed ", "").replace("concurrent ", "")
            if e not in core and base not in core:
                cands.append((e, base))
        uniq_extras = []
        named: set[str] = set()
        for e, base in cands:
            # a bare "metabolic acidosis" adds nothing once a specific type of it
            # (high anion gap, non-gap) is already named
            if any(o != base and o.endswith(base) for _, o in cands):
                continue
            if base in named:
                continue
            named.add(base)
            uniq_extras.append(e)
        if uniq_extras:
            headline += " + " + " + ".join(uniq_extras)

    # de-duplicate differential keys, preserving order
    seen: set[str] = set()
    differential = []
    for key in diff_keys:
        if key not in seen:
            seen.add(key)
            differential.append(_DIFFERENTIALS[key])

    # compact recap of entered values, for the optional AI layer
    parts = []
    for label, val, unit in [
        ("pH", pH, ""), ("pCO₂", pco2, " mmHg"), ("HCO₃⁻", hco3, " mmol/L"),
        ("Na", na, ""), ("K", k, ""), ("Cl", cl, ""), ("albumin", albumin, " g/dL"),
        ("lactate", lactate, " mmol/L"), ("BHB", bhb, " mmol/L"),
        ("glucose", glucose, " mg/dL"), ("BUN", bun, " mg/dL"),
        ("creatinine", creatinine, " mg/dL"), ("osmolality", osm, " mOsm/kg"),
    ]:
        if val is not None:
            parts.append(f"{label} {_fmt(val)}{unit}")
    if corrected is not None:
        parts.append(f"anion gap {_fmt(corrected)}")
    if na is not None and cl is not None:
        if k is not None:
            parts.append(f"SID (Na+K−Cl) {_fmt(na + k - cl)}")
        else:
            parts.append(f"SID (Na−Cl) {_fmt(na - cl)}")
    summary = ", ".join(parts)

    return {
        "headline": headline,
        "steps": steps,
        "differential": differential,
        "warnings": warnings,
        "summary": summary,
    }
