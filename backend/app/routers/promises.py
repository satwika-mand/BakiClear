"""Promise To Pay API Router."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.models.payment_history import PaymentHistory
from backend.app.models.policy import PolicyConfig
from backend.app.models.promise import PromiseToPay
from backend.app.schemas.promise import PromiseCreate, PromiseMarkPaid, PromiseResponse
from backend.app.services.guardrail import policy_for, validate_commitment
from backend.app.services.handoff import create_human_task

router = APIRouter(prefix="/api/promises", tags=["Promises To Pay"])


@router.get("", response_model=list[PromiseResponse])
def list_promises(
    status_filter: str | None = Query(None, alias="status", description="Filter by status: pending, kept, broken"),
    invoice_id: str | None = Query(None),
    customer_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List promises to pay with optional status, invoice, or customer filters."""
    stmt = select(PromiseToPay)
    if status_filter:
        stmt = stmt.where(PromiseToPay.status == status_filter)
    if invoice_id:
        stmt = stmt.where(PromiseToPay.invoice_id == invoice_id)
    if customer_id:
        stmt = stmt.where(PromiseToPay.customer_id == customer_id)

    stmt = stmt.order_by(PromiseToPay.promised_date.asc())
    promises = db.scalars(stmt).all()
    return promises


@router.post("", response_model=PromiseResponse, status_code=status.HTTP_201_CREATED)
def create_promise(promise_in: PromiseCreate, db: Session = Depends(get_db)):
    """Create a new Promise To Pay commitment extracted by AI or confirmed by customer."""
    # Validate invoice
    inv = db.get(Invoice, promise_in.invoice_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{promise_in.invoice_id}' not found.",
        )

    # Validate customer
    cust = db.get(Customer, promise_in.customer_id)
    if not cust:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{promise_in.customer_id}' not found.",
        )

    stored_policy = db.get(PolicyConfig, cust.segment)
    bounds = (
        {
            "max_discount_percent": stored_policy.max_discount_percent,
            "max_extension_days": stored_policy.max_extension_days,
        }
        if stored_policy
        else policy_for(cust.segment)
    )
    verdict = validate_commitment(
        {
            "amount": promise_in.amount,
            "invoice_amount": inv.amount,
            "promised_date": promise_in.promised_date,
            "days_overdue": inv.days_overdue,
            "segment": cust.segment,
            "has_open_dispute": db.scalars(
                select(PaymentHistory).where(
                    PaymentHistory.customer_id == cust.customer_id,
                    PaymentHistory.disputed.is_(True),
                    PaymentHistory.paid_date.is_(None),
                )
            ).first() is not None,
            "broken_promise_count": len(
                db.scalars(
                    select(PromiseToPay).where(
                        PromiseToPay.customer_id == cust.customer_id,
                        PromiseToPay.status == "broken",
                    )
                ).all()
            ),
        },
        bounds,
    )
    if verdict["route_to_human"]:
        create_human_task(
            db, invoice_id=inv.invoice_id, customer_id=cust.customer_id,
            reason=verdict["reason"], priority="urgent",
        )
        # A full-value payment commitment is safe to record; the task prevents
        # any accompanying concession from being autonomous.
    if not verdict["allowed"] and not verdict["route_to_human"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=verdict["reason"])

    promise_id = f"PRM_{uuid.uuid4().hex[:8].upper()}"
    promise = PromiseToPay(
        promise_id=promise_id,
        invoice_id=promise_in.invoice_id,
        customer_id=promise_in.customer_id,
        amount=promise_in.amount,
        promised_date=promise_in.promised_date,
        status="pending",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(promise)
    db.commit()
    db.refresh(promise)
    return promise


@router.post("/{promise_id}/mark-paid", response_model=PromiseResponse)
def mark_promise_paid(
    promise_id: str,
    payload: PromiseMarkPaid | None = None,
    db: Session = Depends(get_db),
):
    """Mark a promise to pay as kept, simultaneously resolving the underlying invoice."""
    promise = db.get(PromiseToPay, promise_id)
    if not promise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promise '{promise_id}' not found.",
        )

    payment_date = payload.paid_date if payload and payload.paid_date else date.today()

    promise.status = "kept"
    promise.updated_at = datetime.now()

    # Update invoice status
    inv = db.get(Invoice, promise.invoice_id)
    if inv:
        inv.status = "paid"
        inv.paid_date = payment_date
        inv.days_overdue = 0
        inv.updated_at = datetime.now()

    db.commit()
    db.refresh(promise)
    return promise


@router.patch("/{promise_id}/status", response_model=PromiseResponse)
def update_promise_status(promise_id: str, status_value: str, db: Session = Depends(get_db)):
    """Update a promise outcome for the collections dashboard."""
    if status_value not in {"pending", "kept", "broken"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid promise status.")
    promise = db.get(PromiseToPay, promise_id)
    if not promise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Promise '{promise_id}' not found.")
    promise.status = status_value
    promise.updated_at = datetime.now()
    db.commit()
    db.refresh(promise)
    return promise
