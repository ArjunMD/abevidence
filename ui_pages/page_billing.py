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
     the initiation of care, including pre-order ED/observation time, toward the
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
     clear — pre-order midnights count for the benchmark but not the audit protection.
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
        r"""
- **Relevance** — People already drawing from SS are automatically enrolled in Medicare
  Part A and Part B (opt-out). So here is a brief overview.
- **Eligibility — the 40-credit rule** — Must have worked 40 quarters (10 years) and paid
  into social security. A spouse's work can count.
- **Claiming at FRA** — FRA (full retirement age) is currently 67:
   - **What it pays** — Claiming at FRA pays 100% of the benefit — the full Primary
     Insurance Amount (PIA), with no reduction.
   - **How the PIA is set** — It's based on the highest 35 years of earnings, indexed for
     wage inflation and averaged into a monthly figure.
   - **Typical amount (2026)** — Somewhere between about \$1,100 and \$4,207 a month,
     depending on lifetime earnings.
- **Claiming early** — Benefits can start as early as 62:
   - **Permanent reduction** — Claiming before FRA locks in a lasting cut, roughly 30%
     below the full benefit at 62 (shrinking the closer the claim is to FRA).
   - **Earnings test** — For someone who keeps working before FRA, some benefits are
     withheld once earnings pass an annual limit (about \$24,480 in 2026, with a higher
     limit in the year FRA is reached). The test goes away entirely at FRA, and withheld
     money isn't lost — the benefit is recalculated upward at FRA.
- **Claiming late** *(not Medicare-relevant)* — Delaying past FRA earns delayed retirement
  credits of 8% a year up to age 70 (about 24% above the full benefit); no reason to wait
  beyond 70.
- **Other pathway — disability (SSDI)** — Besides retirement, Social Security can be drawn
  through disability when a qualifying medical condition prevents work. It still requires
  work credits (including recent ones), and the benefit is based on the earnings record much
  like a retirement benefit. Relevant here because after 24 months on SSDI a person
  qualifies for Medicare regardless of age.
- **Not the same as SSI** — Supplemental Security Income (SSI) is a separate needs-based
  program that SSA administers but that isn't funded by the payroll tax or tied to a work
  record. It generally leads to Medicaid, not Medicare, so it isn't a Medicare enrollment
  pathway.
- **How to claim** — Apply through SSA — online at ssa.gov, by phone, or at a local
  office.
- **How it's funded** — The FICA payroll tax: workers pay 6.2% of income up to the wage
  cap (\$184,500 in 2026) — so at most about \$11,400 a year — matched by another 6.2% from
  the employer (self-employed pay the full 12.4%). Today's workers fund today's retirees;
  surpluses sit in the trust funds.
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
    (
        "Medicare enrollment",
        r"""
- **When it starts** — Medicare eligibility generally begins at 65. Under 65, it comes
  after 24 months on SSDI, or immediately with ESRD (kidney failure) or ALS.
- **Eligibility** — Requires being a U.S. citizen or a lawful permanent resident who has
  lived here at least 5 continuous years.
