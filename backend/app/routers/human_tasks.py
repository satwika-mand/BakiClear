"""Small human handoff queue API; deliberately not a CRM."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.database import get_db
from backend.app.models.human_task import HumanTask
from backend.app.models.invoice import Invoice
from backend.app.models.message import Message
from backend.app.models.negotiation import NegotiationSession
from backend.app.models.payment_history import PaymentHistory
from backend.app.models.promise import PromiseToPay
from backend.app.services.analytics import calculate_payment_metrics, calculate_risk_priority

router = APIRouter(prefix="/api/human-tasks", tags=["Human Collection Handoff"])


class Assignment(BaseModel):
    assigned_to: str = Field(min_length=1, max_length=255)


class Note(BaseModel):
    note: str = Field(min_length=1, max_length=4000)


def _task(task_id: str, db: Session) -> HumanTask:
    task = db.get(HumanTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Human task '{task_id}' not found.")
    return task


@router.get("")
def list_human_tasks(db: Session = Depends(get_db)):
    return db.scalars(select(HumanTask).order_by(HumanTask.created_at.desc())).all()


@router.get("/{task_id}")
def get_human_task(task_id: str, db: Session = Depends(get_db)):
    task = _task(task_id, db)
    invoice = db.scalars(
        select(Invoice).where(Invoice.invoice_id == task.invoice_id).options(joinedload(Invoice.customer))
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Task invoice no longer exists.")
    customer = invoice.customer
    history = db.scalars(select(PaymentHistory).where(PaymentHistory.customer_id == customer.customer_id)).all()
    promises = db.scalars(select(PromiseToPay).where(PromiseToPay.invoice_id == invoice.invoice_id)).all()
    messages = db.scalars(select(Message).where(Message.invoice_id == invoice.invoice_id).order_by(Message.sent_at)).all()
    sessions = db.scalars(
        select(NegotiationSession).where(NegotiationSession.invoice_id == invoice.invoice_id)
        .options(joinedload(NegotiationSession.turns))
    ).unique().all()
    metrics = calculate_payment_metrics(history, promises)
    return {
        "task": task,
        "customer": customer,
        "invoice": invoice,
        "amount": invoice.amount,
        "days_overdue": invoice.days_overdue,
        "risk": calculate_risk_priority(customer, invoice, metrics),
        "payment_history": history,
        "previous_promises": promises,
        "messages": messages,
        "conversation_history": [turn for session in sessions for turn in session.turns],
        "reason_for_escalation": task.reason,
        "ai_recommendation": "Review the payment history and approve, reject, or negotiate the next action.",
    }


@router.post("/{task_id}/assign")
def assign_human_task(task_id: str, payload: Assignment, db: Session = Depends(get_db)):
    task = _task(task_id, db)
    task.assigned_to, task.status = payload.assigned_to, "assigned"
    db.commit(); db.refresh(task)
    return task


@router.post("/{task_id}/notes")
def add_human_task_note(task_id: str, payload: Note, db: Session = Depends(get_db)):
    task = _task(task_id, db)
    task.notes = f"{task.notes}\n{payload.note}" if task.notes else payload.note
    db.commit(); db.refresh(task)
    return task


@router.post("/{task_id}/resolve")
def resolve_human_task(task_id: str, db: Session = Depends(get_db)):
    task = _task(task_id, db)
    task.status, task.resolved_at = "resolved", datetime.now()
    db.commit(); db.refresh(task)
    return task
