"""Collection Strategy Agent. Gemini structured output.

Produces a PROPOSAL only — CollectionStrategy has no authority of its own.
Any concession it suggests still has to pass through the guardrail once a
customer actually negotiates one."""

from ai.llm import generate_structured
from ai.prompts.strategy import SYSTEM_INSTRUCTION, build_prompt
from ai.schemas import (
    CollectionStrategy,
    CustomerIntelligence,
    CustomerProfile,
    Invoice,
    PaymentBehavior,
    RiskAssessment,
)


def propose_strategy(
    customer: CustomerProfile,
    invoice: Invoice,
    intelligence: CustomerIntelligence,
    behavior: PaymentBehavior,
    risk: RiskAssessment,
) -> CollectionStrategy:
    prompt = build_prompt(
        customer_name=customer.name,
        tier=customer.tier.value,
        tenure_months=intelligence.tenure_months,
        lifetime_value=intelligence.lifetime_value,
        relationship_summary=intelligence.relationship_summary,
        invoice_amount=invoice.amount_due,
        days_overdue=invoice.days_overdue,
        behavioral_summary=behavior.behavioral_summary,
        on_time_payment_pct=behavior.on_time_payment_pct,
        risk_level=risk.risk_level.value,
        priority_level=risk.priority_level.value,
        contributing_factors=risk.contributing_factors,
    )
    strategy = generate_structured(
        prompt, CollectionStrategy, system_instruction=SYSTEM_INSTRUCTION
    )
    # Belt-and-braces: the LLM sometimes drops/renames these join keys even
    # with a schema — force them to the values we actually asked about.
    return strategy.model_copy(update={"invoice_id": invoice.invoice_id, "customer_id": customer.customer_id})
