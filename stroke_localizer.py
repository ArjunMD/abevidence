"""Exam findings → infarct location, for the Tools page (Neuro tab).

Pure scoring — no AI, no network. The inverse of "lesion here → expect this
deficit": the clinician records what the exam showed and the engine ranks the
lesion sites whose classic picture fits.

Every finding is recorded as one of
  None       not examined / not recorded — contributes nothing
  "L", "R"   present, on that side (what "side" means is defined per finding
             in stroke_localizer_data.FINDINGS — side of the weak limb, the
             lost visual field, the direction of gaze deviation, ...)
  "B"        present bilaterally
  "present"  present, for findings that have no side (aphasia, dysarthria)
  "absent"   examined and normal — a documented negative

Each location in stroke_localizer_data.LOCATIONS lists the findings it
expects and the findings that argue against it, each with a weight (3
defining, 2 typical, 1 variable) and a side rule relative to the lesion
("contra", "ipsi", "either", "bilateral", "na"). For every location the
engine hypothesizes a lesion side (left, right — or the fixed side for a
dominant / nondominant site, or midline for bilateral syndromes) and scores:

  expected finding present, side consistent with the rule    + weight
  expected finding bilateral where one side was expected     + weight / 2
  expected finding present on the wrong side                 − weight
  expected finding documented absent                         − weight / 2
  "against" finding present                                  − weight
  finding in absence_supports documented absent              + 1 each, at
       most +2, and only once something positive matched — negatives sharpen
       a candidate, they never create one

The better lesion side wins. Locations are ranked by score, then by how much
of their classic picture was matched. Output follows the acid_base / pft
step shape ({"text", "calc", "note", "level"}) so page_tools._render_steps
draws it: one step per candidate site, the evidence beneath it, the
mechanism in the hover note, then the conclusion, what to examine next, and
the remaining differential.
"""

from stroke_localizer_data import FINDINGS, LOCATIONS

PRESENT = ("L", "R", "B", "present")
ABSENT_PENALTY = 0.5      # expected finding examined and absent → −weight × this
BILATERAL_CREDIT = 0.5    # bilateral finding where the site predicts one side
NEGATIVE_BONUS = 1.0      # discriminating negative documented → + this ...
NEGATIVE_CAP = 2.0        # ... up to this much per site
TOP_N = 5                 # candidates shown as steps; the rest go to the differential
MIN_SCORE = 1.0           # below this a site is not worth listing
MIN_MATCHED = 3.0         # nor is one that matched only variable (weight 1–2) findings

_FINDING = {f["id"]: f for f in FINDINGS}
_OPPOSITE = {"L": "R", "R": "L"}
_SIDE_WORD = {"L": "Left", "R": "Right", "M": "Bilateral / midline"}
# Names start with anatomy ("Precentral gyrus…") that reads naturally in
# lower case after a side word; these first words don't.
_KEEP_CASE = {
    "Broca", "Wernicke", "Dejerine", "Heubner", "Meyer", "Marie", "Millard", "Foville",
    "Claude", "Weber", "Benedikt", "Wallenberg", "Parinaud", "Balint", "Anton", "Gerstmann",
    "Opalski", "Avellis", "Jackson", "Babinski", "Percheron", "Caplan", "Bell", "Raymond",
    "Nothnagel", "Schmidt", "Fisher", "Beck", "Horner", "Foix", "Saturday",
}
_STRIP_PREFIX = ("Dominant ", "Nondominant ", "Left ", "Right ")


def finding_label(fid: str) -> str:
    return _FINDING.get(fid, {}).get("label", fid)


def _describe(fid: str, value) -> str:
    """'left arm weakness' style phrase for an entered finding."""
    label = finding_label(fid)
    if value == "B":
        return f"bilateral {label.lower()}"
    if value in ("L", "R"):
        return f"{_SIDE_WORD[value].lower()} {label.lower()}"
    return label.lower()


def _fit(rule: str, lesion_side: str, value: str) -> float:
    """How well a present finding's recorded side fits this side rule for a
    lesion on lesion_side: 1 fits, 0 is the wrong side, BILATERAL_CREDIT for
    a bilateral finding where one side was predicted (the expected side is
    included, but a unilateral site doesn't explain the other). Non-
    lateralized entries and midline sites always fit."""
    if rule in ("na", "either") or value == "present" or lesion_side == "M":
        return 1.0
    if rule == "bilateral":
        return 1.0 if value == "B" else 0.0
    if value == "B":
        return BILATERAL_CREDIT
    if rule == "contra":
        return 1.0 if value == _OPPOSITE[lesion_side] else 0.0
    if rule == "ipsi":
        return 1.0 if value == lesion_side else 0.0
    return 1.0


def _candidate_sides(hemisphere: str) -> list[str]:
    if hemisphere == "dominant":
        return ["L"]
    if hemisphere == "nondominant":
        return ["R"]
    if hemisphere == "midline_or_bilateral":
        return ["M"]
    return ["L", "R"]


