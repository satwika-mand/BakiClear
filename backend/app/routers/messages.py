"""Read-only API for persisted simulated messaging."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.message import Message

router = APIRouter(prefix="/api/messages", tags=["Automated Messaging"])


@router.get("")
def list_messages(invoice_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Message)
    if invoice_id:
        stmt = stmt.where(Message.invoice_id == invoice_id)
    return db.scalars(stmt.order_by(Message.sent_at.desc())).all()
