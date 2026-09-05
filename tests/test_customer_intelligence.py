from datetime import date

from ai.agents.customer_intelligence import compute_intelligence
from ai.orchestration.mock_provider import MockContextProvider


def test_meridian_gold_long_tenure_is_high_criticality():
    customer = MockContextProvider().get_customer("CUST-001")
    intelligence = compute_intelligence(customer, today=date(2026, 9, 5))

    assert intelligence.tenure_months >= 12 * 7  # customer since 2019-03-14
    assert intelligence.relationship_criticality == "High"


def test_low_value_standard_tier_customer_is_low_criticality():
    customer = MockContextProvider().get_customer("CUST-004")
    intelligence = compute_intelligence(customer, today=date(2026, 9, 5))

    assert intelligence.lifetime_value < 500_000
    assert intelligence.relationship_criticality == "Low"
