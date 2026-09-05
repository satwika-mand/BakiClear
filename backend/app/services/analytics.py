"""Deterministic financial calculations and behavioral analytics.

NO LLM CALLS ARE ALLOWED HERE.
All numerical facts and risk priorities are computed deterministically.
"""

from datetime import date
from typing import Any

from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.models.payment_history import PaymentHistory
from backend.app.models.promise import PromiseToPay


def calculate_days_overdue(due_date: date, as_of: date | None = None) -> int:
    """Calculate the number of days an invoice is past due."""
    ref_date = as_of or date.today()
    delta = (ref_date - due_date).days
    return max(0, delta)


def calculate_payment_metrics(
    payment_records: list[PaymentHistory],
    promises: list[PromiseToPay] | None = None,
) -> dict[str, Any]:
    """Deterministically compute payment behavior metrics from historical ledger.

    Returns:
        on_time_percentage: float (0.0 to 100.0)
        average_payment_delay: float (mean delay in days for non-on-time payments)
        disputes: int (total count of disputed invoices)
        broken_promises: int (total count of broken promises to pay)
        total_payments_recorded: int
        delayed_count: int
        defaulted_count: int
    """
    if not payment_records:
        broken_count = sum(1 for p in promises if p.status == "broken") if promises else 0
        return {
            "on_time_percentage": 100.0,
            "average_payment_delay": 0.0,
            "disputes": 0,
            "broken_promises": broken_count,
            "total_payments_recorded": 0,
            "delayed_count": 0,
            "defaulted_count": 0,
        }

    total = len(payment_records)
    on_time = sum(1 for r in payment_records if r.status == "on_time")
    delayed_records = [r for r in payment_records if r.days_to_pay > 0]
    defaulted = sum(1 for r in payment_records if r.status == "defaulted")
    disputes = sum(1 for r in payment_records if r.disputed)

    broken_promises = 0
    if promises:
        broken_promises = sum(1 for p in promises if p.status == "broken")

    on_time_pct = round((on_time / total) * 100.0, 1)
    avg_delay = (
        round(sum(r.days_to_pay for r in delayed_records) / len(delayed_records), 1)
        if delayed_records
        else 0.0
    )

    return {
        "on_time_percentage": on_time_pct,
        "average_payment_delay": avg_delay,
        "disputes": disputes,
        "broken_promises": broken_promises,
        "total_payments_recorded": total,
        "delayed_count": len(delayed_records),
        "defaulted_count": defaulted,
    }


def calculate_risk_priority(
    customer: Customer,
    invoice: Invoice,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Calculate deterministic risk score (0-100) and collection priority.

    Transparent formula:
    - Base score is driven by days overdue (up to 40 pts)
    - Invoice amount severity relative to typical range (up to 20 pts)
    - Historical reliability deficit (100 - on_time_pct) * 0.25 (up to 25 pts)
    - Disputes & broken promises penalty: 5 pts each (up to 15 pts)
    - Customer segment & criticality adjustments:
      - Gold segment: -10 pts (preserves relationship)
      - At-risk segment: +10 pts (escalate sooner)
    """
    days_overdue = invoice.days_overdue
    amount = invoice.amount

    # Overdue severity (0 to 40 pts)
    overdue_score = min(40.0, (days_overdue / 90.0) * 40.0)

    # Amount severity (0 to 20 pts, benchmarked against ₹4,00,000)
    amount_score = min(20.0, (amount / 400_000.0) * 20.0)

    # Reliability deficit (0 to 25 pts)
    on_time_pct = metrics.get("on_time_percentage", 100.0)
    reliability_deficit = ((100.0 - on_time_pct) / 100.0) * 25.0

    # Behavioral friction (0 to 15 pts)
    disputes = metrics.get("disputes", 0)
    broken = metrics.get("broken_promises", 0)
    behavioral_penalty = min(15.0, (disputes * 5.0) + (broken * 7.5))

    # Segment bonus/penalty
    segment_modifier = 0.0
    if customer.segment == "gold":
        segment_modifier = -10.0
    elif customer.segment == "at_risk":
        segment_modifier = 10.0
    elif customer.segment == "new":
        segment_modifier = 5.0

    raw_score = overdue_score + amount_score + reliability_deficit + behavioral_penalty + segment_modifier
    final_score = max(0.0, min(100.0, round(raw_score, 1)))

    # Qualitative classification
    if final_score >= 75:
        risk_tier = "critical"
        priority = "high"
        recommended_action = "Immediate structured negotiation or human escalation"
    elif final_score >= 50:
        risk_tier = "high"
        priority = "high"
        recommended_action = "AI proactive negotiation with bounded payment plan"
    elif final_score >= 25:
        risk_tier = "medium"
        priority = "medium"
        recommended_action = "Standard reminder with small grace extension"
    else:
        risk_tier = "low"
        priority = "low"
        recommended_action = "Gentle courtesy reminder"

    return {
        "risk_score": final_score,
        "risk_tier": risk_tier,
        "priority": priority,
        "recommended_action": recommended_action,
        "score_breakdown": {
            "overdue_component": round(overdue_score, 1),
            "amount_component": round(amount_score, 1),
            "reliability_deficit_component": round(reliability_deficit, 1),
            "behavioral_penalty_component": round(behavioral_penalty, 1),
            "segment_modifier": segment_modifier,
        },
    }
