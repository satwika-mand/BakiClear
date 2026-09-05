"""Customer profile (input, from backend/mock) and CustomerIntelligence (agent output)."""

from datetime import date

from pydantic import BaseModel, Field

from ai.schemas.enums import CustomerSegment, CustomerTier


class CustomerProfile(BaseModel):
    """Raw customer facts as they come from the backend/mock context provider."""

    customer_id: str
    name: str
    segment: CustomerSegment
    tier: CustomerTier
    customer_since: date
    lifetime_value: float = Field(description="Total historical revenue from this customer")
    contact_email: str | None = None
    contact_phone: str | None = None


class CustomerIntelligence(BaseModel):
    """Output of the Customer Intelligence Agent: the relationship read that
    feeds Strategy. Numeric fields (tenure, LTV) are computed in Python;
    `relationship_summary` is the one field worth spending an LLM call on."""

    customer_id: str
    tenure_months: int
    lifetime_value: float
    segment: CustomerSegment
    tier: CustomerTier
    relationship_criticality: str = Field(
        description="Low/Medium/High — how much this relationship matters to retain"
    )
    relationship_summary: str = Field(
        description="One or two sentences of qualitative context an agent can use "
        "when choosing tone, e.g. long-standing high-value customer vs new low-tenure account"
    )
