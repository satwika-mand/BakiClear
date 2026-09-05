"""Negotiation Session and Turn Pydantic Schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TurnCreate(BaseModel):
    speaker: str  # ai, customer, system
    message: str
    intent: str | None = None


class TurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: str
    speaker: str
    message: str
    intent: str | None = None
    timestamp: datetime


class SessionCreate(BaseModel):
    invoice_id: str
    customer_id: str | None = None
    channel: str = "chat"


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    invoice_id: str
    customer_id: str
    channel: str
    status: str
    created_at: datetime
    updated_at: datetime
    turns: list[TurnResponse] = []
