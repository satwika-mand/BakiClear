"""Financial Actions Audit Log Router."""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.action_log import ActionLog
from backend.app.models.invoice import Invoice
from backend.app.schemas.action import ActionLogCreate, ActionLogResponse
from backend.app.services.action_service import log_action

router = APIRouter(prefix="/api/actions", tags=["Financial Actions Audit Trail"])


@router.get("", response_model=list[ActionLogResponse])
def list_actions(
    invoice_id: str | None = Query(None),
    session_id: str | None = Query(None),
    actor: str | None = Query(None, description="ai_agent, policy_engine, human_agent"),
    decision: str | None = Query(None, description="approved, rejected, escalated"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve financial action audit trail with optional filtering."""
    stmt = select(ActionLog)
    if invoice_id:
        stmt = stmt.where(ActionLog.invoice_id == invoice_id)
    if session_id:
        stmt = stmt.where(ActionLog.session_id == session_id)
    if actor:
        stmt = stmt.where(ActionLog.actor == actor)
    if decision:
        stmt = stmt.where(ActionLog.decision == decision)

    stmt = stmt.order_by(ActionLog.timestamp.desc()).offset(offset).limit(limit)
    actions = db.scalars(stmt).all()
    return actions


@router.post("", response_model=ActionLogResponse, status_code=status.HTTP_201_CREATED)
def record_action(
    action_in: ActionLogCreate,
    db: Session = Depends(get_db),
):
    """Persist financial action decision with strict idempotency verification."""
    inv = db.get(Invoice, action_in.invoice_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{action_in.invoice_id}' not found.",
        )

    action_record, _is_new = log_action(
        db,
        invoice_id=action_in.invoice_id,
        action_type=action_in.action_type,
        decision=action_in.decision,
        reason=action_in.reason,
        actor=action_in.actor,
        requested_value=action_in.requested_value,
        approved_value=action_in.approved_value,
        session_id=action_in.session_id,
        idempotency_key=action_in.idempotency_key,
    )
    return action_record
