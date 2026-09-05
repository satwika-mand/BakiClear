import pytest

from ai.orchestration.context_provider import ContextProvider
from ai.orchestration.mock_provider import (
    CustomerNotFoundError,
    InvoiceNotFoundError,
    MockContextProvider,
)
from ai.schemas import CustomerTier


@pytest.fixture
def provider() -> MockContextProvider:
    return MockContextProvider()


def test_conforms_to_protocol(provider: MockContextProvider) -> None:
    assert isinstance(provider, ContextProvider)


def test_get_customer(provider: MockContextProvider) -> None:
    customer = provider.get_customer("CUST-001")
    assert customer.name == "Meridian Textiles Pvt Ltd"
    assert customer.tier == CustomerTier.GOLD


def test_unknown_customer_raises(provider: MockContextProvider) -> None:
    with pytest.raises(CustomerNotFoundError):
        provider.get_customer("CUST-DOES-NOT-EXIST")


def test_unknown_invoice_raises(provider: MockContextProvider) -> None:
    with pytest.raises(InvoiceNotFoundError):
        provider.get_invoice("INV-DOES-NOT-EXIST")


def test_overdue_invoices_sorted_by_days_overdue_desc(provider: MockContextProvider) -> None:
    invoices = provider.list_overdue_invoices()
    days = [inv.days_overdue for inv in invoices]
    assert days == sorted(days, reverse=True)


def test_scenario_a_clean_gold_customer(provider: MockContextProvider) -> None:
    """Meridian: gold tier, no disputes, no broken promises -> should be a
    guardrail ALLOW case once agents are wired up."""
    history = provider.get_payment_history("CUST-001")
    assert not any(r.was_disputed for r in history)
    assert not any(r.broken_promise for r in history)


def test_scenario_b_watch_list_customer_has_risk_flags(provider: MockContextProvider) -> None:
    """Orion: watch-list tier with disputes and broken promises -> should be a
    guardrail REJECT/HUMAN_APPROVAL case once agents are wired up."""
    customer = provider.get_customer("CUST-003")
    history = provider.get_payment_history("CUST-003")
    assert customer.tier == CustomerTier.WATCH_LIST
    assert sum(r.was_disputed for r in history) >= 1
    assert sum(r.broken_promise for r in history) >= 2


def test_policy_watch_list_has_zero_autonomous_concessions(provider: MockContextProvider) -> None:
    rule = provider.get_policy().rule_for(CustomerTier.WATCH_LIST)
    assert rule.max_extension_days == 0
    assert rule.max_discount_pct == 0
