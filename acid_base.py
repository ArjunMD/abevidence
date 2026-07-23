"""Deterministic acid-base interpretation for the Tools page.

Pure arithmetic — no AI, no network. Every input is optional; the engine
computes whatever the supplied values support and says what's missing:

  * Full gas (pH + pCO₂ + HCO₃⁻) → primary disorder + compensation check.
  * BMP only (Na + Cl + HCO₃⁻, no gas) → anion gap, delta ratio, and the
    metabolic direction from the bicarbonate (respiratory component can't be
    assessed without a gas).
  * Optional lactate, β-hydroxybutyrate, and glucose → "explain the gap":
    severity flags plus a quantitative check of whether the measured anions
    account for the gap excess (each mmol/L ≈ 1 of anion gap).

Formulas are the standard bedside ones: Winter's for metabolic acidosis, the
expected-pCO₂ rule for metabolic alkalosis, the acute/chronic HCO₃⁻ rules for
respiratory disorders, and the delta ratio for mixed metabolic pictures.

Reference values: pH 7.40, pCO2 40 mmHg, HCO3 24 mmol/L, anion gap 12,
lactate ≤2 mmol/L, β-hydroxybutyrate <0.6 mmol/L.
"""

NORMAL_HCO3 = 24.0
NORMAL_AG = 12.0
LACTATE_UPPER = 2.0   # upper normal lactate (mmol/L)
BHB_UPPER = 0.6       # upper normal β-hydroxybutyrate (mmol/L)

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
              osm=None) -> dict:
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
                ratio = (corrected - NORMAL_AG) / denom
                steps.append(
                    f"Delta ratio = ({_fmt(corrected)}−12)/(24−{_fmt(hco3)}) = {ratio:.1f}."
                )
                if ratio < 1:
                    steps.append("→ mixed high-gap and non-gap metabolic acidosis.")
                    extras.append("concurrent non-gap metabolic acidosis")
                    diff_keys.append("nagma")
                elif ratio <= 2:
                    steps.append("→ pure high anion gap metabolic acidosis.")
                else:
                    steps.append("→ concurrent metabolic alkalosis or chronic respiratory acidosis.")
                    extras.append("concurrent metabolic alkalosis")
                    diff_keys.append("met_alk")
            elif metabolic_alkalosis_present:
                steps.append(
                    "→ the elevated gap reveals a superimposed high anion gap "
                    "metabolic acidosis."
                )
            else:
                steps.append(
                    "→ HCO₃⁻ not low despite the elevated gap: concurrent "
                    "metabolic alkalosis (or chronic respiratory acidosis)."
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
    elif high_ag:
        core = "high anion gap metabolic acidosis (from BMP; no gas)"
    elif metabolic_dir:
        core = metabolic_dir + " (gas needed to confirm)"
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
        uniq_extras = [e for e in dict.fromkeys(extras) if e not in core]
        if uniq_extras:
            headline += " + " + " + ".join(uniq_extras)

    # de-duplicate differential keys, preserving order
    seen: set[str] = set()
    differential = []
    for k in diff_keys:
        if k not in seen:
            seen.add(k)
            differential.append(_DIFFERENTIALS[k])

    # compact recap of entered values, for the optional AI layer
    parts = []
    for label, val, unit in [
        ("pH", pH, ""), ("pCO₂", pco2, " mmHg"), ("HCO₃⁻", hco3, " mmol/L"),
        ("Na", na, ""), ("Cl", cl, ""), ("albumin", albumin, " g/dL"),
        ("lactate", lactate, " mmol/L"), ("BHB", bhb, " mmol/L"),
        ("glucose", glucose, " mg/dL"), ("BUN", bun, " mg/dL"),
        ("creatinine", creatinine, " mg/dL"), ("osmolality", osm, " mOsm/kg"),
    ]:
        if val is not None:
            parts.append(f"{label} {_fmt(val)}{unit}")
    if corrected is not None:
        parts.append(f"anion gap {_fmt(corrected)}")
    summary = ", ".join(parts)

    return {
        "headline": headline,
        "steps": steps,
        "differential": differential,
        "warnings": warnings,
        "summary": summary,
    }
