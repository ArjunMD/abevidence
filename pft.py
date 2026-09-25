"""Pulmonary function test interpretation for the Tools page.

Pure arithmetic — no AI, no network. Runs on whatever values are entered.

Follows the ATS/ERS 2022 interpretation standard (Stanojevic et al.): a
value is abnormal when it falls outside the lower (or upper) limit of normal,
i.e. a z-score beyond ±1.645, and severity is graded on that z-score
(−1.65 to −2.5 mild, −2.5 to −4 moderate, below −4 severe). Reference values
come from the lab report — the tool does not run reference equations. When
a row has no z-score it falls back to measured vs LLN, and with neither to
fixed %-predicted cutoffs (flagged as such, since those misclassify the old,
the young, and the very short or tall).

  SPIROMETRY     FEV1/FVC (and FEV1/VC using the larger IVC) → obstruction;
                 FEV1 grades it; FVC; bronchodilator response (2022 rule:
                 >10% of predicted; 2005 rule: ≥12% and ≥200 mL).
  LUNG VOLUMES   TLC → restriction / hyperinflation; RV and RV/TLC → air
                 trapping; IVC vs FVC; complex restriction (FVC% ≪ TLC%).
  DIFFUSION      DLCO, Hb-adjusted DLCO (Cotes, as in ATS/ERS 2017), VA,
                 KCO (DL/VA) and VA/TLC — separating loss of alveolar volume
                 from loss of gas transfer per unit volume.
  FLOW-VOLUME    Loop shape, FEF50/FIF50 and Empey index → upper airway
                 obstruction.
  PUTTING IT TOGETHER — the ventilatory pattern plus the gas-transfer
  pattern, and the diagnostic categories each combination points to.

Each step is {"text", "calc", "note", "level"}, as in acid_base: text the
finding, calc the formula / cutoff with values plugged in, note a hover
caveat, level 0 for a step and 1 for a detail beneath it.
"""

Z_LIMIT = 1.645        # LLN / ULN = 5th / 95th percentile
Z_MODERATE = -2.5
Z_SEVERE = -4.0

FIXED_RATIO = 70.0     # GOLD fixed FEV1/FVC cutoff, used only without LLN/z
BDR_PRED_PCT = 10.0    # ATS/ERS 2022: change > 10% of predicted
BDR_BASE_PCT = 12.0    # ATS/ERS 2005: ≥ 12% of baseline …
BDR_BASE_ML = 200.0    # … and ≥ 200 mL
VC_GAP_L = 0.2         # IVC exceeding FVC by more than this → collapse on forced expiration
COMPLEX_GAP = 10.0     # FVC %pred this far below TLC %pred → complex restriction
VA_TLC_LOW = 0.85      # VA under 85% of TLC → uneven gas mixing
EMPEY = 10.0           # FEV1 (mL) / PEF (L/min) above this → upper airway obstruction
FEF_FIF_EXTRA = 2.0    # FEF50/FIF50 ≥ this → variable extrathoracic obstruction
FEF_FIF_INTRA = 0.3    # FEF50/FIF50 ≤ this → variable intrathoracic obstruction

# Parameter → (display name, unit, format, fallback low %pred, fallback high
# %pred, whether a high value means something). Units are the usual report
# units: volumes in L, ratios in %, DLCO mL/min/mmHg, KCO per L of VA.
PARAMS = {
    "ratio":   ("FEV1/FVC", "%", "{:.0f}", None, None, False),
    "fev1":    ("FEV1", "L", "{:.2f}", 80.0, None, False),
    "fvc":     ("FVC", "L", "{:.2f}", 80.0, None, False),
    "fef2575": ("FEF25–75", "L/s", "{:.2f}", 65.0, None, False),
    "tlc":     ("TLC", "L", "{:.2f}", 80.0, 120.0, True),
    "rv":      ("RV", "L", "{:.2f}", 65.0, 140.0, True),
    "rv_tlc":  ("RV/TLC", "%", "{:.0f}", None, 120.0, True),
    "frc":     ("FRC", "L", "{:.2f}", 65.0, 120.0, True),
    "ivc":     ("IVC", "L", "{:.2f}", 80.0, None, False),
    "dlco":    ("DLCO", "mL/min/mmHg", "{:.1f}", 75.0, 140.0, True),
    "dlco_adj": ("DLCO (Hb-adjusted)", "mL/min/mmHg", "{:.1f}", 75.0, 140.0, True),
    "va":      ("VA", "L", "{:.2f}", 80.0, None, False),
    "kco":     ("KCO (DL/VA)", "mL/min/mmHg/L", "{:.2f}", 75.0, 120.0, True),
}
RATIO_KEYS = ("ratio", "rv_tlc")

