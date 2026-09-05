"""Output of the Collection Strategy Agent. Gemini structured output.

This is a PROPOSAL — nothing here is authorized until the Guardrail evaluates
the ActionProposal it eventually leads to."""

from pydantic import BaseModel, Field

from ai.schemas.enums import CollectionChannel, CollectionTone


class CollectionStrategy(BaseModel):
    invoice_id: str
    customer_id: str
    recommended_channel: CollectionChannel
    tone: CollectionTone
    urgency: str = Field(description="Low/Medium/High/Critical")
    max_extension_days: int = Field(
        description="AI's suggested ceiling for an extension it would offer this customer"
    )
    max_discount_pct: float = Field(
        description="AI's suggested ceiling for a discount it would offer this customer"
    )
    requires_human_approval: bool = Field(
        description="AI's own judgment on whether a human should review before any offer is made"
    )
    recommended_approach: str = Field(
        description="One paragraph describing how the negotiation should open"
    )
    reasoning: str = Field(
        description="Why this strategy was chosen, referencing risk/behavior/relationship facts"
    )
