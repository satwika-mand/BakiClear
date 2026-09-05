"""Razorpay Standard Checkout order and verification endpoints."""

import json
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.action_log import ActionLog
from backend.app.models.agent_trace import AgentTrace
from backend.app.models.invoice import Invoice
from backend.app.models.payment_history import PaymentHistory
from backend.app.models.promise import PromiseToPay
from backend.app.services.razorpay_adapter import razorpay_adapter

router = APIRouter(prefix="/api/negotiations", tags=["Razorpay Payments"])


class Verification(BaseModel):
    razorpay_payment_id: str = Field(min_length=1, max_length=100)
    razorpay_order_id: str = Field(min_length=1, max_length=100)
    razorpay_signature: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=255)


def _approved_promise(invoice_id: str, db: Session) -> PromiseToPay:
    """A pending promise is an approved commitment awaiting payment."""
    promise = db.scalars(select(PromiseToPay).where(PromiseToPay.invoice_id == invoice_id, PromiseToPay.status == "pending").order_by(PromiseToPay.created_at.desc())).first()
    if not promise:
        raise HTTPException(status_code=409, detail="No approved pending promise exists for this invoice.")
    return promise


@router.post("/{invoice_id}/create-order")
def create_order(invoice_id: str, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    promise = _approved_promise(invoice_id, db)
    if promise.razorpay_order_id:
        amount_paise = int((Decimal(str(promise.amount)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return {"order_id": promise.razorpay_order_id, "amount": amount_paise, "currency": "INR", "key_id": razorpay_adapter.key_id}
    amount_paise = int((Decimal(str(promise.amount)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    try:
        order = razorpay_adapter.create_order(amount_paise=amount_paise, receipt=f"baki-{promise.promise_id}"[:40])
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to create Razorpay order.") from exc
    promise.razorpay_order_id = order["id"]
    db.commit()
    return {"order_id": order["id"], "amount": amount_paise, "currency": "INR", "key_id": razorpay_adapter.key_id}


@router.post("/{invoice_id}/verify-payment")
def verify_payment(invoice_id: str, payload: Verification, db: Session = Depends(get_db)):
    # An idempotency retry happens after the promise has moved to ``kept``;
    # check the durable action log before looking for an awaiting-payment promise.
    existing_action = db.scalars(
        select(ActionLog).where(ActionLog.idempotency_key == payload.idempotency_key)
    ).first()
    if existing_action:
        existing_promise = db.scalars(
            select(PromiseToPay).where(PromiseToPay.razorpay_order_id == payload.razorpay_order_id)
        ).first()
        if existing_promise and existing_promise.invoice_id == invoice_id and existing_promise.razorpay_payment_id == payload.razorpay_payment_id:
            return {"status": "paid", "payment_id": payload.razorpay_payment_id, "idempotent": True}
        raise HTTPException(status_code=409, detail="Idempotency key was already used for another payment event.")

    # SQLAlchemy begins a read transaction for the idempotency lookup above;
    # close it before entering the explicit atomic financial transaction.
    db.rollback()
    with db.begin():
        promise = db.scalars(
            select(PromiseToPay)
            .where(PromiseToPay.invoice_id == invoice_id, PromiseToPay.status == "pending")
            .order_by(PromiseToPay.created_at.desc())
            .with_for_update()
        ).first()
        if not promise:
            raise HTTPException(status_code=409, detail="No approved pending promise exists for this invoice.")
        if promise.razorpay_payment_id:
            return {"status": "paid", "payment_id": promise.razorpay_payment_id, "idempotent": True}
        if promise.razorpay_order_id != payload.razorpay_order_id:
            raise HTTPException(status_code=400, detail="Order does not belong to this promise.")
        if not razorpay_adapter.verify_signature(order_id=promise.razorpay_order_id, payment_id=payload.razorpay_payment_id, signature=payload.razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid Razorpay payment signature.")
        invoice = db.get(Invoice, invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        promise.status, promise.razorpay_payment_id = "kept", payload.razorpay_payment_id
        invoice.status, invoice.paid_date, invoice.days_overdue = "paid", date.today(), 0
        db.add(PaymentHistory(
            customer_id=promise.customer_id, invoice_id=invoice_id, amount=promise.amount,
            due_date=invoice.due_date, paid_date=date.today(),
            days_to_pay=max(0, (date.today() - invoice.due_date).days), status="delayed" if invoice.due_date < date.today() else "on_time",
        ))
        db.add(ActionLog(action_id=f"ACT_{uuid.uuid4().hex[:10].upper()}", invoice_id=invoice_id,
            action_type="razorpay_payment_verification", decision="approved", reason="Razorpay signature verified",
            actor="payment_gateway", idempotency_key=payload.idempotency_key))
        db.add(AgentTrace(trace_id=f"TRC_{uuid.uuid4().hex[:12].upper()}", invoice_id=invoice_id,
            event_type="payment_verified", payload=json.dumps({"order_id": promise.razorpay_order_id, "payment_id": payload.razorpay_payment_id})))
    return {"status": "paid", "payment_id": payload.razorpay_payment_id, "idempotent": False}


@router.get("/{invoice_id}/status")
def payment_status(invoice_id: str, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    promise = db.scalars(select(PromiseToPay).where(PromiseToPay.invoice_id == invoice_id).order_by(PromiseToPay.created_at.desc())).first()
    return {"invoice_id": invoice_id, "invoice_status": invoice.status, "promise_status": promise.status if promise else None, "order_id": promise.razorpay_order_id if promise else None}
