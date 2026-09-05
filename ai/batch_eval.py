"""Batch evaluation of negotiation extraction accuracy against a labeled test
set — the one genuinely uncertain AI-quality number in this system.

Deliberately separate from ai/evaluate.py: this costs real Gemini calls and
must be run explicitly (`python -m ai.batch_eval`), never on a Streamlit
rerun. Results are persisted to eval_reports/negotiation_extraction.json so
this is a rerunnable regression check, not a one-off number.

Test cases are template-generated where the expected label is defined BY
CONSTRUCTION (the template dictates the discount %/extension days, so there
is no subjective hand-labeling step to get wrong), plus a small hand-crafted
adversarial set for the ambiguous cases templates can't produce. Both are
stratified by intent so results can be broken down per-cohort rather than
reported as one blended number.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ai.agents.negotiation import extract_negotiation_result
from ai.schemas import (
    CollectionChannel,
    CollectionStrategy,
    CollectionTone,
    Invoice,
    NegotiationTurn,
)

_REPORT_PATH = Path(__file__).resolve().parent.parent / "eval_reports" / "negotiation_extraction.json"

_STRATEGY = CollectionStrategy(
    invoice_id="EVAL", customer_id="EVAL",
    recommended_channel=CollectionChannel.EMAIL, tone=CollectionTone.EMPATHETIC,
    urgency="Medium", max_extension_days=10, max_discount_pct=5.0,
    requires_human_approval=False,
    recommended_approach="Open with an empathetic check-in and offer flexible terms.",
    reasoning="Evaluation harness fixture — not a real strategy decision.",
)
_INVOICE = Invoice(
    invoice_id="EVAL", customer_id="EVAL", amount_due=100_000.0,
    due_date=date(2026, 8, 1), days_overdue=12,
)
_OPENER = [NegotiationTurn(speaker="ai", message="Hi, your invoice is overdue. How can we help resolve this?", timestamp=datetime.now())]


@dataclass
class TestCase:
    message: str
    expected_intent: str
    expected_discount_pct: float
    expected_extension_days: int
    tags: list[str] = field(default_factory=list)
    # Mixed-ask cases have two defensible primary intents — grade leniently.
    acceptable_intents: list[str] | None = None


@dataclass
class CaseResult:
    case: TestCase
    actual_intent: str
    actual_discount_pct: float
    actual_extension_days: int
    intent_correct: bool
    discount_correct: bool
    extension_correct: bool
    latency_s: float
    error: str | None = None


_DISCOUNT_TOLERANCE = 1.0  # percentage points
_EXTENSION_TOLERANCE = 1  # days


def _build_test_cases() -> list[TestCase]:
    cases: list[TestCase] = []

    # --- Willing to pay: no concession asked ---
    for msg in [
        "I'll pay the full amount right away.",
        "Sure, I can settle this in full today.",
        "No problem, I'll make the full payment now.",
        "I agree to pay the complete amount immediately.",
        "Yes, I'll clear the entire due amount today.",
    ]:
        cases.append(TestCase(msg, "willing_to_pay", 0.0, 0, tags=["willing_to_pay"]))

    # --- Extension only, boundary-relevant day counts ---
    ext_templates = [
        "Can I get {n} more days to pay this off?",
        "I need {n} extra days before I can settle this.",
        "Would it be possible to extend the deadline by {n} days?",
        "Please give me {n} more days, cash flow is tight right now.",
        "I can pay, but I'll need {n} additional days.",
    ]
    for n, tmpl in zip([3, 5, 7, 10, 15], ext_templates, strict=True):
        cases.append(TestCase(tmpl.format(n=n), "requests_extension", 0.0, n, tags=["requests_extension"]))

    # --- Discount only, boundary-relevant percentages ---
    disc_templates = [
        "Can you give me {d}% off if I pay today?",
        "I'll settle now if you knock {d}% off the total.",
        "Would you consider a {d}% discount for immediate payment?",
        "Give me {d}% off and I'll pay right now.",
        "I can pay today only if there's a {d}% reduction.",
    ]
    for d, tmpl in zip([3, 5, 10, 15, 25], disc_templates, strict=True):
        cases.append(TestCase(tmpl.format(d=d), "requests_discount", float(d), 0, tags=["requests_discount"]))

    # --- Disputes ---
    for msg in [
        "I don't think this amount is correct, I already made a partial payment.",
        "This invoice seems wrong, I dispute the charges.",
        "I already paid part of this, why am I being billed the full amount?",
        "There's an error here, I don't owe this much.",
        "I disagree with this invoice amount, please review it.",
    ]:
        cases.append(TestCase(msg, "disputes_amount", 0.0, 0, tags=["disputes_amount"]))

    # --- Refuses ---
    for msg in [
        "I'm not going to pay this, period.",
        "No, I refuse to pay right now.",
        "I won't be making any payment on this invoice.",
        "Not paying this, end of discussion.",
        "I have no intention of settling this invoice.",
    ]:
        cases.append(TestCase(msg, "refuses", 0.0, 0, tags=["refuses"]))

    # --- Unclear ---
    for msg in [
        "Hmm, let me think about it.",
        "I'm not sure what to do here.",
        "Can you explain this invoice to me again?",
        "What are my options?",
        "I don't understand this charge.",
    ]:
        cases.append(TestCase(msg, "unclear", 0.0, 0, tags=["unclear"]))

    # --- Mixed asks: both fields matter, "primary intent" is genuinely ambiguous ---
    mixed = [
        ("Give me 10% off and 7 more days and I'll pay.", 10.0, 7),
        ("Can I get 5 extra days plus a 15% discount?", 15.0, 5),
        ("I'll pay if you give 3% off, but I also need 10 more days.", 3.0, 10),
    ]
    for msg, d, n in mixed:
        cases.append(TestCase(
            msg, "requests_discount", d, n, tags=["mixed"],
            acceptable_intents=["requests_discount", "requests_extension"],
        ))

    # --- Hand-crafted adversarial: cases templates can't produce ---
    cases.extend([
        TestCase("Yeah sure, take your 50% and get lost.", "unclear", 0.0, 0,
                 tags=["adversarial", "sarcasm"], acceptable_intents=["unclear", "refuses", "requests_discount"]),
        TestCase("I already paid this last week, check your records.", "disputes_amount", 0.0, 0,
                 tags=["adversarial", "already_paid"]),
        TestCase("k", "unclear", 0.0, 0, tags=["adversarial", "too_short"]),
        TestCase("Fine, whatever, just give me some time.", "requests_extension", 0.0, 0,
                 tags=["adversarial", "vague_extension"],
                 acceptable_intents=["requests_extension", "unclear"]),
        TestCase("I want -10% discount and negative days please.", "unclear", 0.0, 0,
                 tags=["adversarial", "nonsensical"],
                 acceptable_intents=["unclear", "requests_discount"]),
        TestCase("Only if you give me 100% off will I even consider it.", "requests_discount", 100.0, 0,
                 tags=["adversarial", "unrealistic_ask"]),
        TestCase("I'll pay half now and half never.", "refuses", 0.0, 0,
                 tags=["adversarial", "partial_refusal"],
                 acceptable_intents=["refuses", "willing_to_pay", "unclear"]),
        TestCase("Talk to my lawyer.", "refuses", 0.0, 0,
                 tags=["adversarial", "hostile"], acceptable_intents=["refuses", "disputes_amount"]),
    ])

    return cases


def _run_case(case: TestCase) -> CaseResult:
    start = time.time()
    try:
        result = extract_negotiation_result(
            session_id="EVAL", customer_name="Eval Customer", invoice=_INVOICE,
            strategy=_STRATEGY, conversation=_OPENER, latest_customer_message=case.message,
        )
    except Exception as exc:
        return CaseResult(case, "ERROR", 0.0, 0, False, False, False, time.time() - start, error=str(exc))

    acceptable = case.acceptable_intents or [case.expected_intent]
    intent_correct = result.intent.value in acceptable
    discount_correct = abs(result.requested_discount_pct - case.expected_discount_pct) <= _DISCOUNT_TOLERANCE
    extension_correct = abs(result.requested_extension_days - case.expected_extension_days) <= _EXTENSION_TOLERANCE

    return CaseResult(
        case=case,
        actual_intent=result.intent.value,
        actual_discount_pct=result.requested_discount_pct,
        actual_extension_days=result.requested_extension_days,
        intent_correct=intent_correct,
        discount_correct=discount_correct,
        extension_correct=extension_correct,
        latency_s=time.time() - start,
    )


def _wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score confidence interval for a proportion — more accurate
    than the normal approximation at small n, which every per-cohort slice
    here is."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return (round(max(0.0, lo) * 100, 1), round(min(1.0, hi) * 100, 1))


def run_batch_eval(limit: int | None = None) -> dict:
    cases = _build_test_cases()
    if limit is not None:
        cases = cases[:limit]

    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        r = _run_case(case)
        results.append(r)
        # The free-tier fallback model caps at 15 requests/minute. Once the
        # primary model's daily quota is exhausted (easy to hit during a dev
        # session), every call here falls through to the fallback, and an
        # unpaced loop blows through its per-minute cap around case 24 —
        # confirmed live. Pace to ~10/minute to leave headroom.
        if i < len(cases):
            time.sleep(6)
        status = "OK" if r.intent_correct and r.discount_correct and r.extension_correct else "MISS"
        print(f"[{i}/{len(cases)}] {status} intent={r.actual_intent} disc={r.actual_discount_pct} ext={r.actual_extension_days} ({r.latency_s:.2f}s) :: {case.message[:60]}")

    # Overall
    n = len(results)
    intent_ok = sum(1 for r in results if r.intent_correct)
    discount_ok = sum(1 for r in results if r.discount_correct)
    extension_ok = sum(1 for r in results if r.extension_correct)
    errors = [r for r in results if r.error]

    # Per-tag (cohort) breakdown
    by_tag: dict[str, list[CaseResult]] = {}
    for r in results:
        for tag in r.case.tags:
            by_tag.setdefault(tag, []).append(r)

    cohort_report = {}
    for tag, rs in by_tag.items():
        ok = sum(1 for r in rs if r.intent_correct and r.discount_correct and r.extension_correct)
        lo, hi = _wilson_ci(ok, len(rs))
        cohort_report[tag] = {
            "n": len(rs), "correct": ok,
            "accuracy_pct": round(ok / len(rs) * 100, 1),
            "wilson_95_ci": [lo, hi],
        }

    overall_ok = sum(1 for r in results if r.intent_correct and r.discount_correct and r.extension_correct)
    overall_lo, overall_hi = _wilson_ci(overall_ok, n)

    report = {
        "generated_at": datetime.now().isoformat(),
        "n_cases": n,
        "overall": {
            "fully_correct": overall_ok,
            "fully_correct_pct": round(overall_ok / n * 100, 1) if n else 0.0,
            "wilson_95_ci": [overall_lo, overall_hi],
            "intent_accuracy_pct": round(intent_ok / n * 100, 1) if n else 0.0,
            "discount_accuracy_pct": round(discount_ok / n * 100, 1) if n else 0.0,
            "extension_accuracy_pct": round(extension_ok / n * 100, 1) if n else 0.0,
            "errors": len(errors),
        },
        "by_cohort": cohort_report,
        "misses": [
            {
                "message": r.case.message, "expected_intent": r.case.expected_intent,
                "acceptable_intents": r.case.acceptable_intents, "actual_intent": r.actual_intent,
                "expected_discount_pct": r.case.expected_discount_pct, "actual_discount_pct": r.actual_discount_pct,
                "expected_extension_days": r.case.expected_extension_days, "actual_extension_days": r.actual_extension_days,
                "tags": r.case.tags, "error": r.error,
            }
            for r in results
            if not (r.intent_correct and r.discount_correct and r.extension_correct)
        ],
    }

    _REPORT_PATH.parent.mkdir(exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    import sys

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    report = run_batch_eval(limit=limit)
    print(f"\n=== Overall: {report['overall']['fully_correct_pct']}% fully correct "
          f"(95% CI: {report['overall']['wilson_95_ci']}) over {report['n_cases']} cases ===")
    print(f"Report written to {_REPORT_PATH}")
