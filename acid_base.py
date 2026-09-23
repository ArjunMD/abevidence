"""Acid-base interpretation for the Tools page — three approaches, step by step.

Pure arithmetic — no AI, no network. Runs on whatever values are entered.

  BOSTON (physiological, bicarbonate-centred)
      pH → culprit by Henderson–Hasselbalch → compensation (Winter's etc.).
      Anion gap → albumin correction → delta ratio → ketones / osmolar gap.

  COPENHAGEN (base excess)
      Standard base excess (measured, or computed from the gas) → "40 + BE"
      compensation rules.

  STEWART (physicochemical) — pH is set by three independent variables: pCO₂,
  the strong ion difference (SID) and the weak acids (Atot). HCO₃⁻ and H⁺ are
  dependent. Done two ways, which describe the same buffer base from two
  reference points:
    Simplified — Fencl–Story partitioning, in BE units. Split the base excess
      into free-water, chloride, albumin and lactate effects; the remainder is
      unmeasured anions (Stewart's anion gap). Already a deviation from normal,
      so one value on one night reads directly.
    Full — SIDa, SIDe, SIG, in absolute units. There is no universal normal
      SIG; it is read against a healthy baseline run through these same
      equations (≈7 here), and carries ±2–3 of measurement noise.

  PUTTING IT TOGETHER — the story the partitioning tells, and whether the
  unmeasured-anion measures agree. Naming the clinical picture is left to the
  optional AI layer.

Albumin, phosphate, iCa²⁺, Mg²⁺ and K⁺ are assumed normal when blank (stated
wherever it matters); everything else is optional.

Each step is {"text", "calc", "note", "level"}: text carries the finding and
its meaning, calc the formula with the values plugged in (shown; one formula
per line), note an optional mechanism/caveat (shown on hover), level 0 for a
step and 1 for a correction beneath it.
"""

NORMAL_PH = 7.40
NORMAL_NA = 140.0
NORMAL_CL = 102.0      # at a sodium of 140
NORMAL_ALB = 4.2       # g/dL
NORMAL_PHOS = 3.7      # mg/dL
NORMAL_K = 4.0
NORMAL_ICA = 1.2       # mmol/L
NORMAL_MG = 2.0        # mg/dL
NORMAL_HCO3 = 24.0
NORMAL_AG = 12.0
LACTATE_BASE = 1.0     # typical baseline lactate (mmol/L)
LACTATE_UPPER = 2.0    # upper normal lactate (mmol/L)
BHB_UPPER = 0.6        # upper normal β-hydroxybutyrate (mmol/L)

MG_TO_MEQ = 0.823      # Mg mg/dL → mEq/L
PHOS_EFFECT = 0.586    # mEq/L of acid per mg/dL of phosphate above normal (pH 7.4)
UREMIC_BUN = 60.0      # BUN (mg/dL) from which uremic anions are a named suspect
PHOS_TO_MMOL = 0.323   # phosphate mg/dL → mmol/L

# An individual effect below this magnitude (mEq/L) is minor; above MARKED it
# is a major driver worth leading with. MODEST is the floor for naming a
# contributor in the story line.
SIG = 3.0
BORDER = 4.0           # effects between SIG and this are called borderline
MARKED = 6.0
MODEST = 1.0

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
    "alk_cl_resp": "High-SID alkalosis, chloride-responsive (urine Cl⁻ <20): "
                   "vomiting/NG suction, prior diuretic use, post-hypercapnia.",
    "alk_cl_resist": "High-SID alkalosis, chloride-resistant (urine Cl⁻ >20): "
                     "mineralocorticoid excess (hyperaldosteronism, Cushing's), "
                     "ongoing diuretics, severe hypokalemia, Bartter/Gitelman.",
    "alk_load": "Alkali load: milk-alkali, bicarbonate, citrate (transfusion, "
                "CRRT), acetate — especially with reduced GFR.",
    "hagma": "Unmeasured anions (GOLDMARK): glycols, oxoproline, L-/D-lactate, "
             "methanol, aspirin, renal failure, ketoacidosis.",
    "lactic": "Lactic acidosis: type A (sepsis, hypoperfusion, ischemia) or "
              "type B (metformin, ethanol metabolism, liver failure, malignancy, "
              "thiamine deficiency).",
    "keto": "Ketoacidosis: diabetic, alcoholic, or starvation.",
    "unexplained": "Unexplained anions: toxic alcohols (methanol/ethylene "
                   "glycol — check osmolar gap), salicylates, uremia, "
                   "5-oxoproline.",
    "osm": "Elevated osmolar gap: ethanol; ketoacidosis or lactic acidosis "
           "themselves (often 10–20); methanol, ethylene glycol, isopropanol, "
           "mannitol, propylene glycol.",
    "resp_ac": "Respiratory acidosis: sedation/opioids, COPD/asthma, "
               "neuromuscular weakness, chest-wall/obesity hypoventilation.",
    "resp_alk": "Respiratory alkalosis: anxiety/pain, hypoxia, PE, sepsis, "
                "salicylates, alcohol withdrawal, pregnancy, hepatic failure.",
}


def _fmt(x: float) -> str:
    """Whole numbers without a trailing '.0', one decimal otherwise; a true
    minus sign for negatives."""
    s = f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"
    return "0" if s in ("-0", "-0.0") else s.replace("-", "−")


def _sfmt(x: float) -> str:
    """Signed format: '+3', '−4.5', '0'."""
    if abs(x) < 0.05:
        return "0"
    return ("+" if x > 0 else "−") + _fmt(abs(x))


def _ph(x: float) -> str:
    """pH always to two decimals."""
    return f"{x:.2f}"


def _paren_neg(x: float) -> str:
    """A number safe to drop after a '+' in a formula: negatives bracketed."""
    return f"({_fmt(x)})" if x < -0.05 else _fmt(x)


def _sum_terms(vals: list[float]) -> str:
    """'−0.6 − 13.7 + 5.5' — a running sum written out."""
    out = ""
    for i, v in enumerate(vals):
        if i == 0:
            out = _fmt(v)
        else:
            out += (" − " if v < 0 else " + ") + _fmt(abs(v))
    return out


def _direction(eff: float, acid: str, alk: str) -> str:
    """Label an effect by the same ±SIG cut everywhere."""
    def grade(x):
        return (", major" if abs(x) >= MARKED else
                " (borderline)" if abs(x) < BORDER else "")
    if eff <= -SIG:
        return f"acidifying — {acid}" + grade(eff)
    if eff >= SIG:
        return f"alkalinizing — {alk}" + grade(eff)
    return "minor"


def _standard_base_excess(pH: float, hco3: float) -> float:
    """Standard base excess (mEq/L), Van Slyke approximation — what the
    analyzer computes from pH and HCO₃⁻. Negative is a base deficit."""
    return 0.9287 * (hco3 - 24.4 + 14.83 * (pH - 7.4))


def _alb_charge(alb_gdl: float, pH: float) -> float:
    """Albumin anionic charge (mEq/L), Figge–Fencl: albumin in g/L."""
    return 10.0 * alb_gdl * (0.123 * pH - 0.631)


def _phos_charge(phos_mgdl: float, pH: float) -> float:
    """Phosphate anionic charge (mEq/L), Figge–Fencl: phosphate in mmol/L."""
    return PHOS_TO_MMOL * phos_mgdl * (0.309 * pH - 0.469)


def _sida(na, k, ica, mg, cl, lactate) -> float:
    return na + k + 2.0 * ica + MG_TO_MEQ * mg - cl - lactate


# A healthy person run through the same full-Stewart equations. There is no
# universal normal SIG — this is the reference point this tool reads against.
BASE_SIDA = _sida(NORMAL_NA, NORMAL_K, NORMAL_ICA, NORMAL_MG, NORMAL_CL, LACTATE_BASE)
BASE_SIDE = (NORMAL_HCO3 + _alb_charge(NORMAL_ALB, NORMAL_PH)
             + _phos_charge(NORMAL_PHOS, NORMAL_PH))
BASE_SIG = BASE_SIDA - BASE_SIDE
BASE_SID = NORMAL_NA + NORMAL_K - NORMAL_CL   # Na + K − Cl, first-order


