"""Shared, idempotent human-collection handoff creation."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.agent_trace import AgentTrace
from backend.app.models.human_task import HumanTask


def create_human_task(db: Session, *, invoice_id: str, customer_id: str, reason: str, priority: str = "high") -> HumanTask:
    existing = db.scalars(
        select(HumanTask).where(HumanTask.invoice_id == invoice_id, HumanTask.status.in_(["open", "assigned"]))
    ).first()
    if existing:
        return existing
    task = HumanTask(
        task_id=f"HT_{uuid.uuid4().hex[:12].upper()}", invoice_id=invoice_id,
        customer_id=customer_id, reason=reason, priority=priority,
    )
    db.add(task)
    db.add(AgentTrace(
        trace_id=f"TRC_{uuid.uuid4().hex[:12].upper()}", invoice_id=invoice_id,
        event_type="human_escalation", payload=json.dumps({"reason": reason, "priority": priority}),
    ))
    return task
