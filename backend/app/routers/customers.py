"""Customers API Router."""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.database import get_db
from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.models.payment_history import PaymentHistory
from backend.app.models.policy import PolicyConfig
from backend.app.schemas.customer import (
    AIContextResponse,
    AICustomerContext,
    AIInvoiceContext,
    AIPaymentHistoryContext,
    AIPolicyBoundsContext,
    AIRiskAssessmentContext,
    CustomerHistoryResponse,
    CustomerResponse,
    PaymentHistoryItem,
)
from backend.app.services.analytics import calculate_payment_metrics, calculate_risk_priority

router = APIRouter(prefix="/api/customers", tags=["Customers"])


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    """Retrieve full customer profile."""
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{customer_id}' not found.",
        )
    return customer


@router.get("/{customer_id}/history", response_model=CustomerHistoryResponse)
def get_customer_history(customer_id: str, db: Session = Depends(get_db)):
    """Retrieve customer's complete payment ledger and aggregated behavioral metrics."""
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{customer_id}' not found.",
        )

    stmt = (
        select(PaymentHistory)
        .where(PaymentHistory.customer_id == customer_id)
        .order_by(PaymentHistory.due_date.desc())
    )
    records = db.scalars(stmt).all()
    metrics = calculate_payment_metrics(records, customer.promises)

    history_items = [
        PaymentHistoryItem(
            id=r.id,
            invoice_id=r.invoice_id,
            amount=r.amount,
            due_date=r.due_date.isoformat(),
            paid_date=r.paid_date.isoformat() if r.paid_date else None,
            days_to_pay=r.days_to_pay,
            status=r.status,
            disputed=r.disputed,
        )
        for r in records
    ]

    return CustomerHistoryResponse(
        customer_id=customer_id,
        total_records=len(records),
        on_time_percentage=metrics["on_time_percentage"],
        average_payment_delay=metrics["average_payment_delay"],
        disputes=metrics["disputes"],
        broken_promises=metrics["broken_promises"],
        records=history_items,
    )


@router.get("/{customer_id}/context", response_model=AIContextResponse)
def get_customer_ai_context(
    customer_id: str,
    invoice_id: str | None = Query(None, description="Target invoice ID. If omitted, the most urgent overdue invoice is selected."),
    db: Session = Depends(get_db),
):
    """Rich financial and behavioral context endpoint specifically designed for Person 2's AI Workflow.

    Supplies verified deterministic facts, customer intelligence, risk score, and merchant policy limits.
    """
    stmt = (
        select(Customer)
        .where(Customer.customer_id == customer_id)
        .options(
            joinedload(Customer.invoices),
            joinedload(Customer.payment_records),
            joinedload(Customer.promises),
        )
    )
    customer = db.scalars(stmt).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{customer_id}' not found.",
        )

    # Resolve target invoice
    target_invoice: Invoice | None = None
    if invoice_id:
        target_invoice = next((inv for inv in customer.invoices if inv.invoice_id == invoice_id), None)
        if not target_invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice '{invoice_id}' does not belong to customer '{customer_id}'.",
            )
    else:
        # Default to the invoice with the highest days_overdue
        overdue_invoices = [inv for inv in customer.invoices if inv.status == "overdue"]
        if overdue_invoices:
            target_invoice = max(overdue_invoices, key=lambda inv: inv.days_overdue)
        elif customer.invoices:
            target_invoice = customer.invoices[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No invoices found for customer '{customer_id}'.",
            )

    # Compute deterministic metrics
    metrics = calculate_payment_metrics(customer.payment_records, customer.promises)
    risk_data = calculate_risk_priority(customer, target_invoice, metrics)

    # Fetch policy limits for segment
    policy = db.get(PolicyConfig, customer.segment)
    max_disc = policy.max_discount_percent if policy else 0.0
    max_ext = policy.max_extension_days if policy else 0
    req_human = policy.requires_human_approval if policy else True
    pol_enabled = policy.enabled if policy else True

    return AIContextResponse(
        invoice=AIInvoiceContext(
            invoice_id=target_invoice.invoice_id,
            amount=target_invoice.amount,
            days_overdue=target_invoice.days_overdue,
            status=target_invoice.status,
        ),
        customer=AICustomerContext(
            customer_id=customer.customer_id,
            name=customer.name,
            segment=customer.segment,
            tenure_months=customer.tenure_months,
            lifetime_value=customer.lifetime_value,
            relationship_criticality=customer.relationship_criticality,
        ),
        payment_history=AIPaymentHistoryContext(
            on_time_percentage=metrics["on_time_percentage"],
            average_payment_delay=metrics["average_payment_delay"],
            disputes=metrics["disputes"],
            broken_promises=metrics["broken_promises"],
            total_payments_recorded=metrics["total_payments_recorded"],
        ),
        risk_assessment=AIRiskAssessmentContext(
            risk_score=risk_data["risk_score"],
            risk_tier=risk_data["risk_tier"],
            priority=risk_data["priority"],
            recommended_action=risk_data["recommended_action"],
            score_breakdown=risk_data["score_breakdown"],
        ),
        policy_bounds=AIPolicyBoundsContext(
            max_discount_percent=max_disc,
            max_extension_days=max_ext,
            requires_human_approval=req_human,
            enabled=pol_enabled,
        ),
    )
