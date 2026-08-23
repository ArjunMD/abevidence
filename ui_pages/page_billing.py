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
