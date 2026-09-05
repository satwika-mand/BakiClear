"""A commitment turned into a tracked obligation, created only after a
GuardrailDecision has authorized the underlying terms."""

from datetime import date, datetime

from pydantic import BaseModel

from ai.schemas.enums import PromiseStatus


class PromiseToPay(BaseModel):
    promise_id: str
    invoice_id: str
    customer_id: str
    amount: float
    due_date: date
    status: PromiseStatus = PromiseStatus.PENDING
    created_at: datetime
    guardrail_decision_reason: str
