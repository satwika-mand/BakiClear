"""The trust boundary contracts. ActionProposal is what Strategy/Negotiation
produce; GuardrailDecision is what pure Python (ai/guardrails/) returns.

No LLM ever constructs a GuardrailDecision, and no ActionProposal reaches the
Action Executor without one."""

from pydantic import BaseModel, Field

from ai.schemas.enums import ActionType, CustomerTier, GuardrailVerdict


class ActionProposal(BaseModel):
    """A concrete, financially-meaningful action a prior agent wants to take.
    This is a PROPOSAL — it has no authority until the Guardrail rules on it."""

    invoice_id: str
    customer_id: str
    action_type: ActionType
    proposed_extension_days: int = Field(default=0, ge=0)
    proposed_discount_pct: float = Field(default=0, ge=0, le=100)
    proposed_amount: float | None = Field(
        default=None, description="Final amount to collect, if different from invoice amount_due"
    )
    source_agent: str = Field(description="e.g. 'collection_strategy' or 'negotiation'")
    rationale: str


class CustomerFacts(BaseModel):
    """The minimal facts the Guardrail needs to evaluate a proposal. Kept
    separate from CustomerIntelligence/PaymentBehavior so the guardrail's
    function signature stays small and dependency-free."""

    tier: CustomerTier
    has_open_dispute: bool
    broken_promise_count: int


class GuardrailDecision(BaseModel):
    verdict: GuardrailVerdict
    original_proposal: ActionProposal
    modified_proposal: ActionProposal | None = Field(
        default=None, description="Set only when verdict is MODIFY"
    )
    reason: str = Field(description="Human-readable explanation, shown in the UI policy panel")
