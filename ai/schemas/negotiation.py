"""Negotiation conversation turns and the structured result extracted from them.

The Negotiation Agent reasons over language, but everything it concludes
(NegotiationResult) is still just a proposal — the Guardrail decides."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ai.schemas.enums import NegotiationIntent


class NegotiationTurn(BaseModel):
    """One message in the conversation, in order."""

    speaker: Literal["customer", "ai"]
    message: str
    timestamp: datetime


class NegotiationResult(BaseModel):
    """Gemini structured output: what the AI understood from the conversation
    so far, extracted after each customer turn."""

    session_id: str
    intent: NegotiationIntent
    requested_extension_days: int = Field(default=0, ge=0)
    requested_discount_pct: float = Field(default=0, ge=0, le=100)
    customer_sentiment: str = Field(description="e.g. cooperative, frustrated, evasive")
    proposed_next_message: str = Field(
        description="The AI's suggested reply — still subject to guardrail-approved terms "
        "before it can mention any concrete concession"
    )
    commitment_detected: bool = Field(
        description="True if the customer has just agreed to a specific amount and date"
    )
    commitment_amount: float | None = None
    commitment_date: datetime | None = None
