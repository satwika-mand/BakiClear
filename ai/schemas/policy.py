"""Merchant policy: the rulebook the Guardrail checks every ActionProposal
against. This is deterministic configuration, never LLM output."""

from pydantic import BaseModel, Field

from ai.schemas.enums import CustomerTier


class TierPolicyRule(BaseModel):
    """Limits that apply to one customer tier, e.g. GOLD vs WATCH_LIST."""

    tier: CustomerTier
    max_extension_days: int = Field(ge=0)
    max_discount_pct: float = Field(ge=0, le=100)
    requires_human_approval_if_disputed: bool = True
    requires_human_approval_if_broken_promises_gte: int = Field(
        default=2, description="broken_promise_count at or above this forces human approval"
    )


class MerchantPolicy(BaseModel):
    policy_id: str
    rules_by_tier: dict[CustomerTier, TierPolicyRule]

    def rule_for(self, tier: CustomerTier) -> TierPolicyRule:
        return self.rules_by_tier[tier]