# %-predicted severity bands, used only when no z-score was entered.
# (floor, label): the first floor the value meets or exceeds wins.
_PCT_BANDS = {
    "obstruction": [(70, "mild"), (60, "moderate"), (50, "moderately severe"),
                    (35, "severe"), (float("-inf"), "very severe")],   # ATS/ERS 2005, FEV1
    "restriction": [(70, "mild"), (60, "moderate"), (float("-inf"), "severe")],  # TLC
    "diffusion":   [(60, "mild"), (40, "moderate"), (float("-inf"), "severe")],  # DLCO
}

FLOW_LOOP_SHAPES = {
    "Not reviewed": None,
    "Normal": ("normal loop", None),
    "Scooped (concave) expiratory limb":
        ("concave expiratory limb → intrathoracic (lower) airway obstruction", None),
    "Narrow and tall, convex expiratory limb":
        ("small, steep loop → restrictive shape (volume lost, flows preserved)", None),
    "Flattened inspiratory limb only":
        ("inspiratory plateau → variable extrathoracic upper airway obstruction",
         "extrathoracic"),
    "Flattened expiratory limb only (plateau)":
        ("expiratory plateau → variable intrathoracic upper airway obstruction",
         "intrathoracic"),
    "Both limbs flattened":
        ("inspiratory and expiratory plateaus → fixed upper airway obstruction", "fixed"),
    "Irregular / early termination":
        ("irregular or truncated loop → submaximal effort, cough or glottic closure; "
         "flows and FVC may be underestimated", None),
}

_UAO_DIFF = {
    "extrathoracic": "Variable extrathoracic obstruction: vocal cord paralysis or "
                     "dysfunction, laryngeal or extrathoracic tracheal lesions, "
                     "extrathoracic tracheomalacia.",
    "intrathoracic": "Variable intrathoracic obstruction: intrathoracic tracheomalacia, "
                     "tumour of the lower trachea or mainstem bronchus.",
    "fixed": "Fixed upper airway obstruction: tracheal stenosis (post-intubation or "
             "tracheostomy), goitre, circumferential tumour, granulomatosis with "
             "polyangiitis.",
}


_ADVERB = {"mild": "mildly ", "moderate": "moderately ", "severe": "severely "}


def _f(key: str, x: float) -> str:
    return PARAMS[key][2].format(x)


def _z(z: float) -> str:
    return f"{z:+.2f}".replace("-", "−")


def _norm_ratio(x):
    """Ratios are handled in %; accept 0.68 as well as 68."""
    if x is None:
        return None
    return x * 100.0 if abs(x) <= 1.5 else x


def _read(key: str, row: dict) -> dict:
    """Classify one row against its reference. Returns {meas, pct, lln, z, pred,
    flag ('low'/'high'/'normal'/None), basis (cutoff with values), fallback}."""
    _, _, _, lo_pct, hi_pct, high_matters = PARAMS[key]
    meas, pct, lln, z = (row.get(k) for k in ("meas", "pct", "lln", "z"))
    pred = meas / (pct / 100.0) if meas is not None and pct else None
    flag, basis, fallback = None, None, False

    if z is not None:
        if z < -Z_LIMIT:
            flag, basis = "low", f"z {_z(z)} < −1.645 (below LLN)"
        elif high_matters and z > Z_LIMIT:
            flag, basis = "high", f"z {_z(z)} > +1.645 (above ULN)"
        else:
            flag, basis = "normal", f"z {_z(z)} (within ±1.645)"
    elif lln is not None and meas is not None:
        # Without a z-score the upper limit is mirrored from the lower one —
        # exact for a symmetric distribution, close enough for a flag.
        uln = 2 * pred - lln if pred is not None else None
        if meas < lln:
            flag, basis = "low", f"{_f(key, meas)} < LLN {_f(key, lln)}"
        elif high_matters and uln is not None and meas > uln:
            flag, basis = "high", (f"{_f(key, meas)} > ULN ≈ 2 × {_f(key, pred)} − "
                                   f"{_f(key, lln)} = {_f(key, uln)}")
        else:
            flag, basis = "normal", f"{_f(key, meas)} ≥ LLN {_f(key, lln)}"
    elif key == "ratio" and meas is not None:
        fallback = True
        if meas < FIXED_RATIO:
            flag, basis = "low", f"{_f(key, meas)} < {FIXED_RATIO:.0f} (fixed ratio)"
        else:
            flag, basis = "normal", f"{_f(key, meas)} ≥ {FIXED_RATIO:.0f} (fixed ratio)"
    elif pct is not None and lo_pct is not None:
        fallback = True
        if pct < lo_pct:
            flag, basis = "low", f"{pct:.0f}% pred < {lo_pct:.0f}%"
        elif high_matters and hi_pct is not None and pct > hi_pct:
            flag, basis = "high", f"{pct:.0f}% pred > {hi_pct:.0f}%"
        else:
            flag, basis = "normal", f"{pct:.0f}% pred"
    elif pct is not None and hi_pct is not None:     # RV/TLC: only high matters
        fallback = True
        flag, basis = (("high", f"{pct:.0f}% pred > {hi_pct:.0f}%") if pct > hi_pct
                       else ("normal", f"{pct:.0f}% pred"))

    return {"meas": meas, "pct": pct, "lln": lln, "z": z, "pred": pred,
            "flag": flag, "basis": basis, "fallback": fallback}


