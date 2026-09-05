from ai.agents.risk_engine import (
    compute_payment_behavior,
    compute_risk_assessment,
    derive_customer_facts,
)
from ai.orchestration.mock_provider import MockContextProvider
from ai.schemas import PriorityLevel, RiskLevel


def test_meridian_clean_history_is_low_risk():
    provider = MockContextProvider()
    customer = provider.get_customer("CUST-001")
    invoice = provider.get_invoice("INV-1001")
    history = provider.get_payment_history("CUST-001")

    behavior = compute_payment_behavior("CUST-001", history)
    facts = derive_customer_facts(customer, history)
    risk = compute_risk_assessment(invoice, behavior, facts)

    assert behavior.dispute_count == 0
    assert facts.has_open_dispute is False
    assert risk.risk_level == RiskLevel.LOW


def test_orion_disputed_and_broken_promises_is_critical_risk():
    provider = MockContextProvider()
    customer = provider.get_customer("CUST-003")
    invoice = provider.get_invoice("INV-2001")
    history = provider.get_payment_history("CUST-003")

    behavior = compute_payment_behavior("CUST-003", history)
    facts = derive_customer_facts(customer, history)
    risk = compute_risk_assessment(invoice, behavior, facts)

    assert facts.has_open_dispute is True
    assert facts.broken_promise_count == 2
    assert risk.risk_level == RiskLevel.CRITICAL
    assert risk.priority_level == PriorityLevel.URGENT


def test_no_history_defaults_to_clean_behavior():
    behavior = compute_payment_behavior("CUST-NEW", [])
    assert behavior.total_invoices == 0
    assert behavior.on_time_payment_pct == 100.0