- **Premium-free Part A** — Part A is premium-free with 40 work credits (the beneficiary's
  or a spouse's) — the same 10-year threshold as Social Security; without enough credits
  Part A can still be had by paying a premium. Part B is open to anyone eligible who pays
  the premium.
- **Automatic vs. sign-up** — People already drawing Social Security benefits are enrolled
  automatically at 65 — Part A and Part B, with Part B being opt-out. Everyone else has to
  actively sign up; it doesn't happen on its own.
- **Enrollment periods** — There are three windows for signing up, depending on timing:
   - **Initial (IEP)** — The first chance: a 7-month window around the 65th birthday — the
     3 months before the birthday month, that month, and the 3 months after. This is the
     penalty-free on-ramp for most people.
   - **General (GEP)** — The fallback after a missed IEP with no other coverage: enrollment
     runs Jan 1–Mar 31 each year, with coverage starting the month after — and a late
     penalty is likely.
   - **Special (SEP)** — For those who kept working past 65 with employer group coverage
     (from their own or a spouse's current job): Medicare can be delayed penalty-free and
     enrolled within 8 months of that job or coverage ending. COBRA and retiree coverage do
     *not* count.
- **HSA backdating trap** — Enrolling in Medicare — even premium-free Part A — ends eligibility to
  contribute to a Health Savings Account, and Part A can back-date up to 6 months. Anyone
  working past 65 and still funding an HSA should stop contributions before enrolling to
  avoid a tax penalty.
- **Working while on Medicare** — Medicare has no earnings test, so unlike Social Security,
  working doesn't reduce benefits — it's fine to work and be on Medicare at the same time.
  When someone also has employer coverage, which pays first depends on employer size: at
  employers with 20+ employees the employer plan is primary and Medicare is secondary,
  while at employers with fewer than 20 employees Medicare is primary. Because a strong
  large-employer plan often has richer coverage and an out-of-pocket cap (which Original
  Medicare lacks), many people with 20+-employee coverage delay Part B while working and
  enroll penalty-free later via the SEP.
- **Part D (drug coverage)** — Bought separately from a private insurer to add drug coverage
  to Original Medicare; requires Part A and/or B first. Enroll during the IEP or each year's
  Open Enrollment (Oct 15–Dec 7).
- **Late-enrollment penalties** — These are usually permanent:
   - **Part B** — Adds 10% to the premium for each full 12 months Part B could have been
     held but wasn't, for as long as it's held.
   - **Part D** — Adds ~1% of the national base premium per month spent without creditable
     drug coverage.
   - **Part A** — Most people get Part A premium-free (from the 40 work credits), so no
     penalty; those who must buy it can face one.
- **What it costs (2026)** — Part A is premium-free for most; Part B's standard premium is
  \$202.90/month. Higher earners pay an income-based surcharge called IRMAA (Income-Related
  Monthly Adjustment Amount) on top of the standard premium for both Part B and Part D —
  based on tax-return income from two years prior, it kicks in above roughly \$109,000
  (single) / \$218,000 (joint) in 2026 and rises in tiers from there. Part D premiums
  otherwise vary by plan.
""",
    ),
    (
        "The parts of Medicare (A, B, D)",
        r"""
Original Medicare is Part A + Part B, run directly by the government; Part D is optional
drug coverage from private plans.
- **Part A — Hospital Insurance** — The inpatient side, funded by the payroll-tax HI trust
  fund.
   - **Covers** — Inpatient hospital stays, skilled nursing facility (SNF) care after a
     qualifying hospital stay, home health, and hospice.
   - **Benefit period** — Part A is metered in benefit periods, not calendar years. One
     begins on the day of inpatient admission and ends only after 60 straight days out of
     any hospital or SNF. A new admission after that gap starts a fresh benefit period — and
     a fresh deductible. There's no cap on how many benefit periods a person can have in a
     year or a lifetime. Hospital and SNF care fall under the *same* benefit period, so a
     hospital stay followed by SNF care doesn't reset the clock.
   - **Costs (2026)** — Premium-free for most (the 40-credit rule). The dollar figures below
     are the patient's out-of-pocket share per day; Medicare covers the rest. Each benefit
     period starts with a \$1,736 deductible, after which hospital days 1–60 cost \$0/day;
     days 61–90 cost \$434/day; days 91+ draw on a lifetime bank of 60 reserve days at
     \$868/day (once used, gone for good) — and after those run out Medicare pays nothing, so
     the patient owes the full bill. SNF care within the same benefit period is \$0/day for
     days 1–20, then \$217/day for days 21–100; after day 100 Medicare pays nothing and the
     patient covers the entire cost.
   - **Doesn't cover custodial care** — Medicare pays for skilled care, not long-term
     custodial care — routine help with daily living like bathing, dressing, eating,
     toileting, and supervision. So it pays nothing for assisted living, memory care, adult
     family homes, or long-term nursing-home stays; those fall to private pay, long-term
     care insurance, or Medicaid.
   - **LTAC (long-term acute care)** — An LTAC hospital treats patients needing extended
     hospital-level care (e.g., ventilator weaning, complex wounds). Because it's inpatient
     hospital care, Part A covers it under the regular hospital-day tiers — not the 100-day
     SNF cap (that limit is SNF-only). A long LTAC stay still draws down the same
     benefit-period hospital days and lifetime reserve days as any hospital admission, but
     it isn't cut off at 100 days. Once the 60 lifetime reserve days are exhausted, though,
     Medicare pays nothing and the patient owes the full cost — a hard stop that lands at day
     150 within a single benefit period (days 1–90 plus 60 reserve days).
   - **Resets and backstops** — The day counts reset only after the 60-day benefit-period
     break above, and supplemental coverage (Medigap) softens this — both discussed
     elsewhere.
- **Part B — Medical Insurance** — The outpatient/physician side, funded by the SMI trust
  fund (beneficiary premiums plus general Treasury revenue).
   - **Covers** — Physician and outpatient services, labs, imaging, durable medical
     equipment, preventive care, and hospital outpatient/observation services.
   - **Costs (2026)** — Standard premium \$202.90/month (higher earners pay IRMAA on top),
     a \$283 annual deductible, then 20% coinsurance on most services — with no out-of-pocket
     cap under Original Medicare.
- **Part D — Prescription Drugs** — Optional outpatient drug coverage bought from private
  plans; requires Part A and/or B first.
   - **Covers** — Self-administered prescription drugs, via standalone plans or bundled into
     a Medicare Advantage plan.
   - **Costs (2026)** — Premiums vary by plan (national base around \$39/month), with IRMAA
     surcharges for higher earners.
   - **The "donut hole"** — Part D used to have a coverage gap: once a person's drug
     spending passed a certain point, the plan stopped chipping in as much and the person had
     to pay a big share out of pocket (at one time 100% of the cost, later 25%) until their
     spending climbed high enough to trigger extra "catastrophic" help. That gap was
     nicknamed the donut hole. It's now basically gone — since 2025 there's a firm yearly
     out-of-pocket limit (\$2,000, rising a little each year). Once a person's own drug
     spending reaches that limit, the plan pays 100% of covered drugs for the rest of the
     year.
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
