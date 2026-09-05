"""The orchestrator. Two entry points cover the whole demo:

  assess_invoice(invoice_id)      -> everything the Queue/Intelligence/Strategy
                                      screens need for one invoice.
  negotiate_turn(assessment, ...) -> one negotiation exchange, all the way
                                      through the guardrail to an executed
                                      (or blocked) action.

Kept as plain functions, not a class — PRINCIPLE 6: nothing here needs state
beyond what's passed in explicitly."""

from dataclasses import dataclass

from ai.agents.action_executor import get_action_executor
from ai.agents.customer_intelligence import compute_intelligence
from ai.agents.negotiation import extract_negotiation_result, to_action_proposal
from ai.agents.risk_engine import (
    compute_payment_behavior,
    compute_risk_assessment,
    derive_customer_facts,
)
from ai.agents.strategy import propose_strategy
from ai.guardrails.policy_engine import evaluate
from ai.orchestration import get_context_provider
from ai.schemas import (
    ActionProposal,
    CollectionStrategy,
    CustomerFacts,
    CustomerIntelligence,
    CustomerProfile,
    GuardrailDecision,
    Invoice,
    MerchantPolicy,
    NegotiationResult,
    NegotiationTurn,
    PaymentBehavior,
    PromiseToPay,
    RiskAssessment,
)


@dataclass
class Assessment:
    """Bundles one invoice's full deterministic + AI read. Not a Pydantic
    schema — this is an internal orchestration convenience, not a contract
    crossing any agent/backend boundary."""

    customer: CustomerProfile
    invoice: Invoice
    intelligence: CustomerIntelligence
    behavior: PaymentBehavior
    facts: CustomerFacts
    risk: RiskAssessment
    strategy: CollectionStrategy
    policy: MerchantPolicy


@dataclass
class NegotiationOutcome:
    result: NegotiationResult
    proposal: ActionProposal
    decision: GuardrailDecision
    promise: PromiseToPay | None


@dataclass
class QuickRisk:
    """Risk/priority only — no Gemini call. Backs the collection queue screen,
    which renders every overdue invoice and must not cost an LLM call per row."""

    customer: CustomerProfile
    invoice: Invoice
    risk: RiskAssessment


def quick_risk(invoice_id: str) -> QuickRisk:
    provider = get_context_provider()
    invoice = provider.get_invoice(invoice_id)
    customer = provider.get_customer(invoice.customer_id)
    history = provider.get_payment_history(customer.customer_id)
    behavior = compute_payment_behavior(customer.customer_id, history)
    facts = derive_customer_facts(customer, history)
    risk = compute_risk_assessment(invoice, behavior, facts)
    return QuickRisk(customer=customer, invoice=invoice, risk=risk)


def assess_invoice(invoice_id: str) -> Assessment:
    provider = get_context_provider()
    invoice = provider.get_invoice(invoice_id)
    customer = provider.get_customer(invoice.customer_id)
    history = provider.get_payment_history(customer.customer_id)
    policy = provider.get_policy()

    intelligence = compute_intelligence(customer)
    behavior = compute_payment_behavior(customer.customer_id, history)
    facts = derive_customer_facts(customer, history)
    risk = compute_risk_assessment(invoice, behavior, facts)
    strategy = propose_strategy(customer, invoice, intelligence, behavior, risk)

    return Assessment(
        customer=customer,
        invoice=invoice,
        intelligence=intelligence,
        behavior=behavior,
        facts=facts,
        risk=risk,
        strategy=strategy,
        policy=policy,
    )


def negotiate_turn(
    assessment: Assessment,
    session_id: str,
    conversation: list[NegotiationTurn],
    customer_message: str,
) -> NegotiationOutcome:
    result = extract_negotiation_result(
        session_id,
        assessment.customer.name,
        assessment.invoice,
        assessment.strategy,
        conversation,
        customer_message,
    )
    proposal = to_action_proposal(result, assessment.invoice.invoice_id, assessment.customer.customer_id)
    decision = evaluate(proposal, assessment.policy, assessment.facts)
    promise = get_action_executor().execute(decision, assessment.invoice)

    return NegotiationOutcome(result=result, proposal=proposal, decision=decision, promise=promise)
