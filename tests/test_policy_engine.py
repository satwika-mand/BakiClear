"""The guardrail is the whole architectural claim of this project. These tests
cover all four verdicts explicitly."""

from ai.guardrails.policy_engine import evaluate
from ai.orchestration.mock_provider import MockContextProvider
from ai.schemas import ActionProposal, ActionType, CustomerFacts, CustomerTier, GuardrailVerdict


def _policy():
    return MockContextProvider().get_policy()


def test_allow_within_gold_limits():
    proposal = ActionProposal(
        invoice_id="INV-1001",
        customer_id="CUST-001",
        action_type=ActionType.RECORD_PROMISE,
        proposed_extension_days=10,
        proposed_discount_pct=2,
        source_agent="negotiation",
        rationale="customer asked for 10 more days",
    )
    facts = CustomerFacts(tier=CustomerTier.GOLD, has_open_dispute=False, broken_promise_count=0)

    decision = evaluate(proposal, _policy(), facts)

    assert decision.verdict == GuardrailVerdict.ALLOW
    assert decision.modified_proposal is None


def test_modify_clamps_to_standard_tier_max():
    proposal = ActionProposal(
        invoice_id="INV-1002",
        customer_id="CUST-002",
        action_type=ActionType.RECORD_PROMISE,
        proposed_extension_days=20,
        proposed_discount_pct=8,
        source_agent="negotiation",
        rationale="customer wants a big break",
    )
    facts = CustomerFacts(tier=CustomerTier.STANDARD, has_open_dispute=False, broken_promise_count=0)

    decision = evaluate(proposal, _policy(), facts)

    assert decision.verdict == GuardrailVerdict.MODIFY
    assert decision.modified_proposal.proposed_extension_days == 7
    assert decision.modified_proposal.proposed_discount_pct == 2


def test_reject_zero_tolerance_watch_list_with_no_flags():
    """A watch-list customer with no dispute/broken-promise history still gets
    a hard REJECT for any concession — the tier itself has zero tolerance."""
    proposal = ActionProposal(
        invoice_id="INV-9001",
        customer_id="CUST-999",
        action_type=ActionType.RECORD_PROMISE,
        proposed_discount_pct=5,
        source_agent="negotiation",
        rationale="customer asked for a small discount",
    )
    facts = CustomerFacts(tier=CustomerTier.WATCH_LIST, has_open_dispute=False, broken_promise_count=0)

    decision = evaluate(proposal, _policy(), facts)

    assert decision.verdict == GuardrailVerdict.REJECT
    assert decision.modified_proposal is None


def test_human_approval_for_open_dispute_orion_scenario():
    """CUST-003 (Orion): open dispute forces human approval before any
    negotiation, regardless of what is being proposed."""
    proposal = ActionProposal(
        invoice_id="INV-2001",
        customer_id="CUST-003",
        action_type=ActionType.RECORD_PROMISE,
        proposed_discount_pct=15,
        source_agent="negotiation",
        rationale="customer demanded 15% off or threatened to walk",
    )
    facts = CustomerFacts(tier=CustomerTier.WATCH_LIST, has_open_dispute=True, broken_promise_count=2)

    decision = evaluate(proposal, _policy(), facts)

    assert decision.verdict == GuardrailVerdict.HUMAN_APPROVAL


def test_human_approval_for_broken_promises_without_dispute():
    proposal = ActionProposal(
        invoice_id="INV-3001",
        customer_id="CUST-777",
        action_type=ActionType.RECORD_PROMISE,
        proposed_extension_days=3,
        source_agent="negotiation",
        rationale="small extension request",
    )
    facts = CustomerFacts(tier=CustomerTier.STANDARD, has_open_dispute=False, broken_promise_count=2)

    decision = evaluate(proposal, _policy(), facts)

    assert decision.verdict == GuardrailVerdict.HUMAN_APPROVAL


def test_non_financial_action_always_allowed():
    proposal = ActionProposal(
        invoice_id="INV-1001",
        customer_id="CUST-001",
        action_type=ActionType.ESCALATE_TO_HUMAN,
        source_agent="negotiation",
        rationale="customer requested a human",
    )
    facts = CustomerFacts(tier=CustomerTier.WATCH_LIST, has_open_dispute=True, broken_promise_count=5)

    decision = evaluate(proposal, _policy(), facts)

    assert decision.verdict == GuardrailVerdict.ALLOW