def interpret(pH=None, pco2=None, hco3=None, na=None, cl=None, albumin=None,
              lactate=None, bhb=None, glucose=None, bun=None,
              osm=None, k=None, vbg=False, ca=None, mg=None, phos=None,
              be=None, urine_cl=None) -> dict:
    """Run every approach on whatever values are supplied (all optional).
    vbg=True converts gas values to arterial estimates (pH +0.03, pCO₂ −5).
    be is the analyzer's base excess; computed from the gas when absent.
    urine_cl separates chloride-responsive from chloride-resistant alkalosis.
    Returns {headline, sections, differential, warnings, summary, next,
    needs}: sections is a list of {"title": str-or-None, "steps": [...]},
    each step {"text", "calc", "note", "level"}; summary primes the optional
    AI layer; next says what would sharpen the read; needs = {"gas":
    reason-or-None, "split": [lab, ...]}."""
    warnings: list[str] = []
    resp_extras: list[str] = []   # superimposed disorders found on the gas
    processes: list[str] = []     # named metabolic components (Stewart side)
    diff_keys: list[str] = []     # which differentials to show

    # section step lists, assembled into display order at the end
    s_pre: list[dict] = []      # untitled preamble (VBG note, derived HCO₃⁻)
    s_bos: list[dict] = []      # Boston
    s_cop: list[dict] = []      # Copenhagen
    s_fs: list[dict] = []       # Stewart, simplified (Fencl–Story)
    s_full: list[dict] = []     # Stewart, full (SIDa/SIDe/SIG)
    s_syn: list[dict] = []      # putting it together

    def add(sec: list, text: str, calc: str = None, note: str = None,
            level: int = 0) -> None:
        sec.append({"text": text, "calc": calc, "note": note, "level": level})

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
    if be is not None and abs(be) > 30:
        warnings.append("Base excess beyond ±30 — recheck the value.")

    # --- assumed-normal stand-ins (stated wherever they matter) ----------
    albumin_assumed = albumin is None
    alb_used = NORMAL_ALB if albumin_assumed else albumin
    phos_used = NORMAL_PHOS if phos is None else phos
    ph_used = pH if pH is not None else NORMAL_PH
    k_used = NORMAL_K if k is None else k
    ca_used = NORMAL_ICA if ca is None else ca
    mg_used = NORMAL_MG if mg is None else mg
    lac_used = 0.0 if lactate is None else lactate

    # --- classical gap ----------------------------------------------------
    ag = None
    corrected = None
    ag_elevated = False
    if na is not None and cl is not None and hco3 is not None:
        ag = na - cl - hco3
        corrected = ag + 2.5 * (NORMAL_ALB - alb_used)
        ag_elevated = corrected > NORMAL_AG

    # --- base excess (Copenhagen; the number Fencl–Story partitions) -----
    be_source = None   # "measured" | "gas" | "hco3"
    sbe = None
    if be is not None:
        sbe, be_source = be, "measured"
    elif has_gas:
        sbe, be_source = _standard_base_excess(pH, hco3), "gas"
    elif hco3 is not None:
        sbe, be_source = hco3 - NORMAL_HCO3, "hco3"
    dev = hco3 - NORMAL_HCO3 if hco3 is not None else None
    be_name = "HCO₃⁻ deviation" if be_source == "hco3" else "BE"

    # --- Fencl–Story effects ---------------------------------------------
    water_eff = chloride_eff = alb_eff = lactate_eff = None
    cl_corr = None
    if na is not None and na > 0:
        water_eff = 0.3 * (na - NORMAL_NA)
        if cl is not None:
            cl_corr = cl * NORMAL_NA / na
            chloride_eff = NORMAL_CL - cl_corr
        alb_eff = 2.5 * (NORMAL_ALB - alb_used)
    if lactate is not None:
        lactate_eff = LACTATE_BASE - lactate

    effects = [e for e in (water_eff, chloride_eff,
                           None if albumin_assumed else alb_eff, lactate_eff)
               if e is not None]
    effects_sum = sum(effects) if effects else None
    residual = None
    if sbe is not None and water_eff is not None and chloride_eff is not None:
        residual = sbe - effects_sum

    if urine_cl is None:
        alk_keys = ["alk_cl_resp", "alk_cl_resist"]
    elif urine_cl < 20:
        alk_keys = ["alk_cl_resp"]
    else:
        alk_keys = ["alk_cl_resist"]

    lac_elevated = lactate is not None and lactate > LACTATE_UPPER
    keto_elevated = bhb is not None and bhb >= BHB_UPPER
    unmeasured_present = residual is not None and residual <= -SIG
    borderline = None   # sub-threshold residual, named when it offsets a force

    keto_explained = None     # β-hydroxybutyrate share alone
    keto_total = None         # + acetoacetate, which BHB assays don't measure
    keto_unexplained = None
    if unmeasured_present and bhb is not None:
        keto_explained = max(0.0, bhb - BHB_UPPER)
        keto_total = keto_explained * 4.0 / 3.0   # BHB:acetoacetate ≈ 3:1 (DKA)
        keto_total_aka = keto_explained * 8.0 / 7.0   # ≈ 7:1 in alcoholic ketoacidosis

    # Phosphate sits outside the four-term partition, so retained phosphate
    # lands in the remainder; itemise it the way ketones are.
    phos_share = PHOS_EFFECT * (phos - NORMAL_PHOS) if phos is not None and phos > NORMAL_PHOS else 0.0
    if phos_share < 1:
        phos_share = 0.0   # below display precision — don't subtract what isn't shown
    uremic = bun is not None and bun >= UREMIC_BUN
    if unmeasured_present and (bhb is not None or phos_share >= 1):
        keto_unexplained = -residual - (keto_total or 0.0) - phos_share

    # --- full Stewart ------------------------------------------------------
    sid = sida = side = sig = sig_excess = None
    alb_ch = _alb_charge(alb_used, ph_used)
    phos_ch = _phos_charge(phos_used, ph_used)
    if na is not None and cl is not None:
        sid = na + k_used - cl
        sida = _sida(na, k_used, ca_used, mg_used, cl, lac_used)
    if hco3 is not None:
        side = hco3 + alb_ch + phos_ch
    if sida is not None and side is not None:
        sig = sida - side
        sig_excess = sig - BASE_SIG

    og = None
    if osm is not None and na is not None and glucose is not None and bun is not None:
        og = osm - (2 * na + glucose / 18.0 + bun / 2.8)

    # =====================================================================
    # Preamble — gas conversions, shared by every approach
    # =====================================================================
    if vbg_applied:
        shown = []
        if pH is not None:
            shown.append(f"pH → {_ph(pH)}")
        if pco2 is not None:
            shown.append(f"pCO₂ → {_fmt(pco2)}")
        add(s_pre,
            "VBG converted to arterial estimates: " + ", ".join(shown) + ".",
            "pH + 0.03; pCO₂ − 5",
            "Approximate — agreement degrades in shock and low-flow states.")
    if hco3_derived:
        add(s_pre,
            f"HCO₃⁻ derived from the gas = {_fmt(hco3)} mmol/L.",
            f"0.03 × pCO₂ × 10^(pH − 6.1) = 0.03 × {_fmt(pco2)} × "
            f"10^({_ph(pH)} − 6.1) = {_fmt(hco3)}",
            "Henderson–Hasselbalch — the same derivation the analyzer uses.")

    # =====================================================================
    # BOSTON — bicarbonate-centred
    # =====================================================================

    # --- step: pH → culprit → compensation --------------------------------
    primary = None
    comp_note = None
    if pH is not None:
        status = ("acidemia" if pH < 7.35 else
                  "alkalemia" if pH > 7.45 else "normal")
        add(s_bos, f"pH {_ph(pH)} → {status} (normal 7.35–7.45).")

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

        def _band(x, lo, hi):
            return "low" if x < lo else "high" if x > hi else "normal"

        add(s_bos,
            f"pCO₂ {_fmt(pco2)} ({_band(pco2, 35, 45)}), HCO₃⁻ {_fmt(hco3)} "
            f"({_band(hco3, 22, 26)}) → primary disorder: {primary}.",
            None,
            "pH = 6.1 + log(HCO₃⁻ / (0.03×pCO₂)). The pH names the side; "
            "whichever of pCO₂ / HCO₃⁻ moved in that direction is the culprit.",
            level=1)

        met_acid_part = (primary in ("metabolic acidosis",
                                     "combined metabolic and respiratory acidosis")
                         or primary.startswith("mixed: metabolic acidosis"))
        met_alk_part = (primary == "metabolic alkalosis"
                        or primary.startswith("mixed: metabolic alkalosis"))
        pure_met = primary in ("metabolic acidosis", "metabolic alkalosis")
        if met_acid_part or met_alk_part:
            if met_acid_part:
                expected = 1.5 * hco3 + 8  # Winter's formula
                calc = (f"1.5 × HCO₃⁻ + 8 = 1.5 × {_fmt(hco3)} + 8 = "
                        f"{_fmt(expected)} (±2)")
                note = ("Winter's formula. Bedside shortcuts: pCO₂ ≈ last two "
                        "digits of the pH; pCO₂ ≈ HCO₃⁻ + 15.")
                name = "Winter's"
            else:
                expected = 0.7 * hco3 + 21  # expected pCO2 for metabolic alkalosis
                calc = (f"0.7 × HCO₃⁻ + 21 = 0.7 × {_fmt(hco3)} + 21 = "
                        f"{_fmt(expected)} (±2)")
                note = "The pCO₂ appropriate respiratory compensation should reach."
                name = "expected pCO₂"
            text = (f"Compensation ({name}): expected pCO₂ {_fmt(expected)}, "
                    f"actual {_fmt(pco2)}")
            # beyond ±2 is outside the range; beyond ±4 is clearly outside
            over = pco2 - round(expected, 1)
            if over > 4:
                ac = ("respiratory acidosis" if pco2 > 45 else
                      "relative respiratory acidosis (compensation falling short)")
                if pure_met:
                    text += f" → pCO₂ too high: superimposed {ac}."
                    resp_extras.append(f"superimposed {ac}")
                else:
                    text += " → pCO₂ above expected: a respiratory acidosis is present."
                diff_keys.append("resp_ac")
            elif over > 2:
                text += (f" → {_fmt(over - 2)} above the range: borderline — "
                         "respiratory compensation may be falling short.")
                if pure_met:
                    comp_note = "borderline — respiratory compensation may be falling short"
            elif over < -4:
                alk_r = ("respiratory alkalosis" if pco2 < 35 else
                         "relative respiratory alkalosis")
                if pure_met:
                    text += f" → pCO₂ too low: superimposed {alk_r}."
                    resp_extras.append(f"superimposed {alk_r}")
                else:
                    text += " → pCO₂ below expected: a respiratory alkalosis is present."
                diff_keys.append("resp_alk")
            elif over < -2:
                text += (f" → {_fmt(-over - 2)} below the range: borderline — "
                         "possibly a mild respiratory alkalosis.")
                if pure_met:
                    comp_note = "borderline — possibly a mild superimposed respiratory alkalosis"
            else:
                text += " → appropriate respiratory compensation."
                comp_note = "appropriate respiratory compensation"
            add(s_bos, text, calc, note, level=1)

            # A normal-pH mixed picture can also be one compensated respiratory
            # disorder; say what separates the two readings.
            if primary.startswith("mixed: metabolic acidosis with respiratory alkalosis"):
                chronic = NORMAL_HCO3 - 0.4 * (40 - pco2)
                if hco3 < chronic - 2:
                    t = (f"HCO₃⁻ {_fmt(hco3)} is below what a chronic respiratory "
                         f"alkalosis alone would give (expected {_fmt(chronic)}) — "
                         "a true metabolic acidosis on top.")
                    add(s_bos, t,
                        f"24 − 0.4 × (40 − pCO₂) = 24 − 0.4 × (40 − {_fmt(pco2)}) = "
                        f"{_fmt(chronic)}", level=1)
                    t = None
                else:
                    t = (f"HCO₃⁻ {_fmt(hco3)} alone also fits a chronic respiratory "
                         f"alkalosis (expected {_fmt(chronic)}) — that's why the pH is "
                         "normal")
                if t is None:
                    pass
                elif corrected is not None and corrected > 20:
                    t += ("; the " + ("anion gap" if albumin_assumed
                                      else "corrected anion gap")
                          + f" of {_fmt(corrected)} (step 2) is what proves a "
                          "primary metabolic acidosis.")
                else:
                    t += ("; without a clearly elevated anion gap this may be a "
                          "compensated chronic respiratory alkalosis, not two disorders.")
                if t is not None:
                    add(s_bos, t,
                        f"24 − 0.4 × (40 − pCO₂) = 24 − 0.4 × (40 − {_fmt(pco2)}) = "
                        f"{_fmt(chronic)}", level=1)
            elif primary.startswith("mixed: metabolic alkalosis with respiratory acidosis"):
                chronic = NORMAL_HCO3 + 0.35 * (pco2 - 40)
                add(s_bos,
                    (f"HCO₃⁻ {_fmt(hco3)} is above what a chronic respiratory "
                     f"acidosis alone would give (expected {_fmt(chronic)}) — a "
                     "true metabolic alkalosis on top."
                     if hco3 > chronic + 2 else
                     f"HCO₃⁻ {_fmt(hco3)} alone also fits a chronic respiratory "
                     f"acidosis (expected {_fmt(chronic)}); the chloride effect "
                     "below and the history separate a true metabolic alkalosis "
                     "from compensation."),
                    f"24 + 0.35 × (pCO₂ − 40) = 24 + 0.35 × ({_fmt(pco2)} − 40) = "
                    f"{_fmt(chronic)}", level=1)

        elif primary in ("respiratory acidosis", "respiratory alkalosis"):
            d = pco2 - 40
            if primary == "respiratory acidosis":
                acute = NORMAL_HCO3 + 0.1 * d     # HCO3 rises 1 per 10 mmHg
                chronic = NORMAL_HCO3 + 0.35 * d  # rises 3.5 per 10 mmHg
                calc = (f"acute: 24 + 0.1 × (pCO₂ − 40) = {_fmt(acute)}\n"
                        f"chronic: 24 + 0.35 × (pCO₂ − 40) = {_fmt(chronic)}")
                note = ("ΔpH shortcut: pH falls ≈0.08 per 10 mmHg pCO₂ acutely, "
                        "≈0.03 chronically.")
            else:
                acute = NORMAL_HCO3 + 0.2 * d     # HCO3 falls 2 per 10 mmHg
                chronic = NORMAL_HCO3 + 0.4 * d   # falls 4 per 10 mmHg
                calc = (f"acute: 24 − 0.2 × (40 − pCO₂) = {_fmt(acute)}\n"
                        f"chronic: 24 − 0.4 × (40 − pCO₂) = {_fmt(chronic)}")
                note = ("ΔpH shortcut: pH rises ≈0.08 per 10 mmHg pCO₂ drop "
                        "acutely, ≈0.03 chronically.")
            text = (f"Compensation: expected HCO₃⁻ acute {_fmt(acute)}, "
                    f"chronic {_fmt(chronic)}, actual {_fmt(hco3)}")
            straddle = abs(hco3 - acute) <= 2 and abs(hco3 - chronic) <= 2
            straddle_text = (" → between the acute and chronic predictions: acute "
                             "vs chronic hard to separate here")
            # a metabolic force pushing HCO₃⁻ up blurs the call further
            if straddle and alb_eff is not None and not albumin_assumed and alb_eff >= SIG:
                straddle_text += (f"; the hypoalbuminemic alkalosis ({_sfmt(alb_eff)}) "
                                  "also nudges HCO₃⁻ up, which can make "
                                  + ("a chronic disorder look acute"
                                     if primary == "respiratory alkalosis"
                                     else "an acute disorder look chronic"))
            if primary == "respiratory acidosis":
                if hco3 < acute - 2:
                    text += " → below acute expected: superimposed metabolic acidosis."
                    resp_extras.append("superimposed metabolic acidosis")
                elif hco3 > chronic + 2:
                    text += " → above chronic expected: superimposed metabolic alkalosis."
                    resp_extras.append("superimposed metabolic alkalosis")
                    diff_keys.extend(alk_keys)
                elif straddle:
                    text += straddle_text + "."
                    comp_note = "acute vs chronic hard to separate here"
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
                    diff_keys.extend(alk_keys)
                elif hco3 < chronic - 2:
                    text += " → below chronic expected: superimposed metabolic acidosis."
                    resp_extras.append("superimposed metabolic acidosis")
                elif straddle:
                    text += straddle_text + "."
                    comp_note = "acute vs chronic hard to separate here"
                elif hco3 >= acute - 2:
                    text += " → consistent with acute respiratory alkalosis."
                    comp_note = "consistent with acute"
                else:
                    text += " → consistent with chronic (or partly compensated) respiratory alkalosis."
                    comp_note = "consistent with chronic (or partly compensated)"
                diff_keys.append("resp_alk")
            add(s_bos, text, calc, note, level=1)
    elif pH is not None:
        add(s_bos, "pCO₂ needed to name the primary disorder and check "
                   "compensation.", level=1)
    elif hco3 is not None:
        tag = ("low" if dev < -2 else "high" if dev > 2 else "normal")
        add(s_bos, f"HCO₃⁻ {_fmt(hco3)} → {tag} (normal 22–26) — a gas is "
                   "needed to separate a primary disorder from compensation.")
    elif pco2 is not None:
        add(s_bos, f"pCO₂ {_fmt(pco2)} — pH needed to interpret it.")

    # In appropriately compensated respiratory disorders the kidney moves
    # chloride (Stewart's compensation lever); that chloride shift is not a
    # separate metabolic disorder.
    chloride_is_comp = (
        chloride_eff is not None and comp_note is not None and not resp_extras
        and ((primary == "respiratory acidosis" and chloride_eff >= SIG)
             or (primary == "respiratory alkalosis" and chloride_eff <= -SIG)))

    # --- step: anion gap → albumin → delta ratio → workup ----------------
    if ag is not None:
        tag = ("elevated: unmeasured anions" if ag > 20 else
               "mildly elevated: possible unmeasured anions" if ag > NORMAL_AG else
               "normal")
        add(s_bos, f"Anion gap {_fmt(ag)} → {tag} (normal ≈ 12).",
            f"Na − Cl − HCO₃⁻ = {_fmt(na)} − {_fmt(cl)} − {_fmt(hco3)} = {_fmt(ag)}",
            "Mild elevations (≈12–20) can be baseline/analyzer variation, "
            "combined measurement error of three analytes, alkalemia, "
            "hyperphosphatemia, or low K/Ca/Mg — a gap >20 cannot.")
        if albumin_assumed:
            add(s_bos, "Albumin not entered — if it is low, the true gap is "
                "higher than this.", level=1)
        else:
            if corrected > 20:
                ctag = "unmeasured anions"
            elif ag_elevated:
                ctag = "mildly elevated"
            else:
                ctag = "normal"
            unmask = (" — low albumin was hiding part of the gap"
                      if corrected - ag >= 2 and corrected > NORMAL_AG else "")
            add(s_bos, f"Albumin-corrected gap {_fmt(corrected)} → {ctag}{unmask}.",
                f"AG + 2.5 × (4.2 − albumin) = {_fmt(ag)} + 2.5 × (4.2 − "
                f"{_fmt(alb_used)}) = {_fmt(corrected)}",
                "Albumin is the main unmeasured anion in the normal gap; each "
                "1 g/dL drop lowers the gap by ≈2.5. Reference albumin here is "
                "4.2 g/dL, the same as the Stewart albumin effect; many "
                "references use 4.0 or 4.4 (4.0 would give "
                f"{_fmt(ag + 2.5 * (4.0 - alb_used))}).", level=1)

        if ag_elevated:
            denom = NORMAL_HCO3 - hco3
            if denom > 0.5:
                dr = (corrected - NORMAL_AG) / denom
                read = ("mostly a non-gap acidosis" if dr < 0.4 else
                        "a gap acidosis plus a non-gap component (chloride or "
                        "dilutional)" if dr < 0.8 else
                        "consistent with a gap acidosis — at most a small non-gap "
                        "component" if dr < 1 else
                        "a pure high-gap acidosis" if dr <= 2 else
                        "a concurrent metabolic alkalosis holding the HCO₃⁻ up")
                why = []
                if denom < 4:
                    why.append(f"HCO₃⁻ fell only {_fmt(denom)}, so small changes "
                               "swing the ratio")
                if primary == "respiratory alkalosis":
                    why.append("part of the HCO₃⁻ fall is compensation for the "
                               "respiratory alkalosis")
                elif primary == "respiratory acidosis":
                    why.append("the HCO₃⁻ is shifted by compensation for the "
                               "respiratory acidosis")
                dtext = (f"Delta ratio {dr:.1f} — unreliable here ("
                         + "; ".join(why) + "); the Stewart lines below explain "
                         "the HCO₃⁻ better."
                         if why else f"Delta ratio {dr:.1f} → {read}.")
                add(s_bos, dtext,
                    f"(gap − 12) / (24 − HCO₃⁻) = ({_fmt(corrected)} − 12) / "
                    f"(24 − {_fmt(hco3)}) = {dr:.1f}",
                    "How much the gap rose versus how far the HCO₃⁻ fell. <0.4: "
                    "mostly non-gap; 0.4–0.8: gap plus non-gap; 0.8–2: gap acid "
                    "alone; >2: something is holding the HCO₃⁻ up. Assumes a normal gap of 12; many "
                    "modern analyzers run 8–10 (with 10 this would be "
                    f"{(corrected - 10) / denom:.1f}).", level=1)

    wk = 1 if ag is not None else 0   # workup nests under the gap when it exists
    if bhb is not None:
        if bhb >= 3:
            kmsg = f"β-hydroxybutyrate {_fmt(bhb)} → ketoacidosis range (≥3)"
        elif bhb >= BHB_UPPER:
            kmsg = f"β-hydroxybutyrate {_fmt(bhb)} → ketosis (mildly elevated)"
        else:
            kmsg = f"β-hydroxybutyrate {_fmt(bhb)} → normal (<0.6)"
        if keto_elevated and glucose is not None:
            if glucose > 250:
                kmsg += f"; with glucose {_fmt(glucose)} → consistent with DKA"
            elif glucose < 200:
                kmsg += (f"; with glucose {_fmt(glucose)} → euglycemic ketoacidosis "
                         "(SGLT2 inhibitor, starvation, alcohol, pregnancy)")
        add(s_bos, kmsg + ".", level=wk)
        if keto_elevated:
            diff_keys.append("keto")

    if bhb is None and glucose is not None and glucose > 250:
        add(s_bos, f"Glucose {_fmt(glucose)} elevated — check β-hydroxybutyrate "
            "to assess for DKA.", level=wk)

    if osm is not None:
        if og is not None:
            calc = (f"measured − (2×Na + glucose/18 + BUN/2.8) = {_fmt(osm)} − "
                    f"(2×{_fmt(na)} + {_fmt(glucose)}/18 + {_fmt(bun)}/2.8) = {_fmt(og)}")
            if og > 10:
                t = f"Osmolar gap {_fmt(og)} → elevated (>10)"
                if (keto_elevated or lac_elevated) and og < 25:
                    t += ("; ketoacidosis and lactic acidosis raise it on their "
                          "own (often 10–20)")
                elif og >= 25:
                    t += "; too large for ketoacidosis or lactate alone"
                t += (f"; an ethanol level of ≈{og * 3.7:.0f} mg/dL would explain "
                      "it — check ethanol"
                      + (" (though ethanol can't explain an anion gap)"
                         if ag_elevated or unmeasured_present else ""))
                t += ("; ≥20, toxic alcohols (methanol, ethylene glycol) are a real "
                      "concern — send levels." if og >= 20 else
                      "; toxic alcohols possible but not established.")
                add(s_bos, t, calc + f"\nethanol equivalent = gap × 3.7 = "
                    f"{og * 3.7:.0f} mg/dL",
                    "Osmolar and anion gaps move in opposite directions over a "
                    "toxic-alcohol course: early, the parent alcohol gives a high "
                    "osmolar gap and little anion gap; late, the acid metabolites "
                    "give a high anion gap as the osmolar gap falls. A normal "
                    "osmolar gap later does not exclude poisoning.", level=wk)
                diff_keys.append("osm")
            else:
                add(s_bos, f"Osmolar gap {_fmt(og)} → not elevated (≤10): toxic "
                    "alcohols less likely.", calc, level=wk)
        else:
            add(s_bos, "Enter Na⁺, glucose, and BUN to compute the osmolar gap.",
                level=wk)

    # =====================================================================
    # COPENHAGEN — base excess
    # =====================================================================
    if sbe is not None:
        mtag = ("metabolic acidosis" if sbe < -2 else
                "metabolic alkalosis" if sbe > 2 else
                "no net metabolic change")
        if primary in ("respiratory acidosis", "respiratory alkalosis") and abs(sbe) > 2:
            mtag = ("raised" if sbe > 0 else "lowered") + " — see whether it is compensation"
        if be_source == "measured":
            add(s_cop, f"Base excess {_sfmt(sbe)} (analyzer) → {mtag} (normal ±2).",
                None,
                "Standard base excess — the metabolic component with the "
                "respiratory part stripped out. One number for the whole "
                "metabolic side.")
        elif be_source == "gas":
            add(s_cop, f"Base excess {_sfmt(sbe)} → {mtag} (normal ±2).",
                f"0.9287 × (HCO₃⁻ − 24.4 + 14.83 × (pH − 7.4)) = 0.9287 × "
                f"({_fmt(hco3)} − 24.4 + 14.83 × ({_ph(pH)} − 7.4)) = {_fmt(sbe)}",
                "Van Slyke standard base excess, as the analyzer computes it. "
                "Enter the analyzer's value to use it directly.")
        else:
            add(s_cop, f"No gas — HCO₃⁻ deviation {_sfmt(sbe)} stands in for "
                f"base excess → {mtag}.",
                f"HCO₃⁻ − 24 = {_fmt(hco3)} − 24 = {_fmt(sbe)}",
                "True base excess needs pH and pCO₂; this assumes pCO₂ ≈ 40.")

        # "40 + BE" compensation rules (display only — Boston classifies).
        # Mixed and combined disorders take the rule for whichever way the BE
        # points, which is how a hidden respiratory component shows itself.
        met_rule = None
        if has_gas and primary not in ("respiratory acidosis", "respiratory alkalosis",
                                       "normal acid-base status"):
            if primary == "metabolic acidosis" or (primary != "metabolic alkalosis"
                                                   and sbe < -2):
                met_rule = "acid"
            elif primary == "metabolic alkalosis" or sbe > 2:
                met_rule = "alk"
        if met_rule:
            mixed = primary not in ("metabolic acidosis", "metabolic alkalosis")
            if met_rule == "acid":
                exp = 40 + sbe
                calc = f"40 + BE = 40 + {_paren_neg(sbe)} = {_fmt(exp)} (±2)"
            else:
                exp = 40 + 0.6 * sbe
                calc = f"40 + 0.6 × BE = 40 + 0.6 × {_fmt(sbe)} = {_fmt(exp)} (±2)"
            d = pco2 - round(exp, 1)
            if abs(d) <= 2:
                verdict = ("appropriate — no separate respiratory disorder" if mixed
                           else "appropriate" + (" (at the edge of the range)"
                                                 if abs(d) > 1.5 else ""))
            elif d > 4:
                verdict = ("pCO₂ above expected — a respiratory acidosis is present"
                           if mixed else "pCO₂ too high — respiratory acidosis too")
            elif d > 2:
                verdict = "borderline — compensation may be falling short"
            elif d < -4:
                verdict = ("pCO₂ below expected — a respiratory alkalosis is present"
                           if mixed else "pCO₂ too low — respiratory alkalosis too")
            else:
                verdict = "borderline — possibly a mild respiratory alkalosis"
            add(s_cop, f"Compensation: expected pCO₂ {_fmt(exp)}, actual "
                f"{_fmt(pco2)} → {verdict}.", calc, level=1)
        elif has_gas and primary in ("respiratory acidosis", "respiratory alkalosis"):
            chronic_be = 0.4 * (pco2 - 40)
            lo, hi = sorted((0.0, chronic_be))
            if abs(sbe) <= 2:
                verdict = "acute (no renal compensation yet)"
            elif abs(sbe - chronic_be) <= 2:
                verdict = "chronic (renal compensation complete)"
            elif lo < sbe < hi:
                verdict = "partly compensated"
            elif (sbe > hi) == (chronic_be > 0):
                verdict = ("beyond chronic compensation — superimposed "
                           + ("metabolic alkalosis" if chronic_be > 0
                              else "metabolic acidosis"))
            else:
                verdict = ("wrong direction — superimposed "
                           + ("metabolic acidosis" if chronic_be > 0
                              else "metabolic alkalosis"))
            add(s_cop, f"Compensation: expected BE acute 0, chronic "
                f"{_sfmt(chronic_be)}, actual {_sfmt(sbe)} → {verdict}.",
                f"chronic: 0.4 × (pCO₂ − 40) = 0.4 × ({_fmt(pco2)} − 40) = "
                f"{_fmt(chronic_be)}", level=1)

    # =====================================================================
    # STEWART, SIMPLIFIED — Fencl–Story base-excess partitioning
    # =====================================================================
    if water_eff is not None:
        add(s_fs,
            f"Sodium / free-water effect {_sfmt(water_eff)} → "
            + _direction(water_eff, "dilution (free-water excess)",
                         "concentration (free-water deficit)") + ".",
            f"0.3 × (Na − 140) = 0.3 × ({_fmt(na)} − 140) = {_fmt(water_eff)}",
            "Free water dilutes the SID (acidifying); a water deficit "
            "concentrates it (alkalinizing).")
        if water_eff <= -SIG:
            processes.append("dilutional (free-water) component")
            diff_keys.append("water_ac")
        elif water_eff >= SIG:
            processes.append("contraction (free-water deficit) alkalosis")
            diff_keys.append("water_alk")

        # Hyperglycemia dilutes the sodium by osmotic water shift; above a
        # material correction (~2 mEq/L) the measured Na misstates the true
        # water balance. Glucose not entered → assumed normal, no correction.
        if glucose is not None:
            na_shift = 1.6 * (glucose - 100.0) / 100.0
            if na_shift >= 2:
                calc = (f"Na + 1.6 × (glucose − 100)/100 = {_fmt(na)} + 1.6 × "
                        f"({_fmt(glucose)} − 100)/100 = {_fmt(na + na_shift)}")
                if water_eff <= -2:
                    add(s_fs,
                        f"Glucose-corrected Na {_fmt(na + na_shift)} → part of the "
                        "low Na is water pulled in by hyperglycemia; that share of "
                        "the dilution resolves as glucose falls.", calc, level=1)
                else:
                    add(s_fs,
                        f"Glucose-corrected Na {_fmt(na + na_shift)} → measured Na "
                        "understates tonicity; hyperglycemia may be masking a "
                        "free-water deficit.", calc, level=1)

        if chloride_eff is not None:
            ctext = (f"Chloride effect {_sfmt(chloride_eff)} → "
                     + _direction(chloride_eff, "hyperchloremic", "chloride depletion"))
            if chloride_is_comp:
                ctext += (" — the expected renal compensation for the "
                          + ("hypercapnia" if primary == "respiratory acidosis"
                             else "hypocapnia") + ", not a separate disorder")
            add(s_fs, ctext + ".",
                f"Cl corrected = Cl × 140/Na = {_fmt(cl)} × 140/{_fmt(na)} = "
                f"{_fmt(cl_corr)}\n"
                f"102 − Cl corrected = 102 − {_fmt(cl_corr)} = {_fmt(chloride_eff)}",
                "Correcting for Na separates a true chloride problem from a "
                "water problem. This is the term where normal saline shows up.")
            if not chloride_is_comp:
                if chloride_eff <= -SIG:
                    processes.append("hyperchloremic component")
                    diff_keys.append("nagma")
                elif chloride_eff >= SIG:
                    processes.append("chloride-depletion alkalosis")
                    diff_keys.extend(alk_keys)
                    if urine_cl is not None:
                        add(s_fs,
                            f"Urine Cl⁻ {_fmt(urine_cl)} → "
                            + ("<20: chloride-responsive (vomiting/NG, prior "
                               "diuretics)."
                               if urine_cl < 20 else
                               "≥20: chloride-resistant — mineralocorticoid "
                               "excess, ongoing diuretics, or severe hypokalemia. "
                               "Recent diuretics also raise urine Cl⁻, so a high "
                               "value is less conclusive than a low one."),
                            level=1)
        else:
            add(s_fs, "Chloride effect: needs Cl⁻.")

        if albumin_assumed:
            add(s_fs, "Albumin effect 0 — albumin not entered (assumed 4.2). "
                "Usually alkalinizing in sick inpatients and the term most "
                "often missed — enter it.")
        else:
            add(s_fs,
                f"Albumin effect {_sfmt(alb_eff)} → "
                + _direction(alb_eff, "hyperalbuminemia / hemoconcentration",
                             "hypoalbuminemia") + ".",
                f"2.5 × (4.2 − albumin) = 2.5 × (4.2 − {_fmt(albumin)}) = "
                f"{_fmt(alb_eff)}",
                "Albumin is the main weak acid (Atot). Low albumin is "
                "alkalinizing — a 'normal' pH or BE can hide a real acidosis. "
                "Reference albumin 4.2 g/dL, the same as the anion-gap "
                "correction.")
            if alb_eff >= SIG:
                processes.append("hypoalbuminemic alkalosis")

        if lactate is not None:
            ltag = _direction(lactate_eff, "lactic acidosis", "")
            if lactate_eff > -SIG:
                ltag = "minor"
            if lactate > 4:
                ltag += " (≥4: sepsis/shock range)"
            add(s_fs, f"Lactate effect {_sfmt(lactate_eff)} → {ltag}.",
                f"1 − lactate = 1 − {_fmt(lactate)} = {_fmt(lactate_eff)}",
                "A measured strong anion — each mmol/L narrows the SID by ≈1.")
            if lactate_eff <= -SIG:
                processes.append("lactic acidosis")
            elif lac_elevated:
                processes.append("mild lactic acidosis")
            if lac_elevated:
                diff_keys.append("lactic")
        else:
            add(s_fs, "Lactate not entered — it stays bundled in the "
                "unmeasured-anion remainder.")

        if residual is not None:
            text = (f"Unexplained remainder {_sfmt(residual)} (negative = "
                    "unmeasured anions)")
            if residual <= -SIG:
                sev = "major " if residual <= -MARKED else ""
                text += f" → {sev}unmeasured anions present"
                bundle = [n for n, miss in (("albumin", albumin_assumed),
                                            ("lactate", lactate is None)) if miss]
                if bundle:
                    text += " (also carries " + " and ".join(bundle) + ", not entered)"
                text += "."
                processes.append("unmeasured-anion component")
            elif residual <= -2:
                text += " → borderline (the cut is about −2 to −3)."
                borderline = "a mild unmeasured-anion load"
            elif residual >= SIG:
                if not albumin_assumed and sbe > 2:
                    diff_keys.append("alk_load")
                text += (" → an alkalinizing remainder — "
                         + ("most often an unentered low albumin." if albumin_assumed
                            else ("an alkali load (bicarbonate, citrate, "
                                  "milk-alkali), " if sbe > 2 else "")
                                 + "unmeasured cations, a lab whose normal anion "
                                 "gap runs low (8–10), or a lab error."))
            else:
                text += " → essentially none."
            add(s_fs, text,
                f"sum of effects = {_sum_terms(effects)} = {_fmt(effects_sum)}\n"
                f"{be_name} − sum = {_fmt(sbe)} − ({_fmt(effects_sum)}) = "
                f"{_fmt(residual)}",
                "Stewart's equivalent of the anion gap: the part of the base "
                "excess the measured effects don't explain.")

            if unmeasured_present:
                load = -residual
                if lactate is None and bhb is None:
                    diff_keys.append("hagma")
                    add(s_fs, f"Enter lactate and β-hydroxybutyrate to itemise "
                        f"the ≈{_fmt(load)}.", level=1)
                elif bhb is None:
                    diff_keys.append("hagma")
                    add(s_fs, f"Enter β-hydroxybutyrate to itemise the "
                        f"≈{_fmt(load)}.", level=1)
                dka = glucose is not None and glucose >= 250
                if bhb is not None and not keto_elevated:
                    add(s_fs, f"β-hydroxybutyrate {_fmt(bhb)} is normal — ketones "
                        "don't account for it.", level=1)
                elif keto_elevated:
                    amount = (f"≈{_fmt(keto_total)}" if dka else
                              f"≈{_fmt(keto_total_aka)}–{_fmt(keto_total)}")
                    add(s_fs,
                        f"Ketones account for {amount} (β-hydroxybutyrate "
                        f"{_fmt(keto_explained)} + estimated acetoacetate"
                        + ("" if dka else " — less in alcoholic ketoacidosis, "
                           "where the ratio is higher") + ").",
                        f"BHB − 0.6 = {_fmt(bhb)} − 0.6 = {_fmt(keto_explained)}\n"
                        + ("" if dka else
                           f"× 8/7 for acetoacetate (AKA, ≈7:1) = {_fmt(keto_total_aka)}\n")
                        + f"× 4/3 for acetoacetate (DKA, ≈3:1) = {_fmt(keto_total)}",
                        "Standard assays measure β-hydroxybutyrate only. "
                        "Acetoacetate runs about a third as high in DKA; in "
                        "alcoholic ketoacidosis the high-NADH state pushes the "
                        "ratio to 7:1 or more, so acetoacetate adds less. An "
                        "estimate either way. Each mmol/L of anion ≈ 1 mEq/L of "
                        "acid load.", level=1)
                if phos_share >= 1:
                    add(s_fs,
                        f"Phosphate {_fmt(phos)} accounts for ≈{_fmt(phos_share)} "
                        "(hyperphosphatemia — a weak-acid effect outside the "
                        "four-term partition).",
                        f"0.586 × (phosphate − 3.7) = 0.586 × ({_fmt(phos)} − 3.7) = "
                        f"{_fmt(phos_share)}",
                        "Retained phosphate adds anionic charge — the acid of renal "
                        "failure, tumor lysis and rhabdomyolysis.", level=1)
                if keto_unexplained is not None:
                    rem_lo = max(0.0, keto_unexplained)
                    rem_hi = (max(0.0, load - keto_total_aka - phos_share)
                              if keto_elevated and not dka else rem_lo)
                    rem = (f"≈{_fmt(rem_lo)}" if abs(rem_hi - rem_lo) < 0.1
                           else f"≈{_fmt(rem_lo)}–{_fmt(rem_hi)}")
                    if rem_hi < SIG:
                        text = f"{rem} remains — within noise"
                        if uremic:
                            text += f", and uremic anions at a BUN of {_fmt(bun)} fit it"
                    else:
                        sug = []
                        if uremic:
                            sug.append("uremic anions (sulfate, urate, hippurate) — "
                                       f"fits the BUN of {_fmt(bun)}")
                        if og is None:
                            sug.append("toxic alcohols (check an osmolar gap)")
                        elif og > 10:
                            sug.append(f"toxic alcohols (osmolar gap {_fmt(og)})")
                        sug.append("salicylates")
                        if not uremic:
                            sug.append("uremia")
                        if lactate is None:
                            sug.append("an unmeasured lactate")
                        text = f"{rem} remains → consider " + ", ".join(sug)
                        if og is not None and og <= 10:
                            text += (f" (osmolar gap {_fmt(og)} is normal — toxic "
                                     "alcohols less likely)")
                    if keto_unexplained > 5:
                        diff_keys.append("unexplained")
                    add(s_fs, text + ".", level=1)
        elif sbe is None:
            add(s_fs, "A gas or CO₂ (HCO₃⁻) is needed for the unmeasured-anion "
                "remainder.")
    elif na is not None or cl is not None or hco3 is not None:
        add(s_fs, "Na⁺ and Cl⁻ needed for the partitioning.")

    # =====================================================================
    # STEWART, FULL — SIDa / SIDe / SIG
    # =====================================================================
    if sid is not None:
        if sid < BASE_SID - 2:
            tag = ("low → acidifying: too much Cl⁻ relative to Na⁺, or "
                   "dilution by free water")
        elif sid > BASE_SID + 2:
            tag = ("high → alkalinizing: Cl⁻ lost relative to Na⁺, or "
                   "concentration by water loss")
        else:
            tag = "normal"
        add(s_full, f"Shortcut SID (Na + K − Cl) {_fmt(sid)} ({tag}; healthy ≈ "
            f"{_fmt(BASE_SID)}).",
            f"Na + K − Cl = {_fmt(na)} + {_fmt(k_used)} − {_fmt(cl)} = {_fmt(sid)}"
            + (" (K assumed 4)" if k is None else ""),
            "Strong cations minus strong anions. A smaller SID lets more water "
            "dissociate into H⁺ (acid); a larger one pushes toward alkalosis. "
            "Not the Na − Cl shortcut, whose normal is ≈ 36–38 (here "
            f"{_fmt(na - cl)}).")
        assumed = [n for n, v in (("iCa²⁺ 1.2", ca), ("Mg²⁺ 2.0", mg)) if v is None]
        atag = ("low" if sida < BASE_SIDA - 2 else
                "high" if sida > BASE_SIDA + 2 else "normal")
        add(s_full,
            f"Apparent SID (SIDa) {_fmt(sida)} ({atag}; healthy ≈ "
            f"{_fmt(BASE_SIDA)}) — adds the minor cations"
            + (" and lactate" if lactate is not None else "") + ".",
            f"SID + 2×iCa + 0.823×Mg − lactate = {_fmt(sid)} + 2×{ca_used:.2f} + "
            f"0.823×{_fmt(mg_used)} − {_fmt(lac_used)} = {_fmt(sida)}"
            + (" (assumed " + ", ".join(assumed) + ")" if assumed else ""),
            "iCa (mmol/L) × 2 and Mg (mg/dL) × 0.823 convert to mEq/L. Use "
            "ionized, not total, calcium.", level=1)

    if side is not None:
        etag = ("low" if side < BASE_SIDE - 2 else
                "high" if side > BASE_SIDE + 2 else "normal")
        side_assumed = [n for n, miss in (("albumin 4.2 g/dL", albumin_assumed),
                                          ("phosphate 3.7 mg/dL", phos is None)) if miss]
        add(s_full, f"Effective SID (SIDe) {_fmt(side)} ({etag}; healthy ≈ "
            f"{_fmt(BASE_SIDE)}"
            + ("; assumed " + ", ".join(side_assumed) if side_assumed else "")
            + ").",
            f"HCO₃⁻ + albumin charge + phosphate charge = {_fmt(hco3)} + "
            f"{_fmt(alb_ch)} + {_fmt(phos_ch)} = {_fmt(side)}",
            "The buffer base as an absolute amount. Base excess is the same "
            "buffer reported as a deviation from normal — which is why the "
            "partitioning above and the SIG below reach the same conclusions.")
        add(s_full,
            f"Albumin charge {_fmt(alb_ch)}"
            + (" (albumin assumed 4.2)" if albumin_assumed else "") + ".",
            f"albumin (g/L) × (0.123 × pH − 0.631) = {_fmt(10 * alb_used)} × "
            f"(0.123 × {_ph(ph_used)} − 0.631) = {_fmt(alb_ch)}", level=1)
        add(s_full,
            f"Phosphate charge {_fmt(phos_ch)}"
            + (" (phosphate assumed 3.7)" if phos is None else "") + ".",
            f"phosphate (mmol/L) = {_fmt(phos_used)} mg/dL × 0.323 = "
            f"{PHOS_TO_MMOL * phos_used:.2f}\n"
            f"{PHOS_TO_MMOL * phos_used:.2f} × (0.309 × {_ph(ph_used)} − 0.469) = "
            f"{_fmt(phos_ch)}", level=1)

    if sig is not None:
        add(s_full, f"Strong ion gap (SIG) {_fmt(sig)}.",
            f"SIDa − SIDe = {_fmt(sida)} − {_fmt(side)} = {_fmt(sig)}",
            "The unmeasured-anion concentration from two charge sums. There is "
            "no universal normal — it depends on the equations and analyzer.")
        if sig_excess >= SIG:
            stag = "unmeasured anions"
        elif sig_excess <= -SIG:
            ion_assumed = [n for n, v in (("iCa", ca), ("Mg", mg), ("phosphate", phos))
                           if v is None]
            stag = ("negative — most often an unentered low albumin; otherwise "
                    "unmeasured cations or lab error" if albumin_assumed else
                    "unmeasured cations (lithium, paraprotein), a lab whose "
                    "normal anion gap runs low, or lab error"
                    + (f"; {'/'.join(ion_assumed)} were assumed" if ion_assumed else ""))
        else:
            stag = "within noise (±2–3) — no unmeasured anions"
        add(s_full,
            f"Against a healthy baseline of {_fmt(BASE_SIG)} → excess "
            f"{_sfmt(sig_excess)} → {stag}.",
            f"SIG − baseline = {_fmt(sig)} − {_fmt(BASE_SIG)} = {_fmt(sig_excess)}",
            "Baseline = normal values (Na 140, K 4, iCa 1.2, Mg 2, Cl 102, "
            "lactate 1, HCO₃⁻ 24, albumin 4.2, phosphate 3.7, pH 7.40) run "
            "through these same equations. SIG is a difference of ~8 measured "
            "values, some from the gas and some from the lab — best trended "
            "within one patient.", level=1)
        if albumin_assumed:
            add(s_full, "Albumin assumed — the SIG here mirrors the anion gap; "
                "enter albumin for an independent read.", level=1)
    elif sid is not None:
        add(s_full, "CO₂ (HCO₃⁻) or a gas needed for SIDe and the strong ion gap.")

    # =====================================================================
    # PUTTING IT TOGETHER
    # =====================================================================

    # --- the story the partitioning tells --------------------------------
    if residual is not None:
        forces = []   # (value, acid name, alkali name, short name)
        forces.append((water_eff, "dilutional acidosis", "contraction alkalosis",
                       "free-water"))
        if not chloride_is_comp:
            forces.append((chloride_eff, "hyperchloremic acidosis",
                           "chloride-depletion alkalosis", "chloride"))
        if not albumin_assumed:
            forces.append((alb_eff, "hyperalbuminemic acidosis",
                           "hypoalbuminemic alkalosis", "albumin"))
        if lactate_eff is not None:
            forces.append((lactate_eff, "lactic acidosis", "", "lactate"))
        if residual <= -2 or residual >= SIG:
            forces.append((residual,
                           "uremic-anion acidosis"
                           if residual < 0 and not keto_elevated and (uremic or phos_share >= 2)
                           else "unmeasured-anion acidosis",
                           "an alkalinizing remainder"
                           + (" (likely an unentered low albumin)" if albumin_assumed else ""),
                           "unmeasured-anion"))

        def _name(f):
            n = f[1] if f[0] < 0 else f[2]
            return f"borderline {n}" if abs(f[0]) < BORDER else n

        major = sorted([f for f in forces if abs(f[0]) >= SIG],
                       key=lambda f: -abs(f[0]))
        modest = [f for f in forces if MODEST <= abs(f[0]) < SIG]
        acids = [f for f in major if f[0] < 0]
        alks = [f for f in major if f[0] > 0]
        lead, against = (acids, alks) if sbe <= 0 else (alks, acids)

        parts = []
        if acids and alks and abs(sbe) < SIG:
            both = sorted(acids + alks, key=lambda f: -abs(f[0]))
            parts.append("Offsetting forces — " + " against ".join(
                " and ".join(f"{_name(f)} ({_sfmt(f[0])})"
                             for f in both if (f[0] > 0) == side)
                for side in (both[0][0] > 0, not both[0][0] > 0))
                + f", netting a base excess of {_sfmt(sbe)}")
        elif lead:
            first = f"Dominant {_name(lead[0])} ({_sfmt(lead[0][0])})"
            first += "".join(f", plus {_name(f)} ({_sfmt(f[0])})" for f in lead[1:])
            if against:
                verb = "partly masked by" if sbe <= 0 else "partly offset by"
                first += f", {verb} " + " and ".join(
                    f"{_name(f)} ({_sfmt(f[0])})" for f in against)
            parts.append(first)
        elif against:
            parts.append("Offsetting " + " and ".join(
                f"{_name(f)} ({_sfmt(f[0])})" for f in against))
        if len(modest) == 1:
            parts.append(f"modest {modest[0][3]} contribution ({_sfmt(modest[0][0])})")
        elif modest:
            names = [f"{f[3]} ({_sfmt(f[0])})" for f in modest]
            parts.append("modest " + (" and ".join(names) if len(names) == 2 else
                                      ", ".join(names[:-1]) + " and " + names[-1])
                         + " contributions")
        if chloride_is_comp:
            parts.append(f"chloride shift ({_sfmt(chloride_eff)}) is the "
                         "expected renal compensation")
        if -2 < residual < SIG:
            parts.append(f"no hidden anions ({_sfmt(residual)})")
        story = "; ".join(parts)
        add(s_syn, story[0].upper() + story[1:] + ".")

    # --- do the unmeasured-anion measures agree? --------------------------
    # All three restated as unmeasured-anion excess (positive = more anions),
    # so the partitioning remainder flips sign.
    verdicts = []   # (label, excess, True/False/None)
    if residual is not None:
        verdicts.append(("partitioning", -residual,
                         True if -residual >= SIG else False if -residual < 2 else None))
    if sig_excess is not None and not albumin_assumed:
        verdicts.append(("SIG", sig_excess,
                         True if sig_excess >= SIG else False if sig_excess < 2 else None))
    if corrected is not None:
        # lactate is measured in the other two, so take it out of the gap too
        lac_share = max(0.0, lactate - LACTATE_BASE) if lactate is not None else 0.0
        ag_excess = corrected - NORMAL_AG - lac_share
        label = "corrected AG" + (" beyond lactate" if lactate is not None else "")
        verdicts.append((label, ag_excess,
                         True if ag_excess >= 4 else False if ag_excess < 2 else None))
    if len(verdicts) >= 2:
        detail = ", ".join(f"{lab} {_sfmt(val)}" for lab, val, _ in verdicts)
        detail = f"Unmeasured-anion excess (positive = more anions) — {detail}"
        calls = {v for _, _, v in verdicts}
        noise = (" — all within noise (±2–3), whatever the sign"
                 if all(abs(val) < SIG for _, val, _ in verdicts) else "")
        if calls == {True}:
            add(s_syn, f"{detail} → all agree: present.")
        elif calls == {False} or noise:
            add(s_syn, f"{detail} → all agree: none{noise}.")
        else:
            add(s_syn, f"{detail} → the measures don't "
                "fully agree. They use different reference points and the SIG "
                "carries ±2–3 of noise"
                + ("; albumin is assumed — enter it" if albumin_assumed else "")
                + ("; alkalemia raises the anion gap a little (more albumin charge)"
                   if pH is not None and pH > 7.45 else "")
                + ". Trust the one with the most measured inputs and trend it.")

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
                                           osm, ca, mg, phos, be, urine_cl))
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
        wants.append(" and ".join(missing_lytes) + " for the Stewart analysis")
    elif anything and hco3 is None and not has_gas:
        wants.append("the CO₂ (HCO₃⁻) to quantify the forces")
    if needs["split"]:
        wants.append(", ".join(needs["split"]) + " to itemise the unmeasured anions")
    if urine_cl is None and chloride_eff is not None and chloride_eff >= SIG \
            and not chloride_is_comp:
        wants.append("urine Cl⁻ to separate chloride-responsive from -resistant alkalosis")
    if sig is not None and not albumin_assumed:
        missing_ions = [n for n, v in (("K⁺", k), ("ionized Ca²⁺", ca), ("Mg²⁺", mg),
                                       ("phosphate", phos)) if v is None]
        if missing_ions:
            wants.append(" / ".join(missing_ions) + " to firm up the strong ion gap")
    next_info = ("Would sharpen the read: " + "; ".join(wants) + ".") if wants else None

    # --- assemble the conclusion -----------------------------------------
    # Name the anion when it's identified, rather than "unmeasured anions".
    if "unmeasured-anion component" in processes and keto_explained is not None \
            and keto_elevated:
        i = processes.index("unmeasured-anion component")
        processes[i] = "ketoacidosis"
        if keto_unexplained > 5:
            processes.insert(i + 1, "further unexplained anions")

    if has_gas:
        core = primary
        if ag_elevated and "metabolic acidosis" in primary:
            core = primary.replace("metabolic acidosis", "high-gap metabolic acidosis", 1)
            if "unmeasured-anion component" in processes:
                processes.remove("unmeasured-anion component")
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

    # A metabolic acidosis with the partitioning in hand is named by its
    # components — gap vs non-gap, which predominates, what masks it — rather
    # than by the anion gap alone (a modest lactate can lift a corrected gap
    # while chloride drives the acidosis).
    acid_headline = None
    acid_primary = ((primary in ("metabolic acidosis",
                                 "combined metabolic and respiratory acidosis")
                     or primary.startswith("mixed: metabolic acidosis"))
                    if has_gas else (sbe is not None and sbe < -2))
    if acid_primary and water_eff is not None and chloride_eff is not None:
        gap = []      # (magnitude, adjective, noun)
        if lac_elevated and lactate_eff is not None:
            mag = -lactate_eff
            gap.append((mag, "lactic" if mag >= SIG else "mild lactic",
                        "lactic acidosis" if mag >= SIG else "mild lactic acidosis"))
        if residual is not None and residual <= -SIG:
            if keto_explained is not None and keto_elevated:
                if keto_unexplained > 5:
                    gap.append((-residual, "ketoacid and other unmeasured-anion",
                                "ketoacidosis with other unmeasured anions"))
                else:
                    gap.append((-residual, "ketoacid", "ketoacidosis"))
            elif uremic or phos_share >= 2:
                gap.append((-residual, "uremic", "uremic anions (phosphate, sulfate)"))
            else:
                gap.append((-residual, "unmeasured-anion", "unmeasured anions"))
        elif residual is None and ag_elevated:
            gap.append((corrected - NORMAL_AG, "high-gap", "unmeasured anions"))
        nongap = []
        if chloride_eff <= -SIG and not chloride_is_comp:
            nongap.append((-chloride_eff, "hyperchloremic", "hyperchloremic"))
        if water_eff <= -SIG:
            nongap.append((-water_eff, "dilutional", "dilutional"))
        # Hypoalbuminemia masks; a chloride-depletion or contraction
        # alkalosis is a disorder of its own.
        masks = []
        if not albumin_assumed and alb_eff >= SIG:
            masks.append("hypoalbuminemic alkalosis")
        alk = []
        if chloride_eff >= SIG and not chloride_is_comp:
            alk.append("chloride depletion")
        if water_eff >= SIG:
            alk.append("contraction")
        resp = None
        if primary == "combined metabolic and respiratory acidosis":
            resp = "respiratory acidosis"
        elif (primary or "").startswith("mixed: metabolic acidosis with respiratory alkalosis"):
            resp = "respiratory alkalosis"
        elif resp_extras:
            resp = resp_extras[0].replace("superimposed ", "")

        gap.sort(key=lambda g: -g[0])
        nongap.sort(key=lambda g: -g[0])

        def _adj(group, kind):
            return " and ".join(g[1] for g in group) + f" ({kind})"

        # the acidosis, as a stand-alone headline and as a phrase to embed
        gm, nm = sum(g[0] for g in gap), sum(g[0] for g in nongap)
        if gap and nongap:
            big, small = ((_adj(nongap, "non-gap"), _adj(gap, "gap")) if nm >= gm
                          else (_adj(gap, "gap"), _adj(nongap, "non-gap")))
            if max(gm, nm) < 1.25 * min(gm, nm):
                inner = f"{big} and {small} in similar measure"
                desc = f"a metabolic acidosis with {big} and {small} parts in similar measure"
            else:
                # a small chloride-based part is within estimate noise; a
                # measured lactate is not
                soft = nm < gm and nm < BORDER
                art = "an" if small[0] in "aeio" or small.startswith("unmeasured") else "a"
                inner = (f"predominantly {big}, with possibly a small {small} component"
                         if soft else
                         f"predominantly {big}, with {art} {small} component")
                desc = f"a metabolic acidosis that is {inner}"
            head = f"Mixed metabolic acidosis: {inner}"
        elif nongap:
            nouns = " and ".join(g[2] for g in nongap)
            head = f"Non-gap metabolic acidosis — {nouns}"
            desc = f"a non-gap metabolic acidosis ({nouns})"
        elif gap:
            nouns = " and ".join(g[2] for g in gap)
            head = f"High-gap metabolic acidosis — {nouns}"
            desc = f"a high-gap metabolic acidosis ({nouns})"
        else:
            head, desc = "Metabolic acidosis", "a metabolic acidosis"

        others = []
        if alk:
            others.append("a metabolic alkalosis (" + " and ".join(alk) + ")")
        if resp:
            others.append(f"a {resp}")
        if others:
            label = "Triple disorder" if len(others) == 2 else "Mixed disorder"
            sentences = [f"{label}: {desc} — plus " + " and ".join(others) + "."]
            if masks:
                sentences.append(" and ".join(masks).capitalize()
                                 + " also partly masks the acidosis.")
        else:
            if masks:
                head += ", partly masked by " + " and ".join(masks)
            sentences = [head + "."]
            if comp_note == "appropriate respiratory compensation":
                sentences.append("Respiratory compensation appropriate.")
            elif comp_note:
                sentences.append(comp_note[0].upper() + comp_note[1:] + ".")
        if not has_gas:
            sentences.append("(No gas — pCO₂ assumed ≈40.)")
        acid_headline = " ".join(sentences)

    sections = [
        {"title": None, "steps": s_pre},
        {"title": "Boston — bicarbonate", "steps": s_bos},
        {"title": "Copenhagen — base excess", "steps": s_cop},
        {"title": "Stewart, simplified — base-excess partitioning (Fencl–Story)",
         "steps": s_fs},
        {"title": "Stewart, full — SIDa / SIDe / SIG", "steps": s_full},
        {"title": "Putting it together", "steps": s_syn},
    ]

    if core is None:
        headline = "Not enough data for a deterministic read"
        if not any(sec["steps"] for sec in sections):
            add(s_pre,
                "Enter whatever is available — a BMP is enough to start; a "
                "gas, albumin, lactate and the rest sharpen it. A clinical "
                "context alone is interpreted by the AI layer.")
    elif acid_headline is not None:
        headline = acid_headline
    elif has_gas and (primary.startswith("mixed: metabolic alkalosis")
                      or primary == "combined metabolic and respiratory alkalosis") \
            and chloride_eff is not None:
        parts = []
        if chloride_eff >= SIG:
            tag = "chloride depletion"
            if urine_cl is not None:
                tag += (", chloride-responsive by urine Cl⁻" if urine_cl < 20
                        else ", chloride-resistant by urine Cl⁻")
            parts.append(tag)
        if water_eff is not None and water_eff >= SIG:
            parts.append("contraction")
        if residual is not None and residual >= SIG and not albumin_assumed:
            parts.append("unexplained alkali")
        alk_desc = "a metabolic alkalosis" + (f" ({'; '.join(parts)})" if parts else "")
        resp = ("respiratory acidosis" if primary.startswith("mixed")
                else "respiratory alkalosis")
        headline = f"Mixed disorder: {alk_desc} — plus a {resp}."
        if not albumin_assumed and alb_eff is not None and alb_eff >= SIG:
            headline += " Hypoalbuminemic alkalosis adds to it."
    elif primary in ("respiratory acidosis", "respiratory alkalosis") and comp_note \
            and not comp_note.startswith("appropriate"):
        if comp_note.startswith("acute vs chronic"):
            head = primary.capitalize() + " (acute vs chronic hard to separate here)"
        else:
            head = (("Acute " if comp_note == "consistent with acute" else
                     "Chronic (or partly compensated) ") + primary)
        extras_all = [e.replace(" (free-water)", "")
                      for e in dict.fromkeys(resp_extras + processes)]
        if extras_all and sbe is not None and abs(sbe) < SIG:
            head += (", with offsetting metabolic forces ("
                     + ", ".join(extras_all) + ")")
        elif extras_all:
            head += " — plus " + " + ".join(extras_all)
        headline = head + "."
    else:
        headline = core[0].upper() + core[1:]
        extras_all = []
        for e in dict.fromkeys(resp_extras + processes):
            base = e.replace("superimposed ", "")
            if e not in core and base not in core:
                extras_all.append(e)
        if extras_all:
            headline += " — " + " + ".join(extras_all)
        if comp_note == "appropriate respiratory compensation":
            headline += ". Respiratory compensation appropriate."
        elif comp_note and comp_note.startswith("borderline"):
            headline += f". {comp_note[0].upper()}{comp_note[1:]}."
        elif comp_note:
            headline += f" — {comp_note}."

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
        ("osmolality", osm, " mOsm/kg"), ("urine Cl", urine_cl, " mEq/L"),
    ]:
        if val is not None:
            parts.append(f"{label} {_fmt(val)}{unit}")
    if sbe is not None:
        parts.append(f"HCO₃⁻ deviation {_sfmt(sbe)} (BE stand-in, pCO₂ assumed 40)"
                     if be_source == "hco3" else
                     f"base excess {_sfmt(sbe)}" + (" (analyzer)" if be_source == "measured" else ""))
    effect_bits = []
    if water_eff is not None:
        effect_bits.append(f"water {_sfmt(water_eff)}")
    if chloride_eff is not None:
        effect_bits.append(f"chloride {_sfmt(chloride_eff)}"
                           + (" (renal compensation)" if chloride_is_comp else ""))
    if alb_eff is not None and not albumin_assumed:
        effect_bits.append(f"albumin {_sfmt(alb_eff)}")
    if lactate_eff is not None:
        effect_bits.append(f"lactate {_sfmt(lactate_eff)}")
    if residual is not None:
        effect_bits.append(f"unmeasured {_sfmt(residual)}")
    if effect_bits:
        parts.append("Fencl–Story effects (mEq/L): " + ", ".join(effect_bits))
    if sida is not None:
        parts.append(f"SIDa {_fmt(sida)}")
    if side is not None:
        parts.append(f"SIDe {_fmt(side)}")
    if sig is not None and not albumin_assumed:
        parts.append(f"SIG {_fmt(sig)} (healthy baseline {_fmt(BASE_SIG)})")
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

