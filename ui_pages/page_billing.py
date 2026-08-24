"""Static inpatient-billing Q&A reference. No AI, no DB — just answers behind a
shared page password. Add a question by appending to _QA."""

import streamlit as st

# Soft access gate — same idea as the A&P page. Not a real credential; it's a
# shared page password.
_BILLING_PASSWORD = "Billing"

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
        "What is the 72-hour rule?",
        """
- **One liner** — The 72-hour rule (Medicare's "3-day payment window") folds a hospital's
  outpatient services given just before an inpatient admission into the inpatient DRG
  payment, so they can't be billed separately.
- **The window** — The 3 calendar days immediately before an inpatient admission, plus the
  admission day itself. For hospitals or units not paid under the inpatient PPS (IPPS), the
  window is only 1 day.
- **What gets bundled** — All outpatient *diagnostic* services in the window are bundled
  into the DRG. Outpatient *non-diagnostic* (therapeutic) services are bundled too when
  they're clinically related to the admission — and since a 2010 law, they're presumed
  related unless the hospital documents that they're unrelated.
- **Whose services count** — Services furnished by the admitting hospital or by an entity
  wholly owned or operated by it. Truly unrelated services, or services from an unaffiliated
  provider, stay separately billable.
- **Why it exists** — It blocks "unbundling" — billing pre-admission outpatient care
  separately under Part B on top of the inpatient DRG, which would pay the hospital twice for
  one episode of care.
- **Observation that converts to inpatient** — When a patient starts in observation
  (outpatient) and is then switched to inpatient by an admission order, the observation and
  other outpatient services delivered in the window get pulled into the inpatient DRG rather
  than billed separately. This mirrors the Two-Midnight benchmark, which counts that
  pre-order time toward the admission decision.
- **The admission order is the pivot** — Inpatient status begins only with a physician's
  inpatient admission order; the 3-day window looks backward from that admission. Before a
  valid order the stay is outpatient. If it's decided before discharge that inpatient wasn't
  appropriate, the hospital can flip inpatient to outpatient using Condition Code 44 (with
  utilization-review and physician sign-off while the patient is still in house); after
  discharge the equivalent is a Part A-to-Part B rebill.
- **Does Medicare Advantage do this?** — Not automatically. The 3-day window is a
  traditional-Medicare IPPS rule. MA plans pay hospitals under their own contracts, which
  are often DRG-based and bundle the pre-admission window similarly — but the specifics are
  contract-driven, and some MA and commercial payers apply their own windows (e.g., 24- or
  72-hour) instead.
- **Other traps** — Despite the "72-hour" nickname it's really 3 *calendar* days, which can
  span more than 72 actual hours. Only the facility/technical services are bundled —
  physicians' professional fees stay separately billable. And to bill related-looking but
  genuinely unrelated non-diagnostic services separately, the hospital attests with
  Condition Code 51.
- **Not the SNF 3-day rule** — Different "3 days": that rule requires a 3-day inpatient stay
  to unlock SNF coverage. This is a billing/payment window, and it's also distinct from the
  Two-Midnight Rule.
""",
    ),
    (
        "What is the SNF 3-day rule?",
        r"""
- **One liner** — Medicare Part A covers a skilled nursing facility (SNF) stay only if it
  follows a qualifying inpatient hospital stay of at least 3 consecutive days.
- **How the 3 days are counted** — Counted by midnights as an admitted inpatient: the
  admission day counts, the discharge day does not. So three inpatient midnights are needed
  to qualify.
- **Observation doesn't count** — The biggest trap. Time in observation (outpatient) status
  does not count toward the 3 days, even when the patient occupies a hospital bed for days.
  Someone observed for 3 days and then sent to a SNF can owe the entire SNF bill, because
  there was never a qualifying inpatient stay. This is the practical bite of the
  observation-vs-inpatient call (and why the MOON notice exists to warn patients of
  observation status).
- **Other conditions** — The SNF care must be for a condition treated during the hospital
  stay (or one that arose while in the SNF), the patient must need daily skilled nursing or
  rehab, and the SNF admission generally must occur within 30 days of hospital discharge.
- **What coverage looks like** — Once qualified, Part A covers up to 100 days per benefit
  period — days 1–20 fully, days 21–100 at \$217/day (2026), nothing after 100 (see the
  Part A section for detail).
- **Waivers** — Medicare Advantage plans commonly waive the 3-day requirement, as do some
  ACOs and value-based arrangements. CMS also waived it temporarily during the COVID-19
  public health emergency, but that blanket waiver ended with the PHE.
- **Not the 72-hour payment window** — Different "3 days": that rule bundles pre-admission
  outpatient billing into the DRG. This one gates whether a later SNF stay is covered.
""",
    ),
    (
        "Admission vs. observation — who wins, who loses",
        r"""
- **The setup** — Same bed, same nurses, often the same care — but the status determines
  which payment machinery runs. Inpatient triggers a Part A DRG lump sum to the hospital
  (commonly on the order of \$10,000+ for a medical DRG); observation is billed as hospital
  *outpatient* under Part B (a comprehensive observation payment, roughly \$2,500). Three
  stakeholders experience that difference very differently.
- **Medicare (the payer)**:
   - **Cost** — Pays far more for an inpatient stay than an observation stay.
   - **Borderline incentive** — Toward *observation*, since it's cheaper per stay — which is
     why the audit apparatus (MACs, RACs) targets short inpatient stays, and why the
     Two-Midnight Rule exists at all: to draw a defensible line and stop the status
     tug-of-war case by case.
- **The patient**:
   - **Inpatient cost** — One Part A deductible (\$1,736) covers the hospital facility bill
     for up to 60 days; physician services still run through Part B.
   - **Observation cost** — Part B cost-sharing instead: the annual deductible (\$283) plus
     20% coinsurance on the services, *plus* the self-administered drug trap covered below.
   - **Borderline incentive** — It genuinely cuts both ways. A short, simple stay can cost
     *less* as observation (20% of a modest outpatient bill beats a \$1,736 deductible), while
     a long stay or one loaded with services favors inpatient, since the uncapped 20% keeps
     accruing under observation. The MOON notice exists because patients often discover their
     status only when the bills arrive; a court-ordered appeals process (from *Alexander v.
     Azar*, implemented 2025) now lets some patients retroactively challenge
     inpatient-to-observation downgrades.
- **What's actually on an observation bill** — Rough Medicare hospital-outpatient (facility)
  payment estimates, unverified; hospital *charges* run far higher before Medicare's rates
  apply:
   - **ED visit (facility fee)** — ~\$450–800 for a level 4–5 visit.
   - **Routine labwork** — ~\$10–40 per test (CBC, CMP, troponin), so ~\$50–150 for a day of
     routine draws; EKG ~\$15.
   - **Imaging (technical component)** — CXR ~\$40; CT head without contrast ~\$150; CT
     chest/abdomen/pelvis with contrast ~\$450–650 (billed as multiple CTs); MRI spine
     ~\$300; TTE with Doppler ~\$450.
   - **Telemetry** — Hospitals charge for it, but Medicare packages cardiac monitoring into
     the visit payment rather than paying it separately.
   - **IV therapy** — Infusions/hydration ~\$150 for the first hour, less for add-on hours.
   - **Physician fees cancel out** — Radiologist reads, hospitalist visits, and consultant
     fees are professional charges billed under Part B *in both statuses*, so they don't
     differentiate observation from admission and are left out here.
   - **The packaging nuance** — For traditional Medicare, a qualifying observation stay
     (8+ hours) usually collapses all of the above into a single comprehensive payment
     (~\$2,500), with the patient owing 20% of that — roughly \$500 — rather than 20% of each
     line. The line items above matter when the stay doesn't qualify for packaging, and for
     MA/commercial payers that pay per service.
- **The self-administered drug trap** — During observation, the patient's routine home
  medications (the daily statin, metformin, blood-pressure pills) are excluded from
  coverage: not Part A (the stay isn't inpatient), not Part B (which covers only drugs that
  are *not usually self-administered*, i.e., clinician-administered infusions and
  injections), and usually not Part D at the point of sale (the hospital pharmacy isn't in
  the Part D network — though a patient can sometimes submit the receipt for partial
  reimbursement). The hospital therefore bills these directly at chargemaster prices — the
  infamous \$10 aspirin.
   - **Does it apply to inpatient?** — No. During an inpatient stay, all drugs are bundled
     into the Part A DRG payment; the trap is observation-only.
   - **Why "self-administered" if a nurse hands it over?** — The term classifies the *drug*,
     not the event: Part B asks whether a drug is *usually* self-administered by the people
     who take it (an oral pill normally swallowed at home fails the test), regardless of who
     actually administers it in the hospital. A nurse bringing lisinopril in a paper cup
     doesn't turn it into a Part B "clinician-administered" drug.
- **The hospital**:
   - **Revenue** — The DRG pays several times what observation pays for a similar short
     stay, so raw revenue always points toward admitting.
   - **What points the other way** — Audit exposure: a RAC clawback takes back the entire
     DRG, and the Condition Code 44 / Part B rebill salvage recovers far less, so a
     borderline admission is revenue *at risk*. Observation revenue is smaller but safe.
     Observation stays also don't count as admissions for the readmission-penalty program
     (HRRP) — a returning recently-discharged patient placed in observation is invisible to
     the penalty, a quiet incentive that has drawn scrutiny.
   - **Borderline incentive** — Split by patient and payer: traditional Medicare with solid
     two-midnight documentation → admit (protected by the presumption); thin documentation,
     an MA plan that ignores the presumption, or a patient back within 30 days of discharge
     → observation pressure. Utilization-review teams exist to arbitrate exactly this line.
- **The punchline** — The three incentives only align for genuinely short, simple stays
  (everyone is fine with observation) and genuinely sick multi-day patients (everyone
  accepts admission). Every borderline case is a three-way tug-of-war — Medicare pulling
  toward observation, hospital revenue pulling toward admission tempered by audit fear, and
  the patient's interest swinging on how long and service-heavy the stay turns out to be.
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
- **How Medicare is funded** — Two streams. Part A (the HI trust fund) runs on the 1.45%
  Medicare payroll tax paid by workers and matched by employers (2.9% for the self-employed,
  with no wage cap and a 0.9% surtax on high earners). Parts B and D (the SMI trust fund) are
  funded by beneficiary premiums (~25%) plus general Treasury revenue (~75%), topped up
  automatically each year.
""",
    ),
    (
        "Medicare Parts A and B",
        r"""
Original Medicare is Part A + Part B, run directly by the government. (Part D drug coverage
has its own detailed section.)
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
   - **Dialysis / ESRD** — Outpatient dialysis (in-center or home) is a Part B benefit, paid
     under the ESRD bundled per-treatment rate — and ESRD is itself a Medicare pathway
     regardless of age. But since Part B has no out-of-pocket cap, the patient owes 20% of
     every treatment with no ceiling; on ongoing dialysis that runs to several thousand
     dollars a year, so it isn't free. Supplemental coverage (Medigap, Medicaid, or a
     Medicare Advantage out-of-pocket max) is what makes it affordable.
""",
    ),
    (
        "Medicare Part D",
        r"""
- **Public program, private plans** — This is the confusing part: Part D is a government
  benefit, but Medicare doesn't sell drug coverage directly. Instead, Medicare defines the
  rules, sets a minimum "standard" benefit and consumer protections, and pays a subsidy
  covering roughly three-quarters of the cost — while private insurers design the actual
  plans, set premiums and drug formularies, and run the coverage. So enrollees buy from and
  pay a private company, yet the benefit, protections, and most of the funding are federal.
  That public-rules / private-delivery split is why it's both "Medicare" and "private pay."
- **How it's funded** — Through the SMI trust fund (the same one that covers Part B), not
  the payroll tax. Three sources fill it each year: general federal revenue from the
  Treasury covers roughly 73–75% (that's the subsidy), enrollee premiums cover about
  15–25%, and states make "clawback" payments for dual-eligibles whose drug coverage moved
  from Medicaid to Part D. Because the law automatically tops the fund up from the Treasury
  to match projected costs, it can't run dry — but rising drug spending means an ever-larger
  annual draw on general revenue.
- **Two ways to get it** — Either a standalone Prescription Drug Plan (PDP) added onto
  Original Medicare, or drug coverage bundled into a Medicare Advantage plan (MA-PD). Part A
  and/or B is required first.
- **How to enroll** — Pick a plan through Medicare's Plan Finder (medicare.gov), directly
  with an insurer, or with a broker. Sign up during the Initial Enrollment Period, the
  annual Open Enrollment window (Oct 15–Dec 7), or a Special Enrollment Period. Going
  without creditable drug coverage triggers a permanent late penalty of about 1% of the
  national base premium per month missed.
- **What it costs (2026)** — Premiums average roughly \$35/month (national base \$38.99;
  some \$0 plans exist; higher earners pay an IRMAA surcharge on top). A plan's deductible
  can be at most \$615. After that, cost-sharing continues until out-of-pocket drug spending
  reaches the \$2,100 annual cap — beyond which covered drugs cost \$0 for the rest of the
  year.
- **Help for low income** — The federal Extra Help / Low-Income Subsidy program sharply
  reduces or eliminates Part D premiums, deductibles, and copays for those who qualify
  financially.
- **Spreading the cost** — The Medicare Prescription Payment Plan lets enrollees spread
  their out-of-pocket drug costs over monthly installments across the year instead of paying
  large amounts at the pharmacy counter.
""",
    ),
    (
        "Medigap (Medicare Supplement)",
        r"""
- **Government or private?** — Private insurance, sold by private companies, with no
  government funding. The government's only role is standardization and regulation: federal
  law defines the benefits into standardized lettered plans, and states regulate the
  insurers. So unlike Part C and Part D — privately delivered but government-funded — Medigap
  is both privately delivered *and* privately paid.
- **What it does — the actual gaps (2026)** — Fills the cost-sharing Original Medicare
  leaves behind: the Part A deductible (\$1,736 per benefit period), hospital day coinsurance
  (\$434/day for days 61–90, \$868/day for lifetime reserve days), SNF coinsurance
  (\$217/day for days 21–100), the 20% Part B coinsurance that otherwise has no ceiling, and
  — on most plans — 365 extra lifetime hospital days after Medicare's run out. This is the
  backstop referred to elsewhere for uncapped costs like dialysis and very long stays.
- **Standardized lettered plans** — Sold as plans A, B, C, D, F, G, K, L, M, and N. A given
  letter offers identical benefits across every insurer, so plans differ only by price and
  service. Plan F (which also covers the Part B deductible) is closed to anyone first
  Medicare-eligible on or after January 1, 2020. Massachusetts, Minnesota, and Wisconsin
  standardize their plans differently.
- **The popular plans and what they cost (2026)**:
   - **Plan G** — Covers essentially all of the above *except* the Part B deductible. After
     paying that \$283 once a year, out-of-pocket on covered services is basically \$0. The
     most popular plan for new enrollees; premiums commonly run about \$165–\$220/month at
     age 65 (varying by insurer, age, and location).
   - **Plan N** — Same idea as Plan G, but the enrollee also pays small copays — up to \$20
     per office visit and up to \$50 per ER visit that doesn't lead to admission — and
     doesn't cover Part B "excess charges." In exchange the premium runs roughly
     \$40–\$80/month less than Plan G.
   - **High-deductible Plan G** — Identical benefits to Plan G, but nothing pays until the
     enrollee meets a \$2,950 annual deductible; the trade-off is a much lower premium, often
     well under \$100/month.
- **Works only with Original Medicare** — Medigap pairs with Parts A + B and cannot be used
  alongside a Medicare Advantage plan. It doesn't include drug coverage (Part D is separate),
  and it doesn't cover long-term/custodial care, dental, vision, or hearing.
- **Premiums rise with age** — Most policies are "attained-age" rated, so the premium climbs
  as the enrollee gets older — a plan that looks cheap at 65 can cost considerably more at 80.
- **When to buy — the underwriting trap** — The 6-month Medigap Open Enrollment Period starts
  the month of turning 65 and being enrolled in Part B; during it, coverage is
  guaranteed-issue with no medical underwriting. Miss that window and — outside limited
  guaranteed-issue situations — insurers can medically underwrite, charging more or denying
  coverage based on health.
""",
    ),
    (
        "Physician (professional) services — inpatient",
        r"""
- **Always Part B — even for an inpatient** — This trips people up: during an inpatient
  admission, Part A pays the *facility* side (room, nursing, the DRG bundle), but the
  physicians' professional work is billed under *Part B*, inpatient or not. So one inpatient
  stay generates a Part A facility claim *plus* a separate Part B professional claim from
  every physician involved — and the patient still owes the Part B deductible and 20%
  coinsurance on those physician services.
- **What counts / how it's priced** — Each physician bills their own work with CPT / E&M
  codes priced by the Medicare Physician Fee Schedule. Payment = the code's relative value
  units (RVUs) × a national conversion factor (\$33.40 in 2026 for non-APM clinicians),
  adjusted for local costs. (Dollar figures below are facility rates from fastrvu.com —
  e.g. fastrvu.com/cpt/99292.)
- **Hospitalists** — Bill inpatient E&M codes, generally one per patient per day, with the
  level driven by medical decision-making or total time (inpatient E&M has 3 levels, unlike
  the 5-level office/outpatient set):
   - **Initial visit / admission** — 99221 / 99222 / 99223 by complexity: low \$74,
     moderate \$117, high \$156.
   - **Subsequent daily visits** — 99231 / 99232 / 99233 by complexity: \$44, \$70, \$107.
   - **Discharge day** — 99238 \$75 (30 min or less) or 99239 \$107 (more than 30 min).
   - Only one hospitalist E&M per patient per day counts; a group's rounding is billed under
     whoever saw the patient.
- **Surgeons — the global package** — A surgical CPT code is paid as a bundled "global
  package": the operation plus routine pre-op and post-op care for a set global period (0,
  10, or 90 days for major surgery). Routine follow-up within that period isn't separately
  billable. Modifiers unbundle the exceptions — -57 (decision for surgery), -25 (separate
  same-day E&M), -78 (return to the OR for a complication), -79 (unrelated procedure).
  Payment ranges from a few hundred dollars for minor procedures to several thousand for
  major operations.
- **Consultants** — A specialist asked to weigh in bills an inpatient E&M visit. Medicare
  stopped recognizing the dedicated consultation codes (99251–99255) in 2010, so consultants
  now use the same initial/subsequent inpatient E&M codes as everyone else (some commercial
  payers still accept consult codes). A consultant's bill is separate from the hospitalist's
  for the same patient and day, since they're different providers/specialties.
- **Critical care time** — Time-based, not per-visit: 99291 covers the first 30–74 minutes
  of critical care in a day (\$199), and 99292 each additional 30 minutes (\$100). It
  requires a critically ill patient and the physician's full attention, and it
  bundles several services (e.g., ventilator management, blood gases) that then can't be
  billed separately during that time. Time within the same group may need to be aggregated.
- **Smoking cessation counseling** — Separately billable at the bedside: 99406 for 3–10
  minutes (\$11) and 99407 for more than 10 minutes (\$22); Medicare covers up to two quit
  attempts a year, four sessions each.
- **Other separately billable services** — Advance care planning (99497, \$66 for the first
  30 minutes) and prolonged-service add-on codes apply on top of the daily E&M.
- **Bedside procedures** — Each carries its own CPT on top of the daily E&M: central line
  36556 (\$77), emergency intubation 31500 (\$133), lumbar puncture 62270 (\$59),
  paracentesis 49082 (\$71).
""",
    ),
    (
        "Choosing a billing level (admission & progress notes)",
        r"""
- **Two ways to pick the level** — Since the 2023 overhaul, an inpatient E&M level is set
  by *either* medical decision-making (MDM) *or* total time on the calendar date —
  whichever supports the higher level. History and exam still get documented for care, but
  they no longer drive the level.
- **"Isn't complexity subjective?"** — No, and this is the key idea. MDM complexity is
  defined by the *patient's* clinical situation — the problems, the data, and the risk — not
  by how hard the case feels to the individual clinician. A brilliant physician who finds a
  septic ICU patient routine still bills a high level, because the problems and risk are
  objectively high. The rubric exists precisely to standardize this and take perceived
  effort and raw intelligence out of it. Judgment survives only at the margins (which is why
  documentation and audits matter), and when MDM is genuinely ambiguous, total time is the
  objective fallback.
- **The MDM rubric — three elements** — Each element has its own low → moderate → high
  ladder, and the visit's overall MDM tier is set by whichever level is met by *at least two
  of the three*:
   - **Problems addressed** — How many active problems and how serious. *Low*: one stable
     chronic illness, or one acute uncomplicated illness. *Moderate*: a chronic illness with
     exacerbation or progression, two or more stable chronic illnesses, an acute illness with
     systemic symptoms, or a new problem with uncertain prognosis. *High*: a chronic illness
     with severe exacerbation, or an acute illness/injury that threatens life or organ
     function.
   - **Data reviewed** — Built from three "categories": (1) ordering/reviewing each unique
     test and reviewing outside records or a separate historian, (2) independently
     interpreting a test someone else performed, and (3) discussing management with an
     external physician/provider. *Moderate* generally needs one category met; *high* needs
     more (e.g., two categories, or an independent interpretation plus outside discussion).
   - **Risk of management** — *Low*: over-the-counter measures. *Moderate*: prescription drug
     management, or a decision limited by social factors. *High*: a decision to hospitalize,
     to escalate or de-escalate care, a drug needing intensive toxicity monitoring, or a
     DNR/comfort-care decision.
   - **How "2 of 3" plays out** — A septic patient admitted to the ICU hits *high* problems
     (threat to life) and *high* risk (decision to hospitalize/escalate) — two of three — so
     the visit is high-level MDM even if the data element is only moderate.
- **Time as the alternative** — Total time counts everything the billing physician
  personally spends on that patient on that calendar date — chart review, exam, ordering,
  documentation, care coordination — but not other providers' time and not the time of
  separately billed procedures.
- **Admission notes (initial care)** — Either path works, exactly like progress notes: pick
  the level by MDM *or* by total time, whichever is higher — it is not time-only. 99221
  straightforward/low MDM or 40 min; 99222 moderate or 55 min; 99223 high or 75 min. In
  practice MDM is the usual driver, and the decision to hospitalize itself pushes risk to at
  least moderate, so most true admissions land at 99222 or 99223.
- **Progress notes (subsequent care)** — 99231 straightforward/low or 25 min (stable,
  improving); 99232 moderate or 35 min (active management, adjusting treatment); 99233 high
  or 50 min (worsening, escalating care, high-risk drugs, or a threat to life/organ).
- **Does observation status change the codes?** — No — not since January 1, 2023, when
  inpatient and observation E&M were merged into one set. 99221–99223 (initial) and
  99231–99233 (subsequent) now cover both, so the physician's professional code and level are
  chosen identically regardless of status. (Before 2023, observation had its own separate
  codes.)
   - **The split is on the facility side, not the physician code** — The physician's E&M is
     the same either way; what differs is the *hospital's* claim. An inpatient generates a
     Part A DRG claim, while observation is billed as hospital outpatient under Part B. So
     status changes how the facility bills, not the doctor's code — which is exactly why the
     inpatient-vs-observation call matters so much elsewhere even though it's invisible in the
     professional coding.
- **Same-day admit and discharge (99234–99236)** — The one distinct set that survives: used
  when a patient is admitted (to inpatient *or* observation) and discharged on the *same
  calendar date*, rolling the admission and discharge work into a single code. Levels mirror
  the others — 99234 straightforward/low MDM or 45 min (\$88); 99235 moderate or 70 min
  (\$143); 99236 high or 85 min (\$190). Medicare requires the stay to span at least 8 hours
  on that date to use these; if it's under 8 hours, only the initial-care code (99221–99223)
  is billed, with no separate discharge code.
- **Practical traps** — The note has to actually document the elements that justify the
  level. Prescription drug management alone reaches moderate risk. Copy-forward notes that
  don't reflect the day's real problems, data, and risk are a common audit target — the
  level must match the work genuinely done that day.
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


def _gate() -> bool:
    """Show the password prompt until unlocked. True once the page may render."""
    if st.session_state.get("billing_unlocked"):
        return True

    st.caption("Password-protected reference.")
    st.text_input("Password", type="password", key="billing_pw",
                  placeholder="Password", label_visibility="collapsed")
    if st.button("Unlock", key="billing_unlock"):
        if st.session_state.get("billing_pw") == _BILLING_PASSWORD:
            st.session_state["billing_unlocked"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


def render() -> None:
    st.title("🧾 Inpatient Billing")

    if not _gate():
        return

    st.caption("Reference only — payer policy changes; verify against current CMS guidance.")
    st.markdown(_CSS, unsafe_allow_html=True)

    for question, answer in _QA:
        with st.expander(question, expanded=len(_QA) == 1):
            st.markdown(answer)
