"""Customer Intelligence Agent. Deterministic — tenure and LTV are arithmetic,
not something worth spending an LLM call on. No Gemini call in this file."""

from datetime import date

from ai.schemas import CustomerIntelligence, CustomerProfile, CustomerTier

_HIGH_LTV_THRESHOLD = 2_000_000
_MEDIUM_LTV_THRESHOLD = 500_000


def _tenure_months(since: date, today: date) -> int:
    months = (today.year - since.year) * 12 + (today.month - since.month)
    if today.day < since.day:
        months -= 1
    return max(0, months)


def _relationship_criticality(tier: CustomerTier, lifetime_value: float) -> str:
    if lifetime_value >= _HIGH_LTV_THRESHOLD or tier == CustomerTier.GOLD:
        return "High"
    if lifetime_value >= _MEDIUM_LTV_THRESHOLD:
        return "Medium"
    return "Low"


def compute_intelligence(
    customer: CustomerProfile, today: date | None = None
) -> CustomerIntelligence:
    today = today or date.today()  # noqa: DTZ011 — month-level tenure calc, tz precision irrelevant
    tenure_months = _tenure_months(customer.customer_since, today)
    tenure_years = tenure_months // 12
    criticality = _relationship_criticality(customer.tier, customer.lifetime_value)

    summary = (
        f"{tenure_years}-year {customer.segment.value.replace('_', ' ')} relationship "
        f"({customer.tier.value} tier), lifetime value {customer.lifetime_value:,.0f}."
    )

    return CustomerIntelligence(
        customer_id=customer.customer_id,
        tenure_months=tenure_months,
        lifetime_value=customer.lifetime_value,
        segment=customer.segment,
        tier=customer.tier,
        relationship_criticality=criticality,
        relationship_summary=summary,
    )
