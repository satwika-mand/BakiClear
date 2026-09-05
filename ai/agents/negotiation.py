"""Negotiation Agent. Gemini structured output.

Understands the customer's ask and drafts a reply, but NegotiationResult is
still just a proposal — to_action_proposal() converts it into the exact shape
the Guardrail evaluates, and nothing here can authorize a concession."""

from ai.llm import generate_structured
from ai.prompts.negotiation import SYSTEM_INSTRUCTION, build_prompt
from ai.schemas import (
    ActionProposal,
    ActionType,
    CollectionStrategy,
    Invoice,
    NegotiationResult,
    NegotiationTurn,
)


def extract_negotiation_result(
    session_id: str,
    customer_name: str,
    invoice: Invoice,
    strategy: CollectionStrategy,
    conversation: list[NegotiationTurn],
    latest_customer_message: str,
) -> NegotiationResult:
    prompt = build_prompt(
        session_id=session_id,
        customer_name=customer_name,
        invoice_amount=invoice.amount_due,
        days_overdue=invoice.days_overdue,
        strategy_tone=strategy.tone.value,
        strategy_max_extension_days=strategy.max_extension_days,
        strategy_max_discount_pct=strategy.max_discount_pct,
        conversation=[(t.speaker, t.message) for t in conversation],
        latest_customer_message=latest_customer_message,
    )
    result = generate_structured(
        prompt, NegotiationResult, system_instruction=SYSTEM_INSTRUCTION
    )
    return result.model_copy(update={"session_id": session_id})


def to_action_proposal(
    result: NegotiationResult, invoice_id: str, customer_id: str
) -> ActionProposal:
    """The exact hand-off point to the Guardrail. Everything the negotiation
    agent understood gets compressed into the fields the policy engine checks —
    nothing else about the conversation carries any authority."""
    action_type = (
        ActionType.RECORD_PROMISE
        if result.commitment_detected
        else ActionType.SCHEDULE_FOLLOW_UP
    )
    return ActionProposal(
        invoice_id=invoice_id,
        customer_id=customer_id,
        action_type=action_type,
        proposed_extension_days=result.requested_extension_days,
        proposed_discount_pct=result.requested_discount_pct,
        proposed_amount=result.commitment_amount,
        source_agent="negotiation",
        rationale=f"Customer intent: {result.intent.value}. Sentiment: {result.customer_sentiment}.",
    )