def _severity(r: dict, bands: str):
    """Severity of a low value: by z-score, else by %pred bands."""
    if r["flag"] != "low":
        return None
    if r["z"] is not None:
        if r["z"] < Z_SEVERE:
            return "severe"
        return "moderate" if r["z"] < Z_MODERATE else "mild"
    if r["pct"] is not None:
        for floor, label in _PCT_BANDS[bands]:
            if r["pct"] >= floor:
                return label
    return None


def _value_text(key: str, r: dict) -> str:
    """'FEV1 1.80 L (55% pred, z −3.10)' from whatever parts were entered."""
    name, unit, *_ = PARAMS[key]
    bits = []
    if r["meas"] is not None:
        bits.append(f"{_f(key, r['meas'])}{'%' if unit == '%' else ' ' + unit}")
    extra = []
    if r["pct"] is not None:
        extra.append(f"{r['pct']:.0f}% pred")
    if r["z"] is not None:
        extra.append(f"z {_z(r['z'])}")
    text = f"{name} {' '.join(bits)}".rstrip()
    if extra:
        text += f" ({', '.join(extra)})"
    return text


_FALLBACK_NOTE = ("No z-score or LLN entered, so this uses a fixed cutoff. ATS/ERS "
                  "2022 uses the LLN (z −1.645); fixed %-predicted and 0.70 cutoffs "
                  "over-call abnormality in older patients and under-call it in the young.")