def _score(loc: dict, entered: dict, lesion_side: str) -> dict:
    score = 0.0
    matched_weight = 0
    total_expected = 0
    supports, wrong_side, missing, against, negatives = [], [], [], [], []

    for f in loc["findings"]:
        fid, role, w, rule = f["id"], f["role"], f["weight"], f["side"]
        value = entered.get(fid)
        if role == "expected":
            total_expected += w
        if value is None:
            continue
        present = value in PRESENT
        if role == "expected":
            if not present:
                score -= w * ABSENT_PENALTY
                missing.append(finding_label(fid).lower())
            else:
                fit = _fit(rule, lesion_side, value)
                if fit:
                    score += w * fit
                    matched_weight += w * fit
                    supports.append(_describe(fid, value))
                else:
                    score -= w
                    wrong_side.append(_describe(fid, value))
        elif present:
            score -= w
            against.append(_describe(fid, value))

    if supports:
        for fid in loc.get("absence_supports", []):
            if entered.get(fid) == "absent":
                negatives.append(finding_label(fid).lower())
        score += min(NEGATIVE_CAP, NEGATIVE_BONUS * len(negatives))

    # A dominant / nondominant site has a side by definition; anything else
    # needs a lateralized finding to name one.
    side_known = lesion_side == "M" or loc["hemisphere"] in ("dominant", "nondominant") or any(
        entered.get(f["id"]) in ("L", "R")
        for f in loc["findings"] if f["side"] in ("contra", "ipsi")
    )
    return {
        "score": score,
        "matched": matched_weight,
        "coverage": matched_weight / total_expected if total_expected else 0.0,
        "side": lesion_side if side_known else None,
        "supports": supports, "wrong_side": wrong_side, "missing": missing,
        "against": against, "negatives": negatives,
    }


def _best(loc: dict, entered: dict) -> dict:
    runs = [_score(loc, entered, s) for s in _candidate_sides(loc["hemisphere"])]
    runs.sort(key=lambda r: (r["score"], r["coverage"]), reverse=True)
    best = dict(runs[0])
    # Two sides tying means nothing lateralized was entered — say so rather
    # than pick one.
    if len(runs) > 1 and runs[0]["score"] == runs[1]["score"]:
        best["side"] = None
    best["loc"] = loc
    return best


def _site_name(r: dict) -> str:
    loc = r["loc"]
    side = r["side"]
    name = loc["name"]
    if side in ("L", "R") and loc["hemisphere"] != "midline_or_bilateral":
        for p in _STRIP_PREFIX:          # the side word replaces these
            if name.startswith(p):
                name = name[len(p):]
        first = name.split(" ", 1)[0].rstrip(",:")
        if first not in _KEEP_CASE and first[1:].islower():
            name = name[0].lower() + name[1:]
        name = f"{_SIDE_WORD[side]} {name}"
        if loc["hemisphere"] in ("dominant", "nondominant") and "dominant" not in name.lower():
            name += f" ({loc['hemisphere']})"
    if loc.get("eponym"):
        name += f" — {loc['eponym']}"
    return name


def _fmt_score(x: float) -> str:
    return f"{x:+.0f}" if float(x).is_integer() else f"{x:+.1f}"


def _evidence(r: dict) -> str:
    lines = []
    if r["supports"]:
        lines.append("For: " + ", ".join(r["supports"]))
    if r["negatives"]:
        lines.append("Documented negatives that fit: " + ", ".join(r["negatives"]))
    if r["wrong_side"]:
        lines.append("Wrong side for this site: " + ", ".join(r["wrong_side"]))
    if r["against"]:
        lines.append("Against: " + ", ".join(r["against"]))
    if r["missing"]:
        lines.append("Expected but absent: " + ", ".join(r["missing"]))
    return "\n".join(lines)


def localize(entered: dict) -> dict:
    """entered: finding id → None | "L" | "R" | "B" | "present" | "absent"."""
    entered = {k: v for k, v in entered.items() if v is not None}
    n_present = sum(1 for v in entered.values() if v in PRESENT)

    ranked = sorted(
        (_best(loc, entered) for loc in LOCATIONS),
        key=lambda r: (r["score"], r["coverage"]),
        reverse=True,
    )
    fits = [r for r in ranked if r["score"] >= MIN_SCORE and r["matched"] >= MIN_MATCHED]

    warnings = []
    if not n_present:
        warnings.append("Only negatives entered — record at least one abnormal "
                        "finding to localize.")

    steps = []
    for r in fits[:TOP_N]:
        loc = r["loc"]
        text = (f"<b>{_site_name(r)}</b> — {loc['territory']} · "
                f"score {_fmt_score(r['score'])}, "
                f"{round(r['coverage'] * 100)}% of the classic picture")
        steps.append({"text": text, "calc": _evidence(r),
                      "note": loc.get("note", ""), "level": 0})
        if loc.get("discriminate"):
            steps.append({"text": f"To separate from its neighbours: {loc['discriminate']}",
                          "level": 1})

    if fits:
        top = fits[0]
        headline = f"{_site_name(top)} — {top['loc']['territory']}."
        if len(fits) > 1 and fits[1]["score"] == top["score"]:
            headline += (f" Ties with {_site_name(fits[1])}; the discriminators "
                         f"above decide.")
        elif len(fits) > 1:
            headline += f" Next best: {_site_name(fits[1])}."
    else:
        headline = ("No infarct site fits what was entered" +
                    (" — the pattern may not be a single brain lesion." if n_present else "."))

    differential = [
        f"{_site_name(r)} — {r['loc']['territory']} ({_fmt_score(r['score'])})"
        for r in fits[TOP_N:TOP_N + 8]
    ]

    return {
        "warnings": warnings,
        "sections": [{"title": "Candidate infarct sites, best fit first" if steps else "",
                      "steps": steps}],
        "headline": headline,
        # Each candidate carries its own "to separate from its neighbours"
        # line, so nothing extra after the conclusion.
        "next": "",
        "differential": differential,
        "summary": headline,
    }
