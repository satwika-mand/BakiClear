"""Financial Action Audit Log Pydantic Schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActionLogCreate(BaseModel):
    invoice_id: str
    action_type: str  # discount_offer, due_date_extension, payment_plan, escalation
    decision: str  # approved, rejected, escalated
    reason: str
    actor: str  # ai_agent, policy_engine, human_agent
    requested_value: str | None = None
    approved_value: str | None = None
    session_id: str | None = None
    idempotency_key: str | None = None


class ActionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    action_id: str
    session_id: str | None = None
    invoice_id: str
    action_type: str
    requested_value: str | None = None
    approved_value: str | None = None
    decision: str
    reason: str
    actor: str
    idempotency_key: str
    timestamp: datetime
