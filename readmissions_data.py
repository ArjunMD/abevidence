"""Curated literature base for the Readmissions page (ui_pages/page_value_based_care.py).

Hand-edited. Structure: sections → questions → answers, where each answer is a
paper. A question can have several answering papers; list them newest first.

Section:  {"title": str, "intro": str (optional markdown), "questions": [Question]}
Question: {"q": str, "answers": [Answer]}
Answer:   {
    "pmid": str,          # PubMed ID ("" if none, then give "url")
    "url": str,           # optional; defaults to the PubMed page for pmid
    "citation": str,      # e.g. "Smith J, et al. JAMA 2021"
    "title": str,         # paper title
    "design": str,        # e.g. "RCT, N=1,200" / "Retrospective cohort, N=45,000"
    "answer": str,        # the one-to-two sentence answer to the question, from this paper
    "details": str,       # optional markdown bullets: key numbers, caveats
}
"""

_AUERBACH_2016 = {
    "pmid": "26954564",
    "citation": "Auerbach AD, et al. JAMA Intern Med 2016 (HOMERuN)",
    "title": "Preventability and Causes of Readmissions in a National Cohort of General Medicine Patients",
    "design": "Observational, 12 US academic centers, N=1,000 readmitted general medicine patients",
}

_SHAH_2016 = {
    "pmid": "27167208",
    "citation": "Shah T, et al. Chest 2016",
    "title": "COPD Readmissions: Addressing COPD in the Era of Value-based Health Care",
    "design": "Narrative review",
}

_CHOW_2023 = {
    "pmid": "",
    "url": "https://doi.org/10.2147/COPD.S418295",
    "citation": "Chow R, et al. Int J Chron Obstruct Pulmon Dis 2023",
    "title": "Predictors of Readmission, for Patients with Chronic Obstructive Pulmonary Disease (COPD) – A Systematic Review",
    "design": "Systematic review, 242 studies, N≈16.5 million",
}

