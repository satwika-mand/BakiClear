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
    CustomerTier,
    GuardrailDecision,
    GuardrailVerdict,
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

    # BackendContextProvider exposes get_precomputed_assessment (one call to
    # the backend's own /context endpoint) so we defer to its numbers instead
    # of running an independent risk formula against the same facts —  two
    # systems scoring the same customer differently is a real trust problem,
    # not just a style choice. MockContextProvider has no such backend to
    # defer to, so it falls through to local computation below.
    get_precomputed = getattr(provider, "get_precomputed_assessment", None)
    if get_precomputed is not None:
        pre = get_precomputed(invoice.customer_id, invoice_id)
        history = provider.get_payment_history(invoice.customer_id)
        # Backend's context payload gives aggregate dispute/broken-promise
        # counts, not "is a dispute still open" — the one fact the guardrail
        # actually branches on — so this still needs the raw ledger.
        facts = derive_customer_facts(pre.customer, history)
        strategy = propose_strategy(pre.customer, invoice, pre.intelligence, pre.behavior, pre.risk)
        return Assessment(
            customer=pre.customer,
            invoice=invoice,
            intelligence=pre.intelligence,
            behavior=pre.behavior,
            facts=facts,
            risk=pre.risk,
            strategy=strategy,
            policy=pre.policy,
        )

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


def should_escalate_to_human(assessment: Assessment, decision: GuardrailDecision) -> bool:
    """Determine if this case must be escalated to a human agent.

    Rules:
      - 15+ days overdue (entrenched)
      - watch_list tier (inherently risky)
      - open dispute (requires human judgment)
      - guardrail verdict is HUMAN_APPROVAL (explicit)
    """
    if assessment.invoice.days_overdue >= 15:
        return True
    if assessment.customer.tier == CustomerTier.WATCH_LIST:
        return True
    if assessment.facts.has_open_dispute:
        return True
    return decision.verdict == GuardrailVerdict.HUMAN_APPROVAL


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
