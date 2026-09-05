"""Audit trail entry: every guardrail decision, ALLOW or otherwise, gets one.
This is what makes the system auditable — nothing is decided silently."""

from datetime import datetime

from pydantic import BaseModel

from ai.schemas.guardrail import GuardrailDecision


class AuditLogEntry(BaseModel):
    timestamp: datetime
    decision: GuardrailDecision
