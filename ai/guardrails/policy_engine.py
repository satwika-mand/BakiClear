"""The Guardrail. PURE PYTHON — no LLM, no network, no I/O.

evaluate() is a pure function: (ActionProposal, MerchantPolicy, CustomerFacts)
-> GuardrailDecision. Nothing upstream of this file can authorize a financial
concession; nothing downstream of it can execute one without passing through
it first. This is PRINCIPLE 2 made literal.

Decision precedence (checked in this order):
  1. Non-financial actions (escalate/no-op) always ALLOW — nothing to guard.
  2. An open dispute forces HUMAN_APPROVAL if the tier's policy requires it —
     a human must resolve the dispute before the AI negotiates further.
  3. Too many broken promises forces HUMAN_APPROVAL for the same reason.
  4. A tier with zero autonomous tolerance (max = 0) REJECTs any positive
     concession outright — there is nothing sensible to modify it down to.
  5. A concession that exceeds the tier's max is MODIFIED down to that max.
  6. Otherwise, ALLOW as proposed.
"""

from ai.schemas import (
    ActionProposal,
    ActionType,
    CustomerFacts,
    GuardrailDecision,
    GuardrailVerdict,
    MerchantPolicy,
)

_NON_FINANCIAL_ACTIONS = {ActionType.ESCALATE_TO_HUMAN, ActionType.NO_ACTION}


def evaluate(
    proposal: ActionProposal,
    policy: MerchantPolicy,
    facts: CustomerFacts,
) -> GuardrailDecision:
    if proposal.action_type in _NON_FINANCIAL_ACTIONS:
        return GuardrailDecision(
            verdict=GuardrailVerdict.ALLOW,
            original_proposal=proposal,
            reason="Non-financial action; no guardrail check required.",
        )

    rule = policy.rule_for(facts.tier)

    if facts.has_open_dispute and rule.requires_human_approval_if_disputed:
        return GuardrailDecision(
            verdict=GuardrailVerdict.HUMAN_APPROVAL,
            original_proposal=proposal,
            reason=(
                f"Customer has an open unresolved dispute; {facts.tier.value} policy "
                "requires human approval before any concession is offered."
            ),
        )

    if facts.broken_promise_count >= rule.requires_human_approval_if_broken_promises_gte:
        return GuardrailDecision(
            verdict=GuardrailVerdict.HUMAN_APPROVAL,
            original_proposal=proposal,
            reason=(
                f"Customer has {facts.broken_promise_count} broken promise(s), at or above the "
                f"{rule.requires_human_approval_if_broken_promises_gte} threshold for "
                f"{facts.tier.value} tier; human approval required."
            ),
        )

    exceeds_extension = proposal.proposed_extension_days > rule.max_extension_days
    exceeds_discount = proposal.proposed_discount_pct > rule.max_discount_pct

    if not exceeds_extension and not exceeds_discount:
        return GuardrailDecision(
            verdict=GuardrailVerdict.ALLOW,
            original_proposal=proposal,
            reason=(
                f"Proposed extension ({proposal.proposed_extension_days}d) and discount "
                f"({proposal.proposed_discount_pct}%) are within {facts.tier.value} policy limits "
                f"(max {rule.max_extension_days}d, {rule.max_discount_pct}%)."
            ),
        )

    zero_tolerance_extension = rule.max_extension_days == 0 and proposal.proposed_extension_days > 0
    zero_tolerance_discount = rule.max_discount_pct == 0 and proposal.proposed_discount_pct > 0

    if zero_tolerance_extension or zero_tolerance_discount:
        return GuardrailDecision(
            verdict=GuardrailVerdict.REJECT,
            original_proposal=proposal,
            reason=(
                f"{facts.tier.value} tier permits zero autonomous concessions "
                f"(max {rule.max_extension_days}d, {rule.max_discount_pct}%); proposal rejected outright."
            ),
        )

    modified = proposal.model_copy(
        update={
            "proposed_extension_days": min(proposal.proposed_extension_days, rule.max_extension_days),
            "proposed_discount_pct": min(proposal.proposed_discount_pct, rule.max_discount_pct),
        }
    )
    return GuardrailDecision(
        verdict=GuardrailVerdict.MODIFY,
        original_proposal=proposal,
        modified_proposal=modified,
        reason=(
            f"Proposed extension ({proposal.proposed_extension_days}d) / discount "
            f"({proposal.proposed_discount_pct}%) exceeds {facts.tier.value} policy limits "
            f"(max {rule.max_extension_days}d, {rule.max_discount_pct}%); capped to policy maximum."
        ),
    )
