"""Dual-track acid-base interpretation for the Tools page.

Pure arithmetic — no AI, no network. Two parallel tracks run on whatever
values are entered (Seifter's merged view: they should tell the same story,
and divergence is itself informative):

  TRADITIONAL APPROACH (bicarbonate-centric / "Boston")
      pH, pCO₂, bicarbonate, anion gap → primary disorder
      (Henderson–Hasselbalch), compensation rules (Winter's etc.), delta
      ratio, then the classical gap workup (ketones, glucose, osmolar gap).
      Ends with its own synthesis.

  PHYSICOCHEMICAL APPROACH (Stewart)
      Base excess (or the bicarbonate deviation standing in without a gas),
      then the metabolic independent variables — SIDa, Atot — with the
      dependent SIDe ("should match SIDa") and the strong ion gap; then the
      decomposition: water / chloride / K / lactate effects, albumin /
      phosphate effects, and the residual ("does it add up?") with ketone
      itemisation. Ends with its own synthesis. (pCO₂, the third independent
      variable, is interpreted in the traditional track.)

  SYNTHESIS — whether the two tracks agree, and fluid choice by SID.

Inputs mirror the frameworks: gas (pH, pCO₂), strong ions (Na, K, Cl,
lactate, ± ionized Ca²⁺, Mg²⁺), bicarbonate + weak acids (CO₂, albumin,
phosphate). Glucose, β-hydroxybutyrate, BUN and osmolality are accessory —
differential tools, not framework variables. Albumin, glucose, phosphate,
iCa²⁺ and Mg²⁺ are assumed normal when blank (stated wherever it matters);
everything else is optional and the read uses what it has.

Each step is {"text", "calc"}: text carries the finding and its value, calc
the formula plus a one-line mechanism, for the UI to show on hover.

Reference values: pH 7.40, pCO₂ 40 mmHg, HCO₃⁻ 24 mmol/L, Na 140, Cl 102
(at Na 140), albumin 4.2 g/dL, phosphate 3.7 mg/dL, anion gap 12, lactate
≈1 (upper 2), β-hydroxybutyrate <0.6 mmol/L, SIDa ≈ 42–46, SIDe ≈ 36–40,
Atot charge ≈ 12–16 (all with the stated assumptions).
"""

NORMAL_NA = 140.0
NORMAL_CL = 102.0      # at a sodium of 140
NORMAL_ALB = 4.2       # g/dL
NORMAL_PHOS = 3.7      # mg/dL
NORMAL_K = 4.0
NORMAL_HCO3 = 24.0
NORMAL_AG = 12.0
LACTATE_BASE = 1.0     # typical baseline lactate (mmol/L)
LACTATE_UPPER = 2.0    # upper normal lactate (mmol/L)
BHB_UPPER = 0.6        # upper normal β-hydroxybutyrate (mmol/L)
PHOS_CHARGE_74 = 0.586  # mEq/L of charge per mg/dL of phosphate at pH 7.4

# An individual effect below this magnitude (mEq/L) is noise; above MARKED it
# is a major driver worth leading with.
SIG = 3.0
MARKED = 6.0
K_GROSS = 1.5          # |K−4| beyond which potassium gets its own line

# One-line differentials keyed by process. Kept short on purpose.
_DIFFERENTIALS = {
    "water_ac": "Free-water excess (dilutional acidosis): hypotonic fluids, "
                "ADH excess (hypovolemia, SIADH), heart/liver/renal failure, "
                "polydipsia.",
    "water_alk": "Free-water deficit (contraction alkalosis): diuretics, "
                 "insensible or GI water loss, poor intake, diabetes insipidus.",
    "nagma": "Hyperchloremic (low-SID) acidosis: saline/chloride-rich fluids, "
             "diarrhea, renal tubular acidosis, TPN, acetazolamide, ureteral "
             "diversion.",
    "met_alk": "Chloride-depletion (high-SID) alkalosis: vomiting/NG suction, "
               "loop and thiazide diuretics, hypokalemia, hyperaldosteronism, "
               "milk-alkali.",
    "hagma": "Unmeasured anions (GOLDMARK): glycols, oxoproline, L-/D-lactate, "
             "methanol, aspirin, renal failure, ketoacidosis.",
    "lactic": "Lactic acidosis: type A (sepsis, hypoperfusion, ischemia) or "
              "type B (metformin, liver failure, malignancy, thiamine deficiency).",
    "keto": "Ketoacidosis: diabetic, alcoholic, or starvation.",
    "unexplained": "Unexplained anions: toxic alcohols (methanol/ethylene "
                   "glycol — check osmolar gap), salicylates, uremia, "
                   "5-oxoproline.",
    "osm": "Elevated osmolar gap: methanol, ethylene glycol, isopropanol "
           "(also ethanol, mannitol, propylene glycol).",
    "resp_ac": "Respiratory acidosis: sedation/opioids, COPD/asthma, "
               "neuromuscular weakness, chest-wall/obesity hypoventilation.",
    "resp_alk": "Respiratory alkalosis: anxiety/pain, hypoxia, PE, sepsis, "
                "salicylates, pregnancy, hepatic failure.",
}


def _fmt(x: float) -> str:
    """Whole numbers without a trailing '.0', one decimal otherwise."""
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


def _sfmt(x: float) -> str:
    """Signed format: '+3', '−4.5', '0'."""
    if abs(x) < 0.05:
        return "0"
    return ("+" if x > 0 else "−") + _fmt(abs(x))


def _standard_base_excess(pH: float, hco3: float) -> float:
    """Standard base excess (mEq/L), Siggaard-Andersen / Van Slyke approximation.
    Negative values are a base deficit. Estimated from a full gas — the analyzer
    computes the same quantity from pH and HCO₃⁻."""
    return 0.9287 * (hco3 - 24.4 + 14.83 * (pH - 7.4))