SECTIONS: list[dict] = [
    {
        "title": "The HRRP",
        "questions": [
            {
                "q": "What are the concerns and unintended consequences of the HRRP?",
                "answers": [
                    {
                        **_SHAH_2016,
                        "answer": (
                            "Safety-net hospitals are penalized more, hospitals can avoid penalties "
                            "by shifting returns to observation or the ED, and it's unclear whether "
                            "lower 30-day readmissions mean better patient outcomes."
                        ),
                        "details": (
                            "- **Safety-net penalties:** hospitals caring for low-income patients were "
                            "penalized more in early HRRP years. Dual-eligible patients are ~2× the "
                            "national average among Medicare COPD admissions and have independently "
                            "higher readmission risk\n"
                            "- **Gaming:** observation stays count as outpatient and are exempt, so "
                            "returns can be treated in observation. Hospitals could also code "
                            "discharges as other conditions, divert patients elsewhere, or delay "
                            "appropriate readmissions\n"
                            "- **Readmission ≠ quality:** in HF, higher 30-day readmission rates have "
                            "been associated with *lower* mortality\n"
                            "- **Costs fall on the discharging hospital:** e.g., the patient can't "
                            "afford inhalers after discharge, but the insurer and pharmacy plan bear none "
                            "of the penalty\n"
                            "- *Since publication:* starting FY2019, CMS compares hospitals within "
                            "peer groups based on their share of dual-eligible patients (21st Century Cures Act)"
                        ),
                    },
                ],
            },
        ],
    },
    {
        "title": "How Many Readmissions Are Preventable?",
        "questions": [
            {
                "q": "What proportion of 30-day readmissions are preventable?",
                "answers": [
                    {
                        **_AUERBACH_2016,
                        "answer": (
                            "About one-quarter (26.9%). Two physicians reviewed each case using patient "
                            "interviews, physician surveys, and the chart."
                        ),
                        "details": (
                            "- \"Preventable\" = ≥50% likelihood on a 6-point scale, judged against an "
                            "\"ideal health system\" (e.g., if the patient couldn't get a follow-up slot, "
                            "that counts as preventable)\n"
                            "- Spread: no evidence 28.6%, slight 29.7%, <50-50 close call 14.8%, "
                            "≥50-50 close call 11.9%, strong 12.8%, virtually certain 2.2%\n"
                            "- Only ~15% had strong or near-certain preventability, so most "
                            "\"preventable\" cases were close calls\n"
                            "- Limits: subjective ratings, no interrater reliability, mostly large "
                            "academic centers, English speakers only"
                        ),
                    },
                ],
            },
            {
                "q": "Where would intervention have prevented the readmission?",
                "answers": [
                    {
                        **_AUERBACH_2016,
                        "answer": (
                            "About half (52%) of preventable readmissions could have been prevented "
                            "during the index admission, so the inpatient stay is the biggest target."
                        ),
                        "details": (
                            "Among the 269 preventable readmissions:\n\n"
                            "| Where intervention would have been most effective | % |\n"
                            "| --- | --- |\n"
                            "| Index admission | 52.0 |\n"
                            "| At home after discharge | 17.5 |\n"
                            "| Outpatient clinic | 14.1 |\n"
                            "| Emergency department | 5.9 |\n"
                            "| Multiple locations | 10.4 |"
                        ),
                    },
                ],
            },
        ],
    },
    {
        "title": "Causes of Preventable Readmissions",
        "questions": [
            {
                "q": "What drives preventable readmissions, and which should we prioritize?",
                "answers": [
                    {
                        **_AUERBACH_2016,
                        "answer": (
                            "The factors most often behind preventable readmissions were ED decisions to "
                            "readmit patients who may not have needed a bed (9.0%), premature discharge (8.7%), "
                            "missed post-discharge appointments (8.3%), and patients not knowing whom to "
                            "contact after discharge (6.2%). Poor handoff to outpatient clinicians and "
                            "missing goals-of-care discussions in serious illness had strong associations "
                            "but were less common."
                        ),
                        "details": (
                            "Factors independently associated with preventability (multivariable). "
                            "\"% affected\" = estimated share of preventable readmissions attributable "
                            "to the factor, a best-case prioritization estimate:\n\n"
                            "| Factor | aOR (95% CI) | % affected |\n"
                            "| --- | --- | --- |\n"
                            "| ED admitted a patient who may not have needed inpatient stay | 9.13 (5.23–15.95) | 9.0 |\n"
                            "| Discharged too soon (e.g., dyspnea, not eating) | 3.88 (2.44–6.17) | 8.7 |\n"
                            "| Unable to keep post-discharge appointments | 3.01 (1.75–5.18) | 8.3 |\n"
                            "| Didn't know whom to contact / when to go to ED | 2.33 (1.64–3.30) | 6.2 |\n"
                            "| Lack of disease monitoring (e.g., daily weights) | 1.75 (1.37–2.24) | 5.6 |\n"
                            "| Important info not relayed to outpatient clinicians | 4.19 (2.17–8.09) | 5.4 |\n"
                            "| Inadequate monitoring for med adverse effects / nonadherence | 2.41 (1.18–4.90) | 5.1 |\n"
                            "| Wrong discharge location (e.g., home vs SNF) | 2.50 (1.24–5.04) | 5.0 |\n"
                            "| End-stage illness, no documented goals-of-care discussion | 3.84 (1.39–10.64) | 4.8 |\n"
                            "| Missed diagnosis at index admission | 2.34 (1.26–4.34) | 4.0 |\n"
                            "| Inadequate pain treatment at index admission | 3.03 (1.22–7.57) | 2.9 |\n"
                            "| Near end of life but wants full treatment (protective) | 0.24 (0.10–0.57) | −4.7 |\n\n"
                            "- Authors frame the ED finding as a system gap, not an ED failure: "
                            "PCP–hospitalist–ED communication about admission criteria and community "
                            "resources, plus better urgent-care access\n"
                            "- Associations only; the paper can't show that fixing these factors "
                            "reduces readmissions"
                        ),
                    },
                ],
            },
            {
                "q": "Do patient-experience scores or functional status identify preventable readmissions?",
                "answers": [
                    {
                        **_AUERBACH_2016,
                        "answer": (
                            "No. Patient-reported care experience and satisfaction were similar in "
                            "preventable and nonpreventable readmissions, and functional status did not "
                            "predict preventability, so neither is a good way to set program priorities."
                        ),
                        "details": (
                            "- Similar in both groups: enough time to talk, preferences considered, "
                            "understood self-care (89% vs 91%)\n"
                            "- One patient report did differ: not knowing how to contact their doctor "
                            "after discharge (18.6% vs 12.6%, P=.02)\n"
                            "- Patient-reported drug/alcohol problems were *less* common in preventable "
                            "readmissions (4.5% vs 8.1%)\n"
                            "- Functional status is a known risk factor for readmission in general, but "
                            "didn't separate preventable from nonpreventable here"
                        ),
                    },
                ],
            },
        ],
    },
    {
        "title": "COPD",
        "intro": (
            "About 1 in 5 patients hospitalized for a COPD exacerbation is readmitted within 30 days "
            "(~22% in Medicare). COPD joined the HRRP in FY2015; the measure counts **all-cause** "
            "30-day readmissions."
        ),
        "questions": [
            {
                "q": "Can we identify HRRP COPD patients while they're still in the hospital?",
                "answers": [
                    {
                        **_SHAH_2016,
                        "answer": (
                            "Not reliably. The HRRP cohort is defined by discharge billing codes "
                            "assigned after the patient leaves, and billing codes and clinician "
                            "diagnoses of COPD exacerbation disagree substantially. Programs either "
                            "miss patients or have to treat a broader group."
                        ),
                        "details": (
                            "- ICD-9 algorithms had only 12–25% sensitivity against chart review for "
                            "clinician-identified exacerbations\n"
                            "- Only ~26% of readmissions after a COPD admission are for COPD itself; "
                            "~50% are respiratory. The penalty counts all causes, so a COPD-only "
                            "program misses most of them\n"
                            "- Watch for studies measuring readmission over long windows (up to 2 yr) "
                            "or COPD-only readmissions; their results may not apply to the 30-day, "
                            "all-cause HRRP measure"
                        ),
                    },
                ],
            },
            {
                "q": "Which COPD patients are at highest risk of readmission?",
                "answers": [
                    {
                        **_CHOW_2023,
                        "answer": (
                            "Across 242 studies, the most consistent predictors were prior "
                            "hospitalization, male sex, older age, poor functional status, heart "
                            "failure, mental health conditions, and a high comorbidity burden. Other "
                            "predictors were long-term oxygen use, longer length of stay, NIV, "
                            "intubation or ICU stay, anemia, lower FEV1, and discharge to a SNF or "
                            "long-term care."
                        ),
                        "details": (
                            "The review found 64 significant predictors of all-cause readmission and "
                            "23 of COPD-related readmission (1 month to 1 year):\n\n"
                            "| Domain | Most frequently reported predictors |\n"
                            "| --- | --- |\n"
                            "| Patient | Prior hospitalization, male sex, older age, poor performance status/ADLs; also COPD severity, alcohol or drug use, malnutrition, prior CAP |\n"
                            "| Comorbidities | HF, mental health, higher Charlson/number of comorbidities, diabetes, CKD, cancer |\n"
                            "| Pre-admission meds | Long-term oxygen |\n"
                            "| Hospital course | Length of stay, NIV, intubation, ICU admission, systemic steroids (likely a marker of severity) |\n"
                            "| Labs/tests | Lower FEV1, anemia; eosinophil count (inconsistent direction across studies) |\n"
                            "| Discharge | SNF/long-term care, home oxygen |\n\n"
                            "- For **COPD-specific** readmission: older age, prior hospitalization, "
                            "mental health, diabetes, Charlson/Elixhauser, cancer, length of stay, "
                            "eosinophils, home O2\n"
                            "- Limits: only significant predictors were extracted, so it's unknown how "
                            "often each was tested and found null. Some patients carried a "
                            "\"COPD\" label without spirometry confirmation. 38% of studies were "
                            "from the US"
                        ),
                    },
                    {
                        **_SHAH_2016,
                        "answer": (
                            "Readmission risk rises with the number of comorbidities, especially HF, "
                            "frailty, and depression/anxiety. Other flags are hospitalization in the "
                            "prior year, discharge to a SNF or home health, dual eligibility, long "
                            "length of stay or ICU use, and hypercapnia. No validated real-time model "
                            "exists for use during admission."
                        ),
                        "details": (
                            "- **Comorbidities are the rule:** 30% of patients admitted for an "
                            "exacerbation have ≥4 comorbidities. HF is the 3rd most common cause of "
                            "readmission and is likely underdiagnosed\n"
                            "- **Psychiatric:** depression, anxiety, psychosis, and alcohol or drug "
                            "use each independently raise early all-cause readmission risk\n"
                            "- **Frailty:** 4-m gait speed and quadriceps ultrasound predicted "
                            "readmission at 90 days and 1 year, respectively\n"
                            "- **Other ORs:** prior-year hospitalization 2.48; SNF 1.42, home health "
                            "1.36; male sex 1.06; Black race 1.13 (inconsistent across studies); also "
                            "home O2 and low BMI\n"
                            "- **Hypercapnia:** 18% of patients in a European audit had no ABG on "
                            "admission. Finding respiratory acidosis identifies patients for NIV and "
                            "higher-intensity care\n"
                            "- **Prediction models:** C-statistics 0.71–0.82, but they rely on data "
                            "that isn't available during the admission"
                        ),
                    },
                ],
            },
            {
                "q": "Is there a validated risk score for COPD readmission?",
                "answers": [
                    {
                        **_CHOW_2023,
                        "answer": (
                            "Six scores predict all-cause readmission (CODEX, BODEX, DOSE, PEARL, "
                            "CORE, RACE), but all are only modestly accurate (AUC ~0.70–0.72). The "
                            "authors suggest richer EHR-based models that use in-hospital and "
                            "discharge data may do better."
                        ),
                        "details": (
                            "| Score | Components | Validated for |\n"
                            "| --- | --- | --- |\n"
                            "| CODEX | Comorbidity, FEV1%, mMRC dyspnea, prior severe exacerbations | 2–3 mo and 6–12 mo |\n"
                            "| BODEX | BMI, FEV1%, mMRC dyspnea, prior severe exacerbations | 2–3 mo |\n"
                            "| DOSE | Dyspnea, obstruction, smoking, exacerbations | 2–3 mo |\n"
                            "| PEARL | Previous admissions, eMRC dyspnea, age, right/left HF | Time to readmission |\n"
                            "| CORE | Includes prior exacerbations, lung function, eosinophil count | Time to readmission |\n"
                            "| RACE | Age, sex, income, race, payer, comorbidities | Time to readmission |\n\n"
                            "- None was built on the 30-day, all-cause HRRP window specifically\n"
                            "- None includes hospital-course or discharge variables such as LOS, "
                            "NIV/ICU, or disposition, even though those predict readmission"
                        ),
                    },
                ],
            },
            {
                "q": "Which interventions reduce readmissions after a COPD exacerbation?",
                "answers": [
                    {
                        **_SHAH_2016,
                        "answer": (
                            "The best evidence supports self-management education, teach-to-goal "
                            "inhaler training, and early follow-up (within 30 days, ideally the first "
                            "week). Dispensing inhalers before discharge, pharmacist med rec, "
                            "supervised pulmonary rehab, telehealth, roflumilast, and hospital-at-home "
                            "look promising."
                        ),
                        "details": (
                            "**Supported**\n"
                            "- Self-management (Cochrane): fewer respiratory and all-cause readmissions\n"
                            "- Inhaler teach-to-goal vs brief verbal instructions (RCT): 8× less likely "
                            "to have an ED visit, readmission, or death within 30 days. Up to 86% of "
                            "patients misuse inhalers\n"
                            "- Early follow-up with a known PCP or pulmonologist within 30 days lowers "
                            "ED visits and readmissions (Medicare cohort). About 1/3 of 30-day "
                            "readmissions happen in week 1. Authors argue for earlier follow-up than "
                            "GOLD's 4–6 weeks\n\n"
                            "**Emerging**\n"
                            "- Meds in hand: pharmacy dispensing inhalers plus teaching before "
                            "discharge cut 30-day readmissions from 21.4% to 8.7% (pre–post study)\n"
                            "- Pulmonary rehab after discharge: fewer COPD readmissions over 3–9 mo "
                            "(Cochrane). One unsupervised program started within 48 h showed "
                            "increased mortality, so rehab should be supervised\n"
                            "- Telehealth: 1-yr hospitalization OR 0.46, ED OR 0.27, but programs vary widely\n"
                            "- Roflumilast: lower 30-day readmission (propensity-matched, retrospective)\n"
                            "- Hospital-at-home for selected ED patients: readmission RR 0.77 (Cochrane)\n\n"
                            "**Not shown to help 30-day readmission:** azithromycin (reduces "
                            "exacerbations over 1 yr, not tested at 30 days), simvastatin"
                        ),
                    },
                ],
            },
            {
                "q": "Do multicomponent COPD care bundles or disease-management programs reduce readmissions?",
                "answers": [
                    {
                        **_CHOW_2023,
                        "answer": (
                            "Mostly no. Of 89 intervention studies (57 observational, 32 RCTs), most "
                            "found no significant reduction in readmission. A COPD-specific care "
                            "package was the most notable exception."
                        ),
                        "details": (
                            "- The intervention results are reported only in the supplementary "
                            "tables and weren't pooled\n"
                            "- The review excluded telemonitoring and home-care studies"
                        ),
                    },
                    {
                        **_SHAH_2016,
                        "answer": (
                            "Mixed and mostly negative for 30-day readmissions. Some programs cut "
                            "1-year hospitalizations, but England's national discharge bundle had no "
                            "effect on 28-day readmissions. One VA care-management RCT was stopped "
                            "early for higher mortality in the intervention arm."
                        ),
                        "details": (
                            "- Bourbeau: 2-month education plus nurse/RT access, ~40% fewer COPD "
                            "admissions and ED visits over 1 yr\n"
                            "- Rice: single education session plus monthly case-manager calls, 28% "
                            "fewer all-cause hospitalizations over 1 yr\n"
                            "- Fan (VA RCT): similar program, stopped for excess mortality\n"
                            "- Two transition programs (community hospital; inner-city with home "
                            "visits to 90 days): no change in 30- or 90-day readmissions, but "
                            "*lower mortality*\n"
                            "- A pre-HRRP systematic review found no RCT targeting 30-day readmission "
                            "at all\n"
                            "- Bundles may suit complex patients with multiple comorbidities long term, "
                            "but there's no clear evidence they reduce early readmissions"
                        ),
                    },
                ],
            },
        ],
    },
]