def interpret(rows: dict, fev1_post=None, fvc_post=None, hb=None, male=True,
              loop_shape=None, pef=None, fef50=None, fif50=None) -> dict:
    """rows: {param: {"meas", "pct", "lln", "z"}} for any PARAMS key (all
    optional). fev1_post / fvc_post in L. hb in g/dL; male selects the Cotes
    adult-male constant (else female / under 15). loop_shape is a
    FLOW_LOOP_SHAPES key; pef, fef50, fif50 in L/s.
    Returns {headline, sections, differential, warnings, next}."""
    rows = {k: dict(rows.get(k) or {}) for k in PARAMS}
    for k in RATIO_KEYS:
        rows[k]["meas"] = _norm_ratio(rows[k].get("meas"))
        rows[k]["lln"] = _norm_ratio(rows[k].get("lln"))

    warnings: list[str] = []
    nxt: list[str] = []
    diff: list[str] = []
    s_spi, s_vol, s_dl, s_loop, s_syn = [], [], [], [], []

    def add(sec, text, calc=None, note=None, level=0):
        sec.append({"text": text, "calc": calc, "note": note, "level": level})

    def m(k):
        return rows[k].get("meas")

    # --- derived ratios ----------------------------------------------------
    ratio_computed = False
    if m("fev1") is not None and m("fvc"):
        computed = m("fev1") / m("fvc") * 100.0
        if m("ratio") is None:
            rows["ratio"]["meas"] = computed
            ratio_computed = True
        elif abs(computed - m("ratio")) > 3:
            warnings.append(f"FEV1/FVC entered as {m('ratio'):.0f}% but FEV1 ÷ FVC = "
                            f"{computed:.0f}% — recheck (pre vs post values mixed?).")
    rvtlc_computed = False
    if m("rv_tlc") is None and m("rv") is not None and m("tlc"):
        rows["rv_tlc"]["meas"] = m("rv") / m("tlc") * 100.0
        rvtlc_computed = True

    # --- sanity ------------------------------------------------------------
    if m("fev1") is not None and m("fvc") is not None and m("fev1") > m("fvc"):
        warnings.append("FEV1 is larger than FVC — recheck the values.")
    if m("fvc") is not None and m("tlc") is not None and m("fvc") > m("tlc"):
        warnings.append("FVC is larger than TLC — recheck the values.")
    if m("rv") is not None and m("tlc") is not None and m("rv") >= m("tlc"):
        warnings.append("RV is not smaller than TLC — recheck the values.")
    for k, row in rows.items():
        if row.get("z") is not None and abs(row["z"]) > 8:
            warnings.append(f"{PARAMS[k][0]} z-score beyond ±8 — recheck the value.")

    R = {k: _read(k, rows[k]) for k in PARAMS}
    any_fallback = False

    def line(sec, key, meaning=None, calc_extra=None, level=0, note=None):
        """Standard value line: 'FEV1 1.80 L (55% pred) → meaning', cutoff below."""
        nonlocal any_fallback
        r = R[key]
        text = _value_text(key, r)
        if meaning:
            text += f" → {meaning}"
        calcs = [c for c in (calc_extra, r["basis"]) if c]
        if r["fallback"]:
            any_fallback = True
            note = (note + " " if note else "") + _FALLBACK_NOTE
        add(sec, text, "\n".join(calcs) or None, note, level)

    # =====================================================================
    # SPIROMETRY
    # =====================================================================
    ratio, fev1, fvc = R["ratio"], R["fev1"], R["fvc"]
    obstruction = ratio["flag"] == "low"
    obs_sev = _severity(fev1, "obstruction") if obstruction else None
    ratio_calc = (f"FEV1/FVC = {m('fev1'):.2f} / {m('fvc'):.2f} = {m('ratio'):.0f}%"
                  if ratio_computed else None)
    if ratio["flag"] == "low":
        line(s_spi, "ratio", "obstruction", ratio_calc)
    elif ratio["flag"] == "normal":
        line(s_spi, "ratio", "no obstruction by FEV1/FVC", ratio_calc)
    elif m("ratio") is not None:
        line(s_spi, "ratio", None, ratio_calc)

    # FEV1/VC: a slow or inspiratory VC larger than the FVC can unmask
    # obstruction hidden by air trapping on the forced manoeuvre.
    vc_unmasked = False
    if (m("ivc") is not None and m("fev1") is not None and m("fvc") is not None
            and m("ivc") > m("fvc") and ratio["flag"] == "normal"):
        fev1_vc = m("fev1") / m("ivc") * 100.0
        cut = ratio["lln"] if ratio["lln"] is not None else (
            FIXED_RATIO if ratio["z"] is None else None)
        if cut is not None and fev1_vc < cut:
            vc_unmasked = obstruction = True
            obs_sev = _severity(fev1, "obstruction")
            add(s_spi, f"FEV1/IVC {fev1_vc:.0f}% → obstruction unmasked by the larger VC",
                f"FEV1/IVC = {m('fev1'):.2f} / {m('ivc'):.2f} = {fev1_vc:.0f}%\n"
                f"{fev1_vc:.0f} < {cut:.0f}",
                "ATS/ERS 2022 uses the largest available VC for the ratio. A forced "
                "manoeuvre can collapse airways early and shrink the FVC, hiding "
                "obstruction.", level=1)

    if fev1["meas"] is not None or fev1["pct"] is not None or fev1["z"] is not None:
        sev = _severity(fev1, "obstruction")
        if obstruction and sev:
            meaning = f"{sev} obstruction"
        elif obstruction:
            meaning = "grades the obstruction (enter % pred or z to grade)"
        elif fev1["flag"] == "low":
            meaning = "reduced"
        else:
            meaning = None
        line(s_spi, "fev1", meaning,
             note="ATS/ERS 2022 grades severity of any spirometric impairment on the "
                  "FEV1 z-score: −1.65 to −2.5 mild, −2.5 to −4 moderate, < −4 severe.")

    if fvc["meas"] is not None or fvc["pct"] is not None or fvc["z"] is not None:
        if fvc["flag"] == "low" and obstruction:
            meaning = "reduced — air trapping or coexisting restriction (TLC separates them)"
        elif fvc["flag"] == "low":
            meaning = "reduced with preserved ratio — restriction possible, not proven"
        else:
            meaning = None
        line(s_spi, "fvc", meaning)

    if R["fef2575"]["meas"] is not None or R["fef2575"]["pct"] is not None:
        line(s_spi, "fef2575", "reduced" if R["fef2575"]["flag"] == "low" else None,
             note="Small-airway flow, but too variable and FVC-dependent to diagnose "
                  "obstruction on its own (ATS/ERS 2022 advises against using it).")

    # --- bronchodilator response -------------------------------------------
    bdr_positive = False
    for key, post in (("fev1", fev1_post), ("fvc", fvc_post)):
        pre = m(key)
        if post is None or pre is None:
            continue
        d = post - pre
        name = PARAMS[key][0]
        pred = R[key]["pred"]
        calcs = [f"Δ{name} = {post:.2f} − {pre:.2f} = {d * 1000:+.0f} mL".replace("-", "−")]
        verdicts = []
        if pred:
            dp = d / pred * 100.0
            calcs.append(f"= {dp:+.1f}% of predicted ({pred:.2f} L)".replace("-", "−"))
            verdicts.append(dp > BDR_PRED_PCT)
        db = d / pre * 100.0
        calcs.append(f"= {db:+.1f}% of baseline".replace("-", "−"))
        old_rule = db >= BDR_BASE_PCT and d * 1000 >= BDR_BASE_ML
        if not pred:
            verdicts.append(old_rule)
        positive = verdicts[0]
        bdr_positive |= positive
        rule = ("> 10% of predicted (ATS/ERS 2022)" if pred
                else "≥ 12% and ≥ 200 mL (ATS/ERS 2005; enter % pred for the 2022 rule)")
        text = (f"Post-BD {name} {post:.2f} L → "
                + ("significant bronchodilator response" if positive
                   else "no significant response") + f" — threshold {rule}")
        note = None
        if pred and old_rule != positive:
            note = ("The older 2005 rule (≥12% and ≥200 mL from baseline) "
                    + ("would call this positive." if old_rule else "would call this negative."))
        add(s_spi, text, "\n".join(calcs), note)
    if fev1_post is not None and fvc_post:
        post_ratio = fev1_post / fvc_post * 100.0
        cut = ratio["lln"] if ratio["lln"] is not None else FIXED_RATIO
        cut_name = "LLN" if ratio["lln"] is not None else "fixed 70"
        if obstruction:
            persists = post_ratio < cut
            add(s_spi, f"Post-BD FEV1/FVC {post_ratio:.0f}% → "
                + ("obstruction persists after bronchodilator" if persists
                   else "ratio normalises after bronchodilator"),
                f"{fev1_post:.2f} / {fvc_post:.2f} = {post_ratio:.0f}% "
                f"{'<' if persists else '≥'} {cut:.0f} ({cut_name})",
                "A post-bronchodilator ratio below the cutoff is the spirometric "
                "criterion for persistent airflow obstruction (as in COPD); full "
                "normalisation favours asthma.", level=1)
    if obstruction and fev1_post is None:
        nxt.append("post-bronchodilator spirometry (reversibility)")

    # =====================================================================
    # LUNG VOLUMES
    # =====================================================================
    tlc, rv, rvtlc, frc = R["tlc"], R["rv"], R["rv_tlc"], R["frc"]
    restriction = tlc["flag"] == "low"
    hyperinflation = tlc["flag"] == "high"
    res_sev = _severity(tlc, "restriction") if restriction else None
    if tlc["flag"] is not None or tlc["meas"] is not None:
        meaning = {"low": f"{res_sev + ' ' if res_sev else ''}restriction",
                   "high": "hyperinflation"}.get(tlc["flag"])
        line(s_vol, "tlc", meaning,
             note="TLC is the only measurement that confirms restriction; a low FVC "
                  "alone is right less than half the time.")

    air_trapping = rv["flag"] == "high" or rvtlc["flag"] == "high"
    if rv["flag"] is not None or rv["meas"] is not None:
        meaning = {"high": "air trapping", "low": "reduced (with restriction)"}.get(rv["flag"])
        if rv["flag"] == "low" and not restriction:
            meaning = "reduced"
        line(s_vol, "rv", meaning)
    if rvtlc["meas"] is not None or rvtlc["pct"] is not None or rvtlc["z"] is not None:
        calc = (f"RV/TLC = {m('rv'):.2f} / {m('tlc'):.2f} = {m('rv_tlc'):.0f}%"
                if rvtlc_computed else None)
        meaning = "air trapping" if rvtlc["flag"] == "high" else None
        note = None
        if rvtlc["flag"] is None:
            note = ("RV/TLC rises with age (≈25% in young adults to ≈40% in the "
                    "elderly); enter the report's % pred, LLN or z to flag it.")
        line(s_vol, "rv_tlc", meaning, calc, level=1 if rv["meas"] is not None else 0,
             note=note)
    if frc["flag"] is not None or frc["meas"] is not None:
        meaning = {"high": "hyperinflation (end-expiratory)",
                   "low": "reduced — restriction or obesity"}.get(frc["flag"])
        line(s_vol, "frc", meaning)

    if R["ivc"]["meas"] is not None or R["ivc"]["pct"] is not None:
        calc, meaning, note = None, None, None
        if m("ivc") is not None and m("fvc") is not None:
            gap = m("ivc") - m("fvc")
            calc = f"IVC − FVC = {m('ivc'):.2f} − {m('fvc'):.2f} = {gap * 1000:+.0f} mL".replace("-", "−")
            if gap > VC_GAP_L:
                meaning = "IVC exceeds FVC — airway collapse / air trapping on forced expiration"
                note = ("A forced expiration compresses floppy or narrowed airways and "
                        "closes them before the lung empties; the relaxed VC does not.")
        line(s_vol, "ivc", meaning, calc, note=note)

    complex_restriction = False
    if restriction and fvc["pct"] is not None and tlc["pct"] is not None:
        gap = fvc["pct"] - tlc["pct"]
        if gap <= -COMPLEX_GAP:
            complex_restriction = True
            add(s_vol, "FVC is reduced out of proportion to TLC → complex restriction",
                f"FVC% − TLC% = {fvc['pct']:.0f} − {tlc['pct']:.0f} = {gap:.0f} (≤ −10)",
                "Clay et al. 2017: a disproportionately low FVC means something besides "
                "volume loss — respiratory muscle weakness, chest wall disease, or "
                "occult air trapping (high RV).", level=1)

    if tlc["flag"] is None and fvc["flag"] == "low":
        nxt.append("lung volumes (TLC) to confirm or exclude restriction")

    # =====================================================================
    # DIFFUSION
    # =====================================================================
    dl, dladj, va, kco = R["dlco"], R["dlco_adj"], R["va"], R["kco"]
    hb_calc = None
    if (dladj["flag"] is None and dladj["meas"] is None and hb and dl["meas"] is not None):
        # Cotes: DLCO_pred(Hb) = DLCO_pred × 1.7Hb / (k + Hb); applied here to the
        # measured value instead, which puts it on the unadjusted predicted scale.
        k = 10.22 if male else 9.38
        factor = (k + hb) / (1.7 * hb)
        adj = dl["meas"] * factor
        rows["dlco_adj"] = {"meas": adj, "lln": dl["lln"],
                            "pct": adj / dl["pred"] * 100.0 if dl["pred"] else None}
        dladj = R["dlco_adj"] = _read("dlco_adj", rows["dlco_adj"])
        hb_calc = (f"DLCO × ({k} + Hb) / (1.7 × Hb) = {dl['meas']:.1f} × "
                   f"({k} + {hb:.1f}) / (1.7 × {hb:.1f}) = {adj:.1f}")
    dl_use = dladj if dladj["flag"] is not None else dl
    dl_flag = dl_use["flag"]
    dl_sev = _severity(dl_use, "diffusion")

    if dl["flag"] is not None or dl["meas"] is not None:
        meaning = None
        if dladj["flag"] is None:
            meaning = {"low": f"{dl_sev + ' ' if dl_sev else ''}reduction in gas transfer",
                       "high": "elevated"}.get(dl["flag"])
            if dl["flag"] == "low" and not hb:
                nxt.append("hemoglobin, to adjust the DLCO")
        line(s_dl, "dlco", meaning)
    if dladj["flag"] is not None:
        meaning = {"low": f"{dl_sev + ' ' if dl_sev else ''}reduction in gas transfer",
                   "high": "elevated", "normal": None}.get(dladj["flag"])
        if dl["flag"] == "low" and dladj["flag"] == "normal":
            meaning = "normal once adjusted — low raw DLCO explained by anemia"
        line(s_dl, "dlco_adj", meaning, hb_calc, level=1 if dl["meas"] is not None else 0,
             note=f"Cotes equation (ATS/ERS 2017), {'adult male' if male else 'female / under 15'} "
                  "constant. Less hemoglobin means less CO uptake capacity at the "
                  "same membrane.")

    if va["flag"] is not None or va["meas"] is not None:
        line(s_dl, "va", "reduced alveolar volume" if va["flag"] == "low" else None)
    if m("va") is not None and m("tlc"):
        va_tlc = m("va") / m("tlc")
        if va_tlc < VA_TLC_LOW:
            add(s_dl, f"VA/TLC {va_tlc:.2f} → uneven gas mixing; VA underestimates lung volume",
                f"VA / TLC = {m('va'):.2f} / {m('tlc'):.2f} = {va_tlc:.2f} (< {VA_TLC_LOW})",
                "The single-breath test gas doesn't reach poorly ventilated regions, "
                "typical of obstruction — so VA (and DLCO) understate the lung.", level=1)

    if kco["flag"] is not None or kco["meas"] is not None:
        meaning = {"low": "reduced transfer per unit volume",
                   "high": "increased transfer per unit volume"}.get(kco["flag"])
        line(s_dl, "kco", meaning,
             note="KCO is not a 'corrected DLCO': when VA falls from incomplete "
                  "expansion, KCO normally rises (capillary blood is concentrated "
                  "in less lung), so a 'normal' KCO with a low VA can still be "
                  "abnormal (Hughes & Pride 2012).")

    extraparenchymal_dl = False
    if dl_flag == "low" and va["flag"] == "low" and kco["flag"] in ("normal", "high"):
        extraparenchymal_dl = True
        add(s_dl, "Low DLCO from lost alveolar volume, with gas transfer per unit "
                  "preserved → incomplete expansion rather than membrane disease",
            None, "Chest wall, pleura, respiratory muscles or resection shrink the "
                  "lung without damaging the alveolar–capillary surface.")
    elif dl_flag == "low" and kco["flag"] == "low":
        add(s_dl, "Low DLCO with low KCO → loss of alveolar–capillary surface "
                  "(parenchymal or pulmonary vascular)")

    # =====================================================================
    # FLOW-VOLUME LOOP
    # =====================================================================
    uao = None
    shape = FLOW_LOOP_SHAPES.get(loop_shape) if loop_shape else None
    if shape:
        add(s_loop, f"Loop: {shape[0]}")
        uao = shape[1]
    if fef50 is not None and fif50:
        rr = fef50 / fif50
        meaning = None
        if rr >= FEF_FIF_EXTRA:
            meaning, uao = "variable extrathoracic obstruction pattern", uao or "extrathoracic"
        elif rr <= FEF_FIF_INTRA:
            meaning, uao = "variable intrathoracic obstruction pattern", uao or "intrathoracic"
        add(s_loop, f"FEF50/FIF50 {rr:.2f}" + (f" → {meaning}" if meaning else ""),
            f"FEF50 / FIF50 = {fef50:.2f} / {fif50:.2f} = {rr:.2f}",
            "Normally just under 1. Inspiratory flow is capped in extrathoracic "
            "lesions (ratio ≥ 2); expiratory flow in intrathoracic ones (≤ 0.3). A "
            "fixed lesion caps both and leaves the ratio near 1.")
    if pef and m("fev1") is not None:
        empey = m("fev1") * 1000 / (pef * 60)
        high = empey > EMPEY
        add(s_loop, f"Empey index {empey:.1f}"
            + (" → upper airway obstruction likely" if high else ""),
            f"FEV1 (mL) / PEF (L/min) = {m('fev1') * 1000:.0f} / {pef * 60:.0f} = "
            f"{empey:.1f} ({'>' if high else '≤'} {EMPEY:.0f})",
            "A central lesion caps peak flow far more than it caps the FEV1.")
        if high and uao is None:
            nxt.append("review the flow-volume loop for upper airway obstruction")

    # =====================================================================
    # PUTTING IT TOGETHER
    # =====================================================================
    head: list[str] = []
    have_spiro = ratio["flag"] is not None or fvc["flag"] is not None
    have_tlc = tlc["flag"] is not None

    if obstruction and restriction:
        head.append("mixed obstructive–restrictive defect")
        add(s_syn, "Obstruction (low FEV1/FVC) and restriction (low TLC) → mixed defect",
            note="Only lung volumes can make this call — a low FVC with obstruction "
                 "is usually air trapping.")
    elif obstruction:
        head.append(f"{obs_sev + ' ' if obs_sev else ''}obstruction")
        if fvc["flag"] == "low" and have_tlc:
            add(s_syn, "Obstruction; the low FVC is air trapping, not restriction "
                       "(TLC not reduced)")
        elif fvc["flag"] == "low":
            add(s_syn, "Obstruction with low FVC — concurrent restriction not excluded "
                       "without TLC")
        else:
            add(s_syn, f"{(obs_sev or '').capitalize()} obstructive defect".strip())
    elif restriction:
        head.append(f"{res_sev + ' ' if res_sev else ''}"
                    f"{'complex ' if complex_restriction else ''}restriction")
        add(s_syn, f"{(res_sev or '').capitalize()} "
                   f"{'complex ' if complex_restriction else ''}restrictive defect "
                   "(low TLC, ratio preserved)".strip())
    elif ratio["flag"] == "normal" and (fvc["flag"] == "low" or fev1["flag"] == "low"):
        if tlc["flag"] == "normal":
            head.append("non-specific pattern")
            add(s_syn, "Low FVC/FEV1 with normal ratio and normal TLC → non-specific pattern",
                note="Seen with obesity, early or small-airway obstruction, and poor "
                     "effort; a proportion evolve to obstruction or restriction.")
        else:
            head.append("preserved-ratio impaired spirometry (PRISm)")
            add(s_syn, "Low FEV1 or FVC with preserved ratio → PRISm — restriction "
                       "and a non-specific pattern look alike without TLC")
    elif have_spiro and ratio["flag"] == "normal" and fvc["flag"] in ("normal", None) \
            and fev1["flag"] in ("normal", None) and tlc["flag"] in ("normal", "high", None):
        head.append("normal ventilatory function" if have_tlc else "normal spirometry")
        add(s_syn, "No obstruction or restriction")

    if hyperinflation:
        head.append("hyperinflation")
    if air_trapping:
        head.append("air trapping")
    if vc_unmasked:
        add(s_syn, "Obstruction seen only on FEV1/IVC — mild or early airflow obstruction",
            level=1)
    if bdr_positive:
        head.append("significant bronchodilator response")

    if dl_flag == "low":
        head.append(f"{_ADVERB.get(dl_sev, '')}reduced gas transfer"
                    + (" (Hb-adjusted)" if dladj["flag"] is not None else ""))
    elif dl_flag == "high":
        head.append("elevated DLCO")
    elif dl_flag == "normal":
        head.append("normal DLCO" + (" (Hb-adjusted)" if dladj["flag"] is not None else ""))

    # Gas-transfer pattern × ventilatory pattern → diagnostic category.
    if dl_flag is not None:
        if obstruction and dl_flag == "low":
            add(s_syn, "Obstruction with reduced DLCO → emphysema pattern")
            diff.append("Obstruction + low DLCO: emphysema (COPD); also obstruction "
                        "with coexisting ILD or pulmonary vascular disease.")
        elif obstruction:
            add(s_syn, "Obstruction with preserved DLCO → airway-predominant disease")
            diff.append("Obstruction + normal/high DLCO: asthma, chronic bronchitis, "
                        "bronchiectasis, bronchiolitis obliterans.")
        elif restriction and (dl_flag == "low" and not extraparenchymal_dl):
            add(s_syn, "Restriction with reduced DLCO → parenchymal (interstitial) pattern")
            diff.append("Restriction + low DLCO: interstitial lung disease (IPF, "
                        "CTD-ILD, hypersensitivity pneumonitis, sarcoidosis, drug), "
                        "pneumonitis, pulmonary edema.")
        elif restriction:
            add(s_syn, "Restriction with preserved gas transfer per unit volume → "
                       "extraparenchymal pattern")
            diff.append("Restriction + preserved KCO/DLCO: obesity, neuromuscular "
                        "weakness, chest wall disease (kyphoscoliosis), pleural "
                        "disease, prior resection.")
            nxt.append("MIP/MEP (respiratory muscle strength) and BMI")
        elif (dl_flag == "low" and ratio["flag"] == "normal"
              and fvc["flag"] != "low" and fev1["flag"] != "low"):
            add(s_syn, "Isolated reduction in DLCO (normal mechanics)")
            diff.append("Isolated low DLCO: pulmonary vascular disease (CTEPH, PAH), "
                        "early ILD, emphysema with preserved spirometry, combined "
                        "pulmonary fibrosis and emphysema, "
                        + ("anemia (DLCO not Hb-adjusted), " if dladj["flag"] is None else "")
                        + "elevated carboxyhemoglobin.")
            nxt.append("chest CT and echocardiography to separate parenchymal from "
                       "vascular causes")
        if dl_flag == "high":
            diff.append("High DLCO: polycythemia, alveolar hemorrhage, asthma, obesity, "
                        "left-to-right shunt.")
    elif (obstruction or restriction or fvc["flag"] == "low") and not any(
            R[k]["flag"] or R[k]["meas"] for k in ("dlco", "dlco_adj")):
        nxt.append("DLCO, to split parenchymal from airway or extraparenchymal causes")

    if uao:
        head.append({"extrathoracic": "variable extrathoracic",
                     "intrathoracic": "variable intrathoracic",
                     "fixed": "fixed"}[uao] + " upper airway obstruction")
        add(s_syn, "Flow-volume pattern of upper airway obstruction")
        diff.append(_UAO_DIFF[uao])

    if any_fallback:
        nxt.append("the report's LLN or z-scores (some rows used fixed cutoffs)")

    sections = [
        {"title": "Spirometry", "steps": s_spi},
        {"title": "Lung volumes", "steps": s_vol},
        {"title": "Diffusion", "steps": s_dl},
        {"title": "Flow-volume loop", "steps": s_loop},
        {"title": "Putting it together", "steps": s_syn},
    ]
    if head:
        headline = head[0][0].upper() + head[0][1:]
        if len(head) > 1:
            headline += " · " + " · ".join(head[1:])
        headline += "."
    else:
        headline = "Enter FEV1, FVC (or the ratio), TLC or DLCO to classify the pattern."
    return {
        "headline": headline,
        "sections": sections,
        "differential": diff,
        "warnings": warnings,
        "next": ("Would sharpen the read: " + "; ".join(dict.fromkeys(nxt)) + ".")
                if nxt else None,
    }
