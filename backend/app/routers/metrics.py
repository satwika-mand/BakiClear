"""Metrics & Reporting API Router."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.action_log import ActionLog
from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.models.promise import PromiseToPay
from backend.app.schemas.metrics import MetricsSummaryResponse, SegmentMetrics

router = APIRouter(prefix="/api/metrics", tags=["Metrics & Analytics"])


@router.get("/summary", response_model=MetricsSummaryResponse)
def get_metrics_summary(db: Session = Depends(get_db)):
    """Retrieve operational collections metrics, recovery statistics, and guardrail analytics."""
    # Invoices aggregate
    overdue_statuses = ["overdue", "in_negotiation"]
    overdue_sum_stmt = select(func.coalesce(func.sum(Invoice.amount), 0.0)).where(
        Invoice.status.in_(overdue_statuses)
    )
    total_overdue = float(db.scalar(overdue_sum_stmt) or 0.0)

    recovered_sum_stmt = select(func.coalesce(func.sum(Invoice.amount), 0.0)).where(
        Invoice.status == "paid"
    )
    total_recovered = float(db.scalar(recovered_sum_stmt) or 0.0)

    total_invoiced = total_overdue + total_recovered
    recovery_rate = (
        round((total_recovered / total_invoiced) * 100.0, 1) if total_invoiced > 0 else 0.0
    )

    total_inv_count = db.scalar(select(func.count(Invoice.invoice_id))) or 0
    overdue_inv_count = db.scalar(
        select(func.count(Invoice.invoice_id)).where(Invoice.status == "overdue")
    ) or 0
    in_negotiation_count = db.scalar(
        select(func.count(Invoice.invoice_id)).where(Invoice.status == "in_negotiation")
    ) or 0
    paid_inv_count = db.scalar(
        select(func.count(Invoice.invoice_id)).where(Invoice.status == "paid")
    ) or 0

    # Promises aggregate
    promises_created = db.scalar(select(func.count(PromiseToPay.promise_id))) or 0
    promises_kept = db.scalar(
        select(func.count(PromiseToPay.promise_id)).where(PromiseToPay.status == "kept")
    ) or 0
    promises_broken = db.scalar(
        select(func.count(PromiseToPay.promise_id)).where(PromiseToPay.status == "broken")
    ) or 0
    promises_pending = db.scalar(
        select(func.count(PromiseToPay.promise_id)).where(PromiseToPay.status == "pending")
    ) or 0

    # Guardrails & Escalation audit aggregates
    escalations = db.scalar(
        select(func.count(ActionLog.action_id)).where(ActionLog.decision == "escalated")
    ) or 0
    guardrail_blocks = db.scalar(
        select(func.count(ActionLog.action_id)).where(
            ActionLog.decision == "rejected",
            ActionLog.actor == "policy_engine",
        )
    ) or 0

    # Segment Breakdown
    segment_data = {}
    for seg in ["gold", "standard", "at_risk", "new"]:
        seg_total_inv = db.scalar(
            select(func.count(Invoice.invoice_id))
            .join(Customer, Invoice.customer_id == Customer.customer_id)
            .where(Customer.segment == seg)
        ) or 0

        seg_overdue = float(
            db.scalar(
                select(func.coalesce(func.sum(Invoice.amount), 0.0))
                .join(Customer, Invoice.customer_id == Customer.customer_id)
                .where(Customer.segment == seg, Invoice.status.in_(overdue_statuses))
            ) or 0.0
        )

        seg_recovered = float(
            db.scalar(
                select(func.coalesce(func.sum(Invoice.amount), 0.0))
                .join(Customer, Invoice.customer_id == Customer.customer_id)
                .where(Customer.segment == seg, Invoice.status == "paid")
            ) or 0.0
        )

        segment_data[seg] = SegmentMetrics(
            total_invoices=seg_total_inv,
            overdue_amount=round(seg_overdue, 2),
            recovered_amount=round(seg_recovered, 2),
        )

    return MetricsSummaryResponse(
        total_overdue_amount=round(total_overdue, 2),
        total_recovered_amount=round(total_recovered, 2),
        recovery_rate_percent=recovery_rate,
        total_invoices_count=total_inv_count,
        overdue_invoices_count=overdue_inv_count,
        in_negotiation_count=in_negotiation_count,
        paid_invoices_count=paid_inv_count,
        promises_created=promises_created,
        promises_kept=promises_kept,
        promises_broken=promises_broken,
        promises_pending=promises_pending,
        human_escalations_count=escalations,
        guardrail_blocks_count=guardrail_blocks,
        segment_breakdown=segment_data,
    )