def interpret(pH=None, pco2=None, hco3=None, na=None, cl=None, albumin=None,
              lactate=None, bhb=None, glucose=None, bun=None,
              osm=None, k=None, vbg=False, ca=None, mg=None, phos=None) -> dict:
    """Run both tracks on whatever values are supplied (all optional).
    vbg=True converts gas values to arterial estimates (pH +0.03, pCO₂ −5).
    Returns {headline, sections, differential, warnings, summary, next,
    needs}: sections is a list of {"title": str-or-None, "steps": [...]},
    each step {"text", "calc"}; summary primes the optional AI layer; next
    says what would sharpen the read; needs = {"gas": reason-or-None,
    "split": [lab, ...]}."""
    warnings: list[str] = []
    resp_extras: list[str] = []   # superimposed disorders found on the gas
    processes: list[str] = []     # named metabolic components (Stewart side)
    diff_keys: list[str] = []     # which differentials to show

    # section step lists, assembled into display order at the end
    s_pre: list[dict] = []      # untitled preamble (VBG note, derived HCO₃⁻)
    s_trad: list[dict] = []     # traditional (bicarbonate-centric) track
    s_phys: list[dict] = []     # physicochemical (Stewart) track
    s_syn: list[dict] = []      # cross-track synthesis

    def add(sec: list, text: str, calc: str = None) -> None:
        sec.append({"text": text, "calc": calc})

    # =====================================================================
    # Compute everything first; assemble the display afterwards.
    # =====================================================================

    # --- gas pre-processing ----------------------------------------------
    vbg_applied = vbg and (pH is not None or pco2 is not None)
    if vbg_applied:
        if pH is not None:
            pH = pH + 0.03
        if pco2 is not None:
            pco2 = pco2 - 5.0

    hco3_derived = False
    if pH is not None and pco2 is not None and hco3 is None:
        # the analyzer itself derives HCO₃⁻ from pH and pCO₂ — do the same
        hco3 = 0.03 * pco2 * (10 ** (pH - 6.1))
        hco3_derived = True

    has_gas = pH is not None and pco2 is not None and hco3 is not None

    # --- input sanity (only for values actually provided) ----------------
    if pH is not None and (pH < 6.8 or pH > 7.8):
        warnings.append("pH outside 6.8–7.8 — recheck the value entered.")
    if pco2 is not None and pco2 <= 0:
        warnings.append("pCO₂ should be positive — recheck the value.")
    if hco3 is not None and hco3 <= 0:
        warnings.append("HCO₃⁻ should be positive — recheck the value.")
    if na is not None and (na < 100 or na > 185):
        warnings.append("Na⁺ outside 100–185 — recheck the value.")
    if cl is not None and (cl < 60 or cl > 140):
        warnings.append("Cl⁻ outside 60–140 — recheck the value.")

    # --- assumed-normal stand-ins (stated wherever they matter) ----------
    albumin_assumed = albumin is None
    alb_used = NORMAL_ALB if albumin_assumed else albumin
    phos_assumed = phos is None
    phos_used = NORMAL_PHOS if phos_assumed else phos
    ph_used = pH if pH is not None else 7.4

    # --- charges, SIDa / SIDe / Atot -------------------------------------
    alb_charge = 10.0 * alb_used * (0.123 * ph_used - 0.631)
    phos_charge = (phos_used / 3.1) * (0.309 * ph_used - 0.469)
    atot_charge = alb_charge + phos_charge

    sida = None
    ion_assumed = []
    if na is not None and k is not None and cl is not None:
        ca_meq = 2.0 * (ca if ca is not None else 1.2)     # ionized, mmol/L → mEq/L
        if ca is None:
            ion_assumed.append("iCa²⁺ 1.2 mmol/L")
        mg_meq = 0.823 * (mg if mg is not None else 2.0)   # total, mg/dL → mEq/L
        if mg is None:
            ion_assumed.append("Mg²⁺ 2.0 mg/dL")
        sida = na + k + ca_meq + mg_meq - cl - (lactate if lactate is not None else 0.0)

    side = hco3 + atot_charge if hco3 is not None else None
    sig = sida - side if (sida is not None and side is not None) else None

    # --- classical gap ----------------------------------------------------
    ag = None
    corrected = None
    ag_elevated = False
    if na is not None and cl is not None and hco3 is not None:
        ag = na - cl - hco3
        corrected = ag + 2.5 * (NORMAL_ALB - alb_used)
        ag_elevated = corrected > NORMAL_AG

    # --- metabolic base excess / bicarbonate deviation -------------------
    sbe = None
    if has_gas:
        sbe = _standard_base_excess(pH, hco3)
    elif hco3 is not None:
        sbe = hco3 - NORMAL_HCO3
    dev = hco3 - NORMAL_HCO3 if hco3 is not None else None

    # --- Stewart effect lines --------------------------------------------
    water_eff = None
    chloride_eff = None
    k_eff = None
    lactate_eff = None
    alb_eff = None
    phos_eff = None
    residual = None
    lac_elevated = lactate is not None and lactate > LACTATE_UPPER
    keto_elevated = bhb is not None and bhb >= BHB_UPPER

    if na is not None and na > 0:
        water_eff = 0.3 * (na - NORMAL_NA)
        if cl is not None:
            chloride_eff = NORMAL_CL - cl * NORMAL_NA / na
    if k is not None and abs(k - NORMAL_K) >= K_GROSS:
        k_eff = k - NORMAL_K
    if lactate is not None:
        lactate_eff = -(lactate - LACTATE_BASE) if lactate > LACTATE_BASE else 0.0
    if water_eff is not None or chloride_eff is not None:
        alb_eff = 2.5 * (NORMAL_ALB - alb_used)
        if phos is not None:
            phos_eff = PHOS_CHARGE_74 * (NORMAL_PHOS - phos)
    if sbe is not None and water_eff is not None and chloride_eff is not None:
        residual = (sbe - water_eff - chloride_eff
                    - (alb_eff if alb_eff is not None else 0.0)
                    - (phos_eff if phos_eff is not None else 0.0)
                    - (k_eff if k_eff is not None else 0.0)
                    - (lactate_eff if lactate_eff is not None else 0.0))

    unmeasured_present = residual is not None and residual <= -SIG
    borderline = None   # sub-threshold residual, named when it offsets a force

    keto_explained = None
    keto_unexplained = None
    if unmeasured_present and bhb is not None:
        keto_explained = max(0.0, bhb - BHB_UPPER)
        keto_unexplained = -residual - keto_explained

    og = None
    if osm is not None and na is not None and glucose is not None and bun is not None:
        og = osm - (2 * na + glucose / 18.0 + bun / 2.8)

    # =====================================================================
    # Preamble — gas conversions, shared by both tracks
    # =====================================================================
    if vbg_applied:
        shown = []
        if pH is not None:
            shown.append(f"pH → {_fmt(pH)}")
        if pco2 is not None:
            shown.append(f"pCO₂ → {_fmt(pco2)}")
        add(s_pre,
            "VBG converted to arterial estimates: " + ", ".join(shown) + ".",
            "pH + 0.03; pCO₂ − 5\nApproximate — agreement degrades in shock "
            "and low-flow states.")
    if hco3_derived:
        add(s_pre,
            f"HCO₃⁻ derived from the gas = {_fmt(hco3)} mmol/L.",
            "0.03×pCO₂×10^(pH−6.1)\nHenderson–Hasselbalch — the same "
            "derivation the analyzer uses.")

    # =====================================================================
    # TRADITIONAL APPROACH (bicarbonate-centric)
    # =====================================================================
    if pH is not None:
        status = ("acidemia" if pH < 7.35 else
                  "alkalemia" if pH > 7.45 else "normal")
        add(s_trad, f"pH {_fmt(pH)} ({status}).",
            "The dependent outcome both tracks explain.")
    if pco2 is not None:
        add(s_trad, f"pCO₂ {_fmt(pco2)}.",
            "The respiratory determinant in both tracks\nCO₂ dissolves to "
            "carbonic acid; ventilation sets it.")
    if pH is None and pco2 is None:
        add(s_trad, "pH / pCO₂ not entered — respiratory side unassessed.")

    if hco3 is not None:
        add(s_trad, f"Bicarbonate {_fmt(hco3)}.",
            "The dependent metabolic readout. A normal value can still hide "
            "offsetting forces — the Stewart residual shows them.")

    if ag is not None:
        text = f"Anion gap {_fmt(ag)}"
        if not albumin_assumed and abs(corrected - ag) >= 0.05:
            text += f", albumin-corrected {_fmt(corrected)}"
        if corrected > 20:
            text += " (there are unmeasured anions)."
        elif ag_elevated:
            text += " (suggests unmeasured anions)."
        else:
            text += " (normal)."
        add(s_trad, text,
            "Na − Cl − HCO₃⁻; corrected gap = AG + 2.5×(4.2 − albumin)\n"
            "Classical unmeasured-anion estimate"
            + (" — albumin assumed 4.2." if albumin_assumed else ".")
            + "\nMild elevations (≈12–20) can be baseline/analyzer variation, "
            "combined measurement error of three analytes, alkalemia, "
            "hyperphosphatemia, or low K/Ca/Mg — a corrected gap >20 cannot.")

    primary = None
    comp_note = None
    if has_gas:
        hco3_low, hco3_high = hco3 < 22, hco3 > 26
        pco2_low, pco2_high = pco2 < 35, pco2 > 45

        if pH < 7.35:
            if hco3_low and pco2_high:
                primary = "combined metabolic and respiratory acidosis"
            elif pco2_high:
                primary = "respiratory acidosis"
            else:
                primary = "metabolic acidosis"
        elif pH > 7.45:
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

        add(s_trad, f"Primary disorder: {primary}.",
            "pH = 6.1 + log(HCO₃⁻ / (0.03×pCO₂))\nHenderson–Hasselbalch — the "
            "pH names the side, pCO₂ vs HCO₃⁻ names the culprit.")

        if primary in ("metabolic acidosis", "metabolic alkalosis"):
            if primary == "metabolic acidosis":
                expected = 1.5 * hco3 + 8  # Winter's formula
                calc = ("Expected pCO₂ = 1.5×HCO₃⁻ + 8 (±2)\nWinter's formula — "
                        "the pCO₂ appropriate compensation should reach.\n"
                        "Bedside shortcuts: pCO₂ ≈ last two digits of the pH; "
                        "pCO₂ ≈ HCO₃⁻ + 15.")
                name = "Winter's"
            else:
                expected = 0.7 * hco3 + 21  # expected pCO2 for metabolic alkalosis
                calc = ("Expected pCO₂ = 0.7×HCO₃⁻ + 21 (±2)\nThe pCO₂ "
                        "appropriate compensation should reach.")
                name = "expected-pCO₂ rule"
            text = (f"Compensation ({name}): expected pCO₂ {_fmt(expected)} ±2, "
                    f"actual {_fmt(pco2)}")
            if pco2 > expected + 2:
                text += " → pCO₂ higher than expected: superimposed respiratory acidosis."
                resp_extras.append("superimposed respiratory acidosis")
                diff_keys.append("resp_ac")
            elif pco2 < expected - 2:
                text += " → pCO₂ lower than expected: superimposed respiratory alkalosis."
                resp_extras.append("superimposed respiratory alkalosis")
                diff_keys.append("resp_alk")
            else:
                text += " → appropriate respiratory compensation."
                comp_note = "appropriate respiratory compensation"
            add(s_trad, text, calc)

        elif primary in ("respiratory acidosis", "respiratory alkalosis"):
            if primary == "respiratory acidosis":
                acute = NORMAL_HCO3 + 0.1 * (pco2 - 40)     # HCO3 rises 1 per 10 mmHg
                chronic = NORMAL_HCO3 + 0.35 * (pco2 - 40)  # rises 3.5 per 10 mmHg
                calc = ("Acute: 24 + 0.1×(pCO₂ − 40); chronic: 24 + "
                        "0.35×(pCO₂ − 40)\nWhere the HCO₃⁻ should sit for the "
                        "duration of the hypercapnia.\nΔpH shortcut: pH falls "
                        "≈0.08 per 10 mmHg pCO₂ acutely, ≈0.03 chronically.")
            else:
                acute = NORMAL_HCO3 - 0.2 * (40 - pco2)     # HCO3 falls 2 per 10 mmHg
                chronic = NORMAL_HCO3 - 0.4 * (40 - pco2)   # falls 4 per 10 mmHg
                calc = ("Acute: 24 − 0.2×(40 − pCO₂); chronic: 24 − "
                        "0.4×(40 − pCO₂)\nWhere the HCO₃⁻ should sit for the "
                        "duration of the hypocapnia.\nΔpH shortcut: pH rises "
                        "≈0.08 per 10 mmHg pCO₂ drop acutely, ≈0.03 chronically.")
            text = (f"Compensation: expected HCO₃⁻ acute ≈ {_fmt(acute)}, "
                    f"chronic ≈ {_fmt(chronic)}, actual {_fmt(hco3)}")
            if primary == "respiratory acidosis":
                if hco3 < acute - 2:
                    text += " → below acute expected: superimposed metabolic acidosis."
                    resp_extras.append("superimposed metabolic acidosis")
                elif hco3 > chronic + 2:
                    text += " → above chronic expected: superimposed metabolic alkalosis."
                    resp_extras.append("superimposed metabolic alkalosis")
                    diff_keys.append("met_alk")
                elif hco3 <= acute + 2:
                    text += " → consistent with acute respiratory acidosis."
                    comp_note = "consistent with acute"
                else:
                    text += " → consistent with chronic (or partly compensated) respiratory acidosis."
                    comp_note = "consistent with chronic (or partly compensated)"
                diff_keys.append("resp_ac")
            else:
                if hco3 > acute + 2:
                    text += " → above acute expected: superimposed metabolic alkalosis."
                    resp_extras.append("superimposed metabolic alkalosis")
                    diff_keys.append("met_alk")
                elif hco3 < chronic - 2:
                    text += " → below chronic expected: superimposed metabolic acidosis."
                    resp_extras.append("superimposed metabolic acidosis")
                elif hco3 >= acute - 2:
                    text += " → consistent with acute respiratory alkalosis."
                    comp_note = "consistent with acute"
                else:
                    text += " → consistent with chronic (or partly compensated) respiratory alkalosis."
                    comp_note = "consistent with chronic (or partly compensated)"
                diff_keys.append("resp_alk")
            add(s_trad, text, calc)
    elif pH is not None or pco2 is not None or hco3 is not None:
        add(s_trad, "pH and pCO₂ needed for the primary-disorder and "
                    "compensation analysis.")

    if corrected is not None and ag_elevated:
        denom = NORMAL_HCO3 - hco3
        if denom > 0.5:
            dr = (corrected - NORMAL_AG) / denom
            read = ("a concurrent non-gap component (chloride or dilutional)"
                    if dr < 1 else
                    "a pure high-gap acidosis" if dr <= 2 else
                    "a concurrent alkalinizing process holding the HCO₃⁻ up")
            add(s_trad,
                f"Delta ratio {dr:.1f} → {read}.",
                "(gap − 12)/(24 − HCO₃⁻)\nHow much the gap rose versus how far "
                "the HCO₃⁻ fell.\nEquivalent form — corrected bicarbonate = "
                "HCO₃⁻ + (gap − 12): >26 hidden metabolic alkalosis, "
                "<22 concurrent non-gap acidosis.")

    # classical gap workup: ketones, glucose, osmolar gap
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
        add(s_trad, kmsg)
        if keto_elevated:
            diff_keys.append("keto")

    if bhb is None and glucose is not None and glucose > 250:
        add(s_trad, f"Glucose {_fmt(glucose)} elevated — check β-hydroxybutyrate "
            "to assess for DKA.")

    if osm is not None:
        if og is not None:
            calc = ("Measured − (2×Na + glucose/18 + BUN/2.8)\nUnaccounted "
                    "osmoles suggest a toxic alcohol.")
            if og > 10:
                add(s_trad,
                    f"Osmolar gap {_fmt(og)} → elevated (>10): unmeasured osmoles — "
                    "toxic alcohols (methanol, ethylene glycol, isopropanol); also "
                    "ethanol, mannitol.", calc)
                diff_keys.append("osm")
            else:
                add(s_trad, f"Osmolar gap {_fmt(og)} — not elevated (<10): toxic "
                    "alcohols less likely.", calc)
        else:
            add(s_trad, "Enter Na⁺, glucose, and BUN to compute the osmolar gap.")

    # traditional synthesis
    if has_gas and primary is not None:
        prim_disp = primary
        if ag_elevated and "metabolic acidosis" in primary:
            prim_disp = primary.replace("metabolic acidosis",
                                        "high-gap metabolic acidosis", 1)
        syn = " + ".join([prim_disp] + resp_extras)
        if comp_note:
            syn += f" — {comp_note}"
        add(s_trad, f"Synthesis: {syn}.")
    elif hco3 is not None:
        if dev < -2:
            base = "metabolic acidosis"
        elif dev > 2:
            base = "metabolic alkalosis"
        else:
            base = "no bicarbonate shift"
        if ag_elevated:
            base += " with a high anion gap"
        add(s_trad, f"Synthesis: {base} — gas needed to separate primary "
            "from compensation.")

    # =====================================================================
    # PHYSICOCHEMICAL APPROACH (Stewart)
    # =====================================================================
    if has_gas:
        add(s_phys,
            f"Base excess ≈ {_sfmt(sbe)} mEq/L (net metabolic burden).",
            "0.9287×(HCO₃⁻ − 24.4 + 14.83×(pH − 7.4))\nVan Slyke standard "
            "base excess — the sum the effect lines below must explain. "
            "pCO₂, the respiratory independent variable, is interpreted in "
            "the traditional track.")
    elif hco3 is not None:
        add(s_phys,
            f"Bicarbonate deviation {_sfmt(dev)} mEq/L (stand-in for base "
            "excess; pCO₂ assumed ≈ 40).",
            "HCO₃⁻ − 24\nWithout a gas the true base excess is not "
            "computable; the effect lines below must explain this stand-in.")

    if sida is not None:
        low_causes = ("free-water excess, chloride excess"
                      + (", or lactate" if lactate is not None else ""))
        tag = ("high → chloride-depletion alkalosis, or unmeasured anions"
               if sida > 46 else
               f"low → strong-ion acidosis due to {low_causes}"
               if sida < 42 else
               "normal")
        calc = ("Na + K + Ca + Mg − Cl" +
                (" − lactate" if lactate is not None else "") +
                " (mEq/L; normal ≈ 42–46)")
        if ion_assumed:
            calc += "\nAssumed: " + ", ".join(ion_assumed) + "."
        calc += ("\nA low value is reliably acidifying; a high value can be "
                 "alkalosis OR a large anion gap; a normal value can still "
                 "hide offsetting effects — the decomposition below shows them.")
        add(s_phys, f"SIDa {_fmt(sida)} ({tag}).", calc)

    # Atot — the other metabolic independent variable. Interpretation rule:
    # more weak acid = more acid; less = alkalosis. Its members move for
    # non-acid-base reasons (albumin with illness, phosphate with renal
    # failure), so a deranged Atot is an incidental force, never compensation.
    if (not albumin_assumed) or (not phos_assumed) or side is not None:
        if albumin_assumed and phos_assumed:
            tag = "assumed normal — albumin/phosphate not entered"
        elif atot_charge < 12:
            tag = "low → hypoalbuminemic alkalosis; also masks the anion gap"
        elif atot_charge > 16:
            tag = "high → weak-acid acidosis (usually phosphate retention)"
        else:
            tag = "normal"
        add(s_phys, f"Atot charge {_fmt(atot_charge)} ({tag}).",
            "Albumin charge 10×albumin×(0.123×pH − 0.631) + phosphate charge "
            "(phosphate/3.1)×(0.309×pH − 0.469) (normal ≈ 12–16)\n"
            "The weak-acid independent variable: more weak acid = more acid, "
            "less = alkalosis. Low albumin is a true alkalinizing force (and "
            "hides anions on an uncorrected gap); high phosphate (renal "
            "failure) is a true acidosis. Decomposed below.")

    if side is not None:
        if sida is not None:
            tag = "should match SIDa"
        else:
            tag = ("buffer consumed — acid is present" if side < 36 else
                   "alkalosis" if side > 40 else "normal")
        add(s_phys, f"SIDe {_fmt(side)} ({tag}).",
            "HCO₃⁻ + albumin charge + phosphate charge (normal ≈ 36–40)\n"
            "The effective SID — the charge the dependent side actually "
            "provides. In fully measured plasma SIDe = SIDa; unmeasured "
            "anions open the gap."
            + ("\nAlbumin assumed 4.2." if albumin_assumed else ""))

    if sig is not None:
        text = f"Strong ion gap = SIDa − SIDe = {_fmt(sig)}"
        if albumin_assumed:
            text += (" (albumin assumed — mirrors the anion gap; measure "
                     "albumin to make it independent).")
        else:
            if sig >= 8:
                text += " (elevated — unmeasured anions)."
            elif sig <= 2:
                text += " (no unmeasured-anion signal)."
            else:
                text += " (within the healthy band, ≈ 4–6 with these approximations)."
        add(s_phys, text,
            "SIDa − SIDe\nThe unmeasured-anion concentration itself, obtained "
            "by subtracting two charge sums — not inferred as a leftover from "
            "the base excess (that's the residual) and not read against a "
            "population normal (that's the anion gap). Healthy baseline "
            "≈ 4–6 with these approximations.")

    # decomposing the SID
    if water_eff is not None:
        if water_eff <= -SIG:
            add(s_phys, f"Free-water effect {_sfmt(water_eff)} (acidifying).",
                "0.3×(Na − 140)\nFree water shrinks the SID by dilution — acidifying.")
            processes.append("dilutional (free-water) component")
            diff_keys.append("water_ac")
        elif water_eff >= SIG:
            add(s_phys, f"Free-water effect {_sfmt(water_eff)} (alkalinizing).",
                "0.3×(Na − 140)\nA free-water deficit concentrates the strong "
                "ions and widens the SID — alkalinizing.")
            processes.append("contraction (free-water deficit) alkalosis")
            diff_keys.append("water_alk")
        else:
            add(s_phys, f"Free-water effect {_sfmt(water_eff)} (negligible).",
                "0.3×(Na − 140)\nFree water shifts the SID by dilution or "
                "concentration.")

        # Hyperglycemia dilutes the sodium by osmotic water shift; above a
        # material correction (~2 mEq/L) the measured Na misstates the true
        # water balance. Glucose not entered → assumed normal, no correction.
        if glucose is not None:
            na_shift = 1.6 * (glucose - 100.0) / 100.0
            if na_shift >= 2:
                calc = ("Na + 1.6×(glucose − 100)/100\nHyperglycemia pulls "
                        "water into plasma, diluting the measured Na "
                        "(translocational).")
                if water_eff <= -2:
                    add(s_phys,
                        f"Glucose-corrected Na = {_fmt(na + na_shift)} → part of "
                        "the low Na is osmotic water shift from hyperglycemia "
                        "(translocational) — that share of the dilutional force "
                        "should resolve as glucose falls.", calc)
                else:
                    add(s_phys,
                        f"Glucose-corrected Na = {_fmt(na + na_shift)} → measured "
                        "Na understates tonicity — hyperglycemia may be masking "
                        "a free-water deficit.", calc)

    if chloride_eff is not None:
        calc = ("102 − (Cl⁻×140/Na)\nChloride relative to sodium (the "
                "correction removes the water component): chloride excess "
                "narrows the SID — acidifying; chloride deficit widens it — "
                "alkalinizing.")
        if chloride_eff <= -SIG:
            sev = ", major" if chloride_eff <= -MARKED else ""
            add(s_phys, f"Chloride effect {_sfmt(chloride_eff)} (acidifying — "
                f"hyperchloremic{sev}).", calc)
            processes.append("hyperchloremic component")
            diff_keys.append("nagma")
        elif chloride_eff >= SIG:
            sev = ", major" if chloride_eff >= MARKED else ""
            add(s_phys, f"Chloride effect {_sfmt(chloride_eff)} (alkalinizing — "
                f"chloride depletion{sev}).", calc)
            processes.append("chloride-depletion alkalosis")
            diff_keys.append("met_alk")
        else:
            add(s_phys, f"Chloride effect {_sfmt(chloride_eff)} (negligible).", calc)
    elif water_eff is not None:
        add(s_phys, "Chloride effect: needs Cl⁻ — not assessed.")
    elif hco3 is not None:
        add(s_phys, "Na⁺ and Cl⁻ needed to decompose the SID.")

    if k_eff is not None:
        add(s_phys,
            f"K⁺ effect {_sfmt(k_eff)} "
            f"({'alkalinizing' if k_eff > 0 else 'acidifying'}).",
            "K − 4\nA strong cation — shown only when grossly abnormal.")

    if lactate is not None:
        calc = ("−(lactate − 1)\nA measured strong anion — each mmol/L narrows "
                "the SID by ≈1: acidifying.")
        if lactate > 4:
            add(s_phys, f"Lactate effect {_sfmt(lactate_eff)} (acidifying — lactate "
                f"{_fmt(lactate)}, ≥4: sepsis/shock range).", calc)
        elif lactate > LACTATE_UPPER:
            add(s_phys, f"Lactate effect {_sfmt(lactate_eff)} (acidifying).", calc)
        else:
            add(s_phys, f"Lactate effect {_sfmt(lactate_eff)} (negligible — "
                f"lactate {_fmt(lactate)}).", calc)
        if lactate_eff is not None and lactate_eff <= -SIG:
            processes.append("lactic acidosis")
        if lac_elevated:
            diff_keys.append("lactic")

    sid_terms = [("free water", water_eff), ("chloride", chloride_eff),
                 ("K⁺", k_eff), ("lactate", lactate_eff)]
    sid_present = [(n, v) for n, v in sid_terms if v is not None]
    sid_net = sum(v for _, v in sid_present) if sid_present else None
    if sid_present:
        drivers = [(n, v) for n, v in sid_present if abs(v) >= 2]
        if drivers:
            dtxt = ", ".join(f"{n} {_sfmt(v)}" for n, v in drivers)
            add(s_phys, f"→ Net strong-ion force {_sfmt(sid_net)} — driven by {dtxt}.")
        else:
            add(s_phys, f"→ No meaningful strong-ion force (net {_sfmt(sid_net)}).")

    # decomposing the Atot
    atot_net = None
    if alb_eff is not None:
        calc = ("2.5×(4.2 − albumin)\nAlbumin is the main weak acid (Atot): "
                "low albumin removes anionic charge — alkalinizing (and masks "
                "unmeasured anions on an uncorrected gap); high albumin — "
                "acidifying.")
        if albumin_assumed:
            add(s_phys, "Albumin effect 0 (assumed albumin 4.2 — enter to "
                "confirm).", calc)
        elif alb_eff >= SIG:
            add(s_phys, f"Albumin effect {_sfmt(alb_eff)} (alkalinizing — "
                "hypoalbuminemia).", calc)
            processes.append("hypoalbuminemic alkalinizing effect")
        elif alb_eff <= -SIG:
            add(s_phys, f"Albumin effect {_sfmt(alb_eff)} (acidifying — "
                "hyperalbuminemia/hemoconcentration).", calc)
        else:
            add(s_phys, f"Albumin effect {_sfmt(alb_eff)} (negligible).", calc)

        if phos_eff is not None:
            calc = ("0.586×(3.7 − phosphate)\nPhosphate is the minor weak acid "
                    "(Atot): retained phosphate adds anionic charge — "
                    "acidifying (renal failure); low phosphate — mildly "
                    "alkalinizing.")
            if phos_eff <= -SIG:
                add(s_phys, f"Phosphate effect {_sfmt(phos_eff)} (acidifying — "
                    "hyperphosphatemia).", calc)
                processes.append("hyperphosphatemic acidifying effect")
            elif phos_eff >= SIG:
                add(s_phys, f"Phosphate effect {_sfmt(phos_eff)} (alkalinizing — "
                    "hypophosphatemia).", calc)
            else:
                add(s_phys, f"Phosphate effect {_sfmt(phos_eff)} (negligible).", calc)

        atot_net = alb_eff + (phos_eff if phos_eff is not None else 0.0)
        if not (albumin_assumed and phos_eff is None):
            if atot_net >= 2:
                dir_tag = " — alkalinizing"
            elif atot_net <= -2:
                dir_tag = " — acidifying"
            else:
                dir_tag = " (negligible)"
            add(s_phys, f"→ Net Atot (weak-acid) force {_sfmt(atot_net)}{dir_tag}.")

    # does it add up? — the residual
    if residual is not None:
        bundle = []
        if albumin_assumed:
            bundle.append("albumin")
        if lactate is None:
            bundle.append("lactate")
        bundle.append("unmeasured anions")
        label = " + ".join(bundle)
        be_term = "base excess" if has_gas else "HCO₃⁻ deviation"
        calc = (f"{be_term[0].upper()}{be_term[1:]} − (sum of the effect lines)\n"
                "The acid or base the measured lines cannot explain.")
        text = f"Does it add up? Residual {_sfmt(residual)} ({label})"
        if residual <= -SIG:
            sev = "major " if residual <= -MARKED else ""
            text += f" → {sev}unexplained acid load."
            if albumin_assumed:
                text += (" (If albumin is low, the true load is larger "
                         "than this number.)")
            processes.append("unmeasured-anion component")
        elif residual >= SIG:
            if albumin_assumed:
                text += (" → an alkalinizing residual — most often hypoalbuminemia; "
                         "add albumin to confirm.")
            else:
                text += (" → alkalinizing residual despite the albumin line: "
                         "unmeasured cations, halide interference, or a lab error.")
        elif residual <= -2:
            text += " — a mild unexplained load (below the ±3 significance cut)."
            borderline = ("a mild unmeasured-anion load" if not albumin_assumed
                          else "a mild unmeasured-anion/albumin load")
        elif residual >= 2:
            text += " — a mild alkalinizing residual (below the ±3 significance cut)."
            borderline = "a mild alkalinizing residual"
        else:
            text += " — the effect lines account for the base excess."
        add(s_phys, text, calc)

    if unmeasured_present:
        load = -residual
        if lactate is None and bhb is None:
            diff_keys.append("hagma")
            add(s_phys,
                f"Enter lactate and β-hydroxybutyrate to itemise the "
                f"≈{_fmt(load)} mEq/L bundled in the residual.")
        elif bhb is None:
            diff_keys.append("hagma")
            add(s_phys,
                f"Enter β-hydroxybutyrate to itemise the ≈{_fmt(load)} mEq/L "
                "residual (lactate is already split out above).")
        else:
            calc = ("Ketone share = BHB − 0.6; unexplained = residual − ketone "
                    "share\nEach mmol/L of anion ≈ 1 mEq/L of acid load.")
            if keto_unexplained > 5:
                text = (
                    f"Ketones explain ≈{_fmt(keto_explained)} of the ≈{_fmt(load)} "
                    f"residual; ≈{_fmt(keto_unexplained)} unexplained → consider "
                    "toxic alcohols (osmolar gap), salicylates, uremia"
                )
                if lactate is None:
                    text += " — and check a lactate"
                text += "."
                if keto_elevated:
                    text += (" (β-hydroxybutyrate doesn't count acetoacetate, "
                             "so ketoacids likely explain part of this.)")
                add(s_phys, text, calc)
                diff_keys.append("unexplained")
            elif keto_elevated:
                add(s_phys,
                    f"Ketones (≈{_fmt(keto_explained)}) account for most of the "
                    f"≈{_fmt(load)} residual.", calc)

    # Stewart synthesis
    if residual is not None:
        forces = []
        if sid_net is not None:
            forces.append(f"strong ions {_sfmt(sid_net)}")
        if atot_net is not None:
            forces.append(f"Atot {_sfmt(atot_net)}")
        lead = " and ".join(forces) if forces else "the measured forces"
        if unmeasured_present:
            syn = (f"Synthesis: {lead} leave a residual {_sfmt(residual)} → "
                   "a real unmeasured-anion load")
            if keto_explained is not None:
                syn += f" — ketones cover ≈{_fmt(keto_explained)}"
                if keto_unexplained is not None and keto_unexplained > 5:
                    syn += f", ≈{_fmt(keto_unexplained)} still unaccounted"
            else:
                syn += " — not yet itemised"
            if og is not None and og > 10:
                syn += "; the elevated osmolar gap keeps toxic alcohols in play"
            add(s_phys, syn + ".")
        elif residual >= SIG:
            add(s_phys, f"Synthesis: {lead} overshoot the metabolic state — an "
                "alkalinizing residual; verify the albumin, then consider "
                "unmeasured cations or lab error.")
        else:
            add(s_phys, f"Synthesis: {lead} account for the metabolic state — "
                "no hidden anion load.")

    # =====================================================================
    # SYNTHESIS — cross-track
    # =====================================================================
    if residual is not None and corrected is not None:
        # residual ≤ −2 counts as (at least borderline) agreement with an
        # elevated gap, so a rounding-edge case doesn't read as divergence
        stewart_anion = (residual <= -2) or (sig is not None and not albumin_assumed and sig >= 8)
        if stewart_anion and ag_elevated:
            add(s_syn, "Both tracks find unmeasured anions — the residual and "
                "the anion gap agree.")
        elif not stewart_anion and not ag_elevated:
            add(s_syn, "Both tracks agree: no significant unmeasured-anion load.")
        elif ag_elevated and not stewart_anion:
            add(s_syn, "Divergence: the anion gap is elevated but the Stewart "
                "residual is not — usually a water/chloride or albumin effect "
                "the plain gap misreads; trust the decomposition.")
        else:
            add(s_syn, "Divergence: the Stewart residual finds an anion load "
                "the plain gap misses — usually hypoalbuminemia masking the gap.")

    if chloride_eff is not None:
        if chloride_eff <= -SIG:
            add(s_syn,
                "Fluids: normal saline (SID 0) deepens a hyperchloremic "
                "acidosis — prefer a balanced fluid (LR/Plasma-Lyte, SID ≈ 28) "
                "if volume is needed.")
        elif chloride_eff >= SIG:
            add(s_syn,
                "Fluids: chloride-depletion alkalosis is chloride-responsive — "
                "normal saline ± KCl repletes it.")

    # --- what to order next, and why -------------------------------------
    needs = {"gas": None, "split": []}
    if not has_gas:
        if pH is not None and pco2 is None:
            needs["gas"] = "a pH implies a gas was run — add its pCO₂."
        elif pco2 is not None and pH is None:
            needs["gas"] = "add the pH from the same gas."
        elif hco3 is not None:
            if sbe is not None and sbe > 2:
                needs["gas"] = (
                    f"HCO₃⁻ {_fmt(hco3)} could be a metabolic alkalosis or renal "
                    "compensation for chronic hypercapnia — only a gas distinguishes them."
                )
            elif sbe is not None and sbe < -2:
                needs["gas"] = (
                    f"HCO₃⁻ {_fmt(hco3)} could be a metabolic acidosis or renal "
                    "compensation for chronic respiratory alkalosis — only a gas "
                    "distinguishes them."
                )
            elif processes:
                needs["gas"] = (
                    "forces are offsetting on a normal HCO₃⁻ — a gas pins down "
                    "the true base excess and the respiratory side."
                )
    if residual is not None and (residual <= -2.5 or residual >= SIG or ag_elevated):
        if albumin is None:
            needs["split"].append("albumin (assumed 4.2 — confirm it)")
        if lactate is None:
            needs["split"].append("lactate")
        if bhb is None and residual <= -2:
            needs["split"].append("β-hydroxybutyrate")
        if (osm is None and unmeasured_present
                and (bhb is not None and lactate is not None)
                and (keto_unexplained is None or keto_unexplained > 5)):
            needs["split"].append("measured osmolality (+BUN)")

    anything = any(v is not None for v in (pH, pco2, hco3, na, cl, k, albumin,
                                           lactate, bhb, glucose, bun,
                                           osm, ca, mg, phos))
    wants = []
    if needs["gas"]:
        if pH is not None and pco2 is None:
            wants.append("the pCO₂ from the same gas")
        elif pco2 is not None and pH is None:
            wants.append("the pH from the same gas")
        else:
            wants.append("a gas (pH + pCO₂)")
    if anything and (na is None or cl is None):
        missing_lytes = [n for n, v in (("Na⁺", na), ("Cl⁻", cl)) if v is None]
        wants.append(" and ".join(missing_lytes) + " to decompose the metabolic side")
    elif anything and hco3 is None and not has_gas:
        wants.append("the CO₂ (HCO₃⁻) to quantify the forces")
    if needs["split"]:
        wants.append(", ".join(needs["split"]) + " to split the residual")
    if sig is not None and not albumin_assumed:
        missing_ions = [n for n, v in (("ionized Ca²⁺", ca), ("Mg²⁺", mg),
                                       ("phosphate", phos)) if v is None]
        if missing_ions:
            wants.append(" / ".join(missing_ions) + " to firm up the strong ion gap")
    next_info = ("Would sharpen the read: " + "; ".join(wants) + ".") if wants else None

    # --- assemble the conclusion -----------------------------------------
    if has_gas:
        core = primary
        if primary == "normal acid-base status" and processes:
            core = "normal pH with offsetting metabolic forces"
            if borderline:
                processes.append(borderline)
    elif sbe is not None:
        if sbe < -2:
            core = "metabolic acidosis (no gas — pCO₂ assumed ≈40)"
        elif sbe > 2:
            core = "metabolic alkalosis (no gas — pCO₂ assumed ≈40)"
        elif processes:
            core = "normal net metabolic status with offsetting forces"
            if borderline:
                processes.append(borderline)
        else:
            core = "no metabolic derangement on these values (gas needed for the respiratory side)"
    elif processes:
        # Na/Cl entered without a bicarbonate: the forces are readable even
        # though the net metabolic state isn't.
        core = " + ".join(processes) + " (forces only — add HCO₃⁻/CO₂ to quantify)"
        processes = []
    else:
        core = None

    sections = [
        {"title": None, "steps": s_pre},
        {"title": "Traditional approach", "steps": s_trad},
        {"title": "Physicochemical approach (Stewart)", "steps": s_phys},
        {"title": "Synthesis", "steps": s_syn},
    ]

    if core is None:
        headline = "Not enough data for a deterministic read"
        if not any(sec["steps"] for sec in sections):
            add(s_pre,
                "Enter whatever is available — a BMP is enough to start; a "
                "gas, albumin, lactate and the rest sharpen it. A clinical "
                "context alone is interpreted by the AI layer.")
    else:
        headline = core[0].upper() + core[1:]
        extras_all = []
        for e in dict.fromkeys(resp_extras + processes):
            base = e.replace("superimposed ", "")
            if e not in core and base not in core:
                extras_all.append(e)
        if extras_all:
            headline += " — " + " + ".join(extras_all)

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
        ("iCa", ca, " mmol/L"), ("Mg", mg, " mg/dL"), ("phosphate", phos, " mg/dL"),
        ("lactate", lactate, " mmol/L"), ("BHB", bhb, " mmol/L"),
        ("glucose", glucose, " mg/dL"), ("BUN", bun, " mg/dL"),
        ("osmolality", osm, " mOsm/kg"),
    ]:
        if val is not None:
            parts.append(f"{label} {_fmt(val)}{unit}")
    if sbe is not None:
        parts.append(f"base excess {_sfmt(sbe)}" if has_gas
                     else f"HCO₃⁻ deviation {_sfmt(sbe)} (BE stand-in, pCO₂ assumed 40)")
    effect_bits = []
    if water_eff is not None:
        effect_bits.append(f"water {_sfmt(water_eff)}")
    if chloride_eff is not None:
        effect_bits.append(f"chloride {_sfmt(chloride_eff)}")
    if k_eff is not None:
        effect_bits.append(f"K {_sfmt(k_eff)}")
    if lactate_eff is not None:
        effect_bits.append(f"lactate {_sfmt(lactate_eff)}")
    if alb_eff is not None:
        effect_bits.append(f"albumin {_sfmt(alb_eff)}")
    if phos_eff is not None:
        effect_bits.append(f"phosphate {_sfmt(phos_eff)}")
    if residual is not None:
        effect_bits.append(f"residual {_sfmt(residual)}")
    if effect_bits:
        parts.append("Stewart effects (mEq/L): " + ", ".join(effect_bits))
    if sida is not None:
        parts.append(f"SIDa {_fmt(sida)}")
    if side is not None:
        parts.append(f"SIDe {_fmt(side)}")
    if sig is not None and not albumin_assumed:
        parts.append(f"strong ion gap {_fmt(sig)}")
    if vbg_applied:
        parts.append("gas VBG-adjusted to arterial estimates")
    if hco3_derived:
        parts.append("HCO₃⁻ derived from the gas")
    summary = ", ".join(parts)

    return {
        "headline": headline,
        "sections": sections,
        "differential": differential,
        "warnings": warnings,
        "summary": summary,
        "next": next_info,
        "needs": needs,
    }
