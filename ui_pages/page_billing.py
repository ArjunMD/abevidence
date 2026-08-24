"""Static inpatient-billing Q&A reference. No AI, no DB — just answers behind
expanders. Add a question by appending to _QA."""

import streamlit as st

# (question, markdown answer). Answers are plain markdown bullets; indent a
# sub-bullet by three spaces.
_QA: list[tuple[str, str]] = [
    (
        "What is the Medicare 2-midnight rule?",
        """
- **One liner** — The Two-Midnight Rule remains CMS's central framework for deciding
  inpatient (Part A) vs. outpatient/observation (Part B) payment.
- **The core rule** — In effect since October 1, 2013. If the admitting physician
  reasonably expects the patient to need hospital care spanning at least two midnights,
  and the record supports it, the stay is generally appropriate for Part A. The
  documented expectation at the time of decision is what counts, not the retrospective
  actual length of stay.
- **Benchmark vs. presumption (two distinct pieces)** — The rule contains two mechanisms
  that do different jobs and count midnights differently:
   - **Benchmark** = the bedside decision tool: "Should this be inpatient?" Counts from
     the initiation of care, including pre-order ED/observation time, toward your
     two-midnight expectation. Guides the admission decision.
   - **Presumption** = an audit-selection safe harbor aimed at reviewers (MACs, RACs):
     "Should auditors leave this claim alone?" Counts only midnights after the inpatient
     admission order — pre-order ED/observation time does not count. A stay spanning two+
     midnights after the order is presumed appropriate for Part A and shouldn't be
     targeted for status second-guessing, absent evidence of gaming.
   - So a patient with one observation midnight + one inpatient midnight meets the
     benchmark (correct inpatient decision) but falls outside the presumption (still
     reviewable) — not a contradiction; if reviewed, it should be upheld. Practical
     upshot: place the inpatient order promptly once the two-midnight expectation is
     clear — pre-order midnights count for the benchmark but not your audit protection.
- **Unforeseen-circumstances carve-out** — A reasonable, documented two-midnight
  expectation still qualifies for Part A even if the actual stay was shorter due to
  death, transfer, rapid improvement, or leaving AMA.
- **2016 case-by-case exception** — A physician can admit as inpatient for an expected
  sub-two-midnight stay when documentation justifies inpatient-level care (a
  discretionary escape hatch on the short-stay side).
- **Medicare Advantage now bound (since 2024)** — MA plans must follow the two-midnight
  rule, but the presumption (the audit-protection safe harbor) does not apply to them.
  They can review stays of any length — even ones several midnights past the order that
  would be untouchable under traditional Medicare — which is the mechanism behind
  persistent MA short-stay denials and observation downgrades.
- **Inpatient-Only (IPO) list and its phase-out** — Created in 2000, the IPO list is CMS's
  annual catalog of surgical/interventional procedures (HCPCS codes) it considers too
  complex, high-risk, or resource-intensive to be safely done outpatient (~1,700+
  procedures as of 2025). If a procedure is on the list, Medicare pays for it only when
  performed inpatient and covers it automatically under Part A — regardless of expected
  length of stay, so the Two-Midnight Rule doesn't apply to it; bill it as outpatient and
  Medicare denies the claim. CMS has tried to unwind the list before (total knee
  arthroplasty removed 2018, total hip 2020; a 2020 plan to eliminate it was reversed by
  the Biden administration in 2022), but the CY 2026 OPPS final rule now finalizes full
  elimination by January 1, 2028, starting January 1, 2026 with ~285 musculoskeletal
  procedures moved off (and the ASC-payable list expanded in parallel). Two consequences:
  (1) procedures removed from the IPO list are temporarily exempt from Two-Midnight
  medical review until CMS judges them commonly done outpatient; and (2) as the list
  shrinks, more procedures fall under Two-Midnight logic — and expect payers, especially
  MA and commercial, to push newly-removed codes toward outpatient/observation billing
  and deny inpatient claims lacking strong medical-necessity documentation.
- **2026 dollar stakes** — Part A inpatient deductible $1,736 (covers up to 60 days);
  Part B deductible $283 plus 20% coinsurance on physician services. The
  inpatient-vs-observation call directly determines which cost structure hits the
  patient.
""",
    ),
    (
        "Social Security",
        """
- **Relevance** — People already drawing from SS are automatically enrolled in Medicare
  Part A and Part B (opt-out). So here is a brief overview.
- **Eligibility — the 40-credit rule** — Must have worked 40 quarters (10 years) and paid
  into social security. A spouse's work can count.
- **Claiming at FRA** — FRA (full retirement age) is currently 67:
   - **What you get** — Claiming at FRA pays 100% of your benefit — your full Primary
     Insurance Amount (PIA), with no reduction.
   - **How the PIA is set** — It's based on your highest 35 years of earnings, indexed for
     wage inflation and averaged into a monthly figure.
   - **Typical amount (2026)** — Somewhere between about \$1,100 and \$4,207 a month,
     depending on your lifetime earnings.
- **Claiming early** — You can start as early as 62:
   - **Permanent reduction** — Claiming before FRA locks in a lasting cut, roughly 30%
     below your full benefit at 62 (shrinking the closer you claim to FRA).
   - **Earnings test** — If you keep working before FRA, some benefits are withheld once
     your earnings pass an annual limit (about \$24,480 in 2026, with a higher limit in the
     year you reach FRA). The test goes away entirely once you hit FRA, and withheld money
     isn't lost — your benefit is recalculated upward at FRA.
- **Claiming late** *(not Medicare-relevant)* — Delaying past FRA earns delayed retirement
  credits of 8% a year up to age 70 (about 24% above your full benefit); no reason to wait
  beyond 70.
- **Other pathway — disability (SSDI)** — Besides retirement, you can draw Social Security
  through disability if a qualifying medical condition keeps you from working. It still
  requires work credits (including recent ones), and the benefit is based on your earnings
  record much like a retirement benefit. Relevant here because after 24 months on SSDI you
  qualify for Medicare regardless of age.
- **Not the same as SSI** — Supplemental Security Income (SSI) is a separate needs-based
  program that SSA administers but that isn't funded by the payroll tax or tied to your
  work record. It generally leads to Medicaid, not Medicare, so it isn't a Medicare
  enrollment pathway.
- **How to claim** — Apply through SSA — online at ssa.gov, by phone, or at a local
  office.
- **How it's funded** — The FICA payroll tax: you pay 6.2% of your income up to the wage
  cap (\$184,500 in 2026) — so at most about \$11,400 out of your paycheck — matched by
  another 6.2% from your employer (self-employed pay the full 12.4%). Today's workers fund
  today's retirees; surpluses sit in the trust funds.
- **Note** — The above primarily concerns the Old-Age and Survivors Insurance (OASI)
  portion of Social Security — the retirement side — not the separate Disability Insurance
  (DI) fund.
- **Current status** — Per SSA.gov:
   - "The Old-Age and Survivors Insurance (OASI) Trust Fund will be able to pay 100 percent
     of total scheduled benefits until the fourth quarter of 2032, one quarter earlier than
     projected last year. At that time, the fund's reserves will become depleted and
     continuing program income will be sufficient to pay 78 percent of total scheduled
     benefits."
   - "The Disability Insurance (DI) Trust Fund is projected to be able to pay 100 percent of
     total scheduled benefits through at least 2100, the last year of this report's
     projection period."
   - And on Medicare's own fund (Part A / Hospital Insurance): "The Hospital Insurance (HI)
     Trust Fund will be able to pay 100 percent of total scheduled benefits until the second
     quarter of 2033, one quarter earlier than projected last year. At that point, that
     fund's reserves will become depleted and continuing program income will be sufficient
     to pay 89 percent of total scheduled benefits."
   - And on Medicare Part B / Part D (Supplementary Medical Insurance): "The Supplementary
     Medical Insurance (SMI) Trust Fund is adequately financed into the indefinite future
     because, unlike the other trust funds, its main financing sources — enrolled
     beneficiary premiums and the associated federal contributions from the Treasury — are
     automatically adjusted each year to cover costs for the upcoming year. Although the
     financing is assured, rapidly rising SMI expenditures have been placing steadily
     increasing demands on beneficiaries and general taxpayers."
""",
    ),
]

_CSS = """
<style>
[data-testid="stExpander"] summary {padding: .35rem .6rem;}
[data-testid="stExpander"] summary p {font-weight: 600; margin: 0;}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] {font-size: .92rem; line-height: 1.45;}
[data-testid="stExpander"] ul {margin: 0; padding-left: 1.1rem;}
[data-testid="stExpander"] li {margin: 0 0 .3rem 0;}
</style>
"""


def render() -> None:
    st.title("🧾 Inpatient Billing")

    st.caption("Reference only — payer policy changes; verify against current CMS guidance.")
    st.markdown(_CSS, unsafe_allow_html=True)

    for question, answer in _QA:
        with st.expander(question, expanded=len(_QA) == 1):
            st.markdown(answer)
