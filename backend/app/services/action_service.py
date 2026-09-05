"""Action persistence and idempotency enforcement service."""

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.action_log import ActionLog


def generate_idempotency_key(invoice_id: str, action_type: str, action_date: date | None = None) -> str:
    """Generate default deterministic idempotency key for financial actions."""
    d = action_date or date.today()
    return f"{invoice_id}:{action_type}:{d.isoformat()}"


def log_action(
    db: Session,
    *,
    invoice_id: str,
    action_type: str,
    decision: str,
    reason: str,
    actor: str,
    requested_value: str | None = None,
    approved_value: str | None = None,
    session_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[ActionLog, bool]:
    """Persist financial action with idempotency guarantee.

    Returns:
        tuple[ActionLog, bool]: (action_log_record, is_newly_created)
    """
    key = idempotency_key or generate_idempotency_key(invoice_id, action_type)

    # Check for existing action with identical key
    stmt = select(ActionLog).where(ActionLog.idempotency_key == key)
    existing = db.scalars(stmt).first()
    if existing:
        return existing, False

    action_id = f"ACT_{uuid.uuid4().hex[:10].upper()}"
    new_action = ActionLog(
        action_id=action_id,
        session_id=session_id,
        invoice_id=invoice_id,
        action_type=action_type,
        requested_value=requested_value,
        approved_value=approved_value,
        decision=decision,
        reason=reason,
        actor=actor,
        idempotency_key=key,
        timestamp=datetime.now(),
    )
    db.add(new_action)
    db.commit()
    db.refresh(new_action)
    return new_action, True
