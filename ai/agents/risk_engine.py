"""Payment Behavior + Risk/Priority Engine. PURE PYTHON — no LLM, no network.

PRINCIPLE 1: numeric/financial judgments are deterministic business rules, not
model output. Every score here is a simple, explainable formula so it can be
justified line-by-line in the demo — no black box.
"""

from ai.schemas import (
    CustomerFacts,
    CustomerProfile,
    Invoice,
    PaymentBehavior,
    PaymentRecord,
    PriorityLevel,
    RiskAssessment,
    RiskLevel,
)


def summarize_payment_behavior(on_time_pct: float, broken_promise_count: int) -> str:
    """Shared wording so mock-mode (computed here) and api-mode (backend's own
    numbers, adapted in ai/orchestration/backend_provider.py) describe a
    customer identically given the same underlying facts."""
    if broken_promise_count >= 2 or on_time_pct < 25:
        return "Unreliable payer — frequent delays, disputes, or broken promises."
    if on_time_pct >= 75:
        return "Reliable payer — pays on time or with minor delays."
    return "Mixed payment history — some delays, no major red flags."


def compute_payment_behavior(customer_id: str, history: list[PaymentRecord]) -> PaymentBehavior:
    """All numeric fields computed directly from PaymentRecord history.

    "On time" = paid on or before the due date. An invoice still awaiting
    payment (paid_date is None) counts against on-time % but is excluded from
    the average-delay calculation since its eventual delay is not yet known.
    """
    if not history:
        return PaymentBehavior(
            customer_id=customer_id,
            total_invoices=0,
            on_time_payment_pct=100.0,
            average_delay_days=0.0,
            dispute_count=0,
            broken_promise_count=0,
            behavioral_summary="No payment history on file yet.",
        )

    on_time_count = sum(1 for r in history if r.paid_date and r.paid_date <= r.due_date)
    delays = [max(0, (r.paid_date - r.due_date).days) for r in history if r.paid_date]
    dispute_count = sum(1 for r in history if r.was_disputed)
    broken_promise_count = sum(1 for r in history if r.broken_promise)
    on_time_pct = round(on_time_count / len(history) * 100, 1)
    avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0
    summary = summarize_payment_behavior(on_time_pct, broken_promise_count)

    return PaymentBehavior(
        customer_id=customer_id,
        total_invoices=len(history),
        on_time_payment_pct=on_time_pct,
        average_delay_days=avg_delay,
        dispute_count=dispute_count,
        broken_promise_count=broken_promise_count,
        behavioral_summary=summary,
    )


def derive_customer_facts(customer: CustomerProfile, history: list[PaymentRecord]) -> CustomerFacts:
    """The minimal facts the Guardrail needs. An "open" dispute is one where
    the disputed invoice is still unpaid — a disputed-then-resolved invoice
    does not block autonomous negotiation."""
    has_open_dispute = any(r.was_disputed and r.paid_date is None for r in history)
    broken_promise_count = sum(1 for r in history if r.broken_promise)
    return CustomerFacts(
        tier=customer.tier,
        has_open_dispute=has_open_dispute,
        broken_promise_count=broken_promise_count,
    )


# Scoring weights. Kept as named constants (not buried magic numbers) so the
# formula is auditable at a glance — this table doubles as the "how risk is
# calculated" answer in the pitch.
_MAX_OVERDUE_POINTS = 30
_MAX_UNRELIABILITY_POINTS = 20
_OPEN_DISPUTE_POINTS = 15
_MAX_BROKEN_PROMISE_POINTS = 30
_POINTS_PER_BROKEN_PROMISE = 15

_MAX_AMOUNT_WEIGHT = 30
_AMOUNT_SCALE = 30_000  # amount_due / this, capped at _MAX_AMOUNT_WEIGHT
_MAX_URGENCY_DAYS_WEIGHT = 20
_URGENCY_DAYS_SCALE = 3  # days_overdue / this, capped at _MAX_URGENCY_DAYS_WEIGHT

_LEVEL_THRESHOLDS = (25, 50, 75)  # score < t1 -> tier[0], < t2 -> tier[1], < t3 -> tier[2], else tier[3]


def _level(score: int, levels: tuple) -> str:
    low, medium, high, critical = levels
    if score < _LEVEL_THRESHOLDS[0]:
        return low
    if score < _LEVEL_THRESHOLDS[1]:
        return medium
    if score < _LEVEL_THRESHOLDS[2]:
        return high
    return critical


def compute_risk_assessment(
    invoice: Invoice,
    behavior: PaymentBehavior,
    facts: CustomerFacts,
) -> RiskAssessment:
    """Risk = how likely this customer is to not pay. Priority = how urgently
    this invoice deserves attention (risk + money at stake + time pressure)."""
    overdue_points = min(_MAX_OVERDUE_POINTS, invoice.days_overdue)
    unreliability_points = round((100 - behavior.on_time_payment_pct) / 100 * _MAX_UNRELIABILITY_POINTS)
    dispute_points = _OPEN_DISPUTE_POINTS if facts.has_open_dispute else 0
    broken_promise_points = min(
        _MAX_BROKEN_PROMISE_POINTS, facts.broken_promise_count * _POINTS_PER_BROKEN_PROMISE
    )

    risk_score = min(
        100, overdue_points + unreliability_points + dispute_points + broken_promise_points
    )

    amount_weight = min(_MAX_AMOUNT_WEIGHT, round(invoice.amount_due / _AMOUNT_SCALE))
    urgency_days_weight = min(
        _MAX_URGENCY_DAYS_WEIGHT, round(invoice.days_overdue / _URGENCY_DAYS_SCALE)
    )
    priority_score = min(100, round(risk_score * 0.5) + amount_weight + urgency_days_weight)

    factors = []
    if overdue_points:
        factors.append(f"{invoice.days_overdue} days overdue")
    if unreliability_points:
        factors.append(f"{behavior.on_time_payment_pct}% on-time payment rate")
    if dispute_points:
        factors.append("open unresolved dispute")
    if broken_promise_points:
        factors.append(f"{facts.broken_promise_count} broken promise(s)")
    if not factors:
        factors.append("clean payment history")

    return RiskAssessment(
        customer_id=invoice.customer_id,
        invoice_id=invoice.invoice_id,
        risk_score=risk_score,
        risk_level=RiskLevel(_level(risk_score, (
            RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL
        ))),
        priority_score=priority_score,
        priority_level=PriorityLevel(_level(priority_score, (
            PriorityLevel.LOW, PriorityLevel.MEDIUM, PriorityLevel.HIGH, PriorityLevel.URGENT
        ))),
        contributing_factors=factors,
    )
