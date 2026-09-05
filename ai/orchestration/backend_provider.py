"""HTTP implementation of the AI context boundary.

This adapter translates FastAPI responses into the domain schemas used by the
AI pipeline, so the frontend never reads fixture JSON when ``CONTEXT_SOURCE``
is set to ``api``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, NamedTuple

import httpx

from ai.agents.risk_engine import summarize_payment_behavior
from ai.config import settings
from ai.orchestration.mock_provider import CustomerNotFoundError, InvoiceNotFoundError
from ai.schemas import (
    CustomerIntelligence,
    CustomerProfile,
    CustomerSegment,
    CustomerTier,
    Invoice,
    MerchantPolicy,
    PaymentBehavior,
    PaymentRecord,
    PriorityLevel,
    RiskAssessment,
    RiskLevel,
    TierPolicyRule,
)


class BackendAPIError(RuntimeError):
    """The configured BakiClear API could not fulfil a request."""


class PrecomputedAssessment(NamedTuple):
    """What GET /customers/{id}/context gives us in one call: the backend's
    own deterministic intelligence/behavior/risk/policy, already computed
    against real data. Not a formal ai.schemas contract — an internal adapter
    shape, mirrored 1:1 into Assessment by ai/orchestration/pipeline.py."""

    customer: CustomerProfile
    intelligence: CustomerIntelligence
    behavior: PaymentBehavior
    risk: RiskAssessment
    policy: MerchantPolicy


_BACKEND_PRIORITY_MAP = {
    "low": PriorityLevel.LOW,
    "medium": PriorityLevel.MEDIUM,
    "high": PriorityLevel.HIGH,
}
# Backend only has 3 priority tiers; PriorityLevel has 4 (URGENT). A "high"
# priority item that's also "critical" risk gets bumped to URGENT — critical
# risk is exactly the case that should visually stand out above plain "high".
_PRIORITY_SCORE_PROXY = {
    PriorityLevel.LOW: 15,
    PriorityLevel.MEDIUM: 40,
    PriorityLevel.HIGH: 65,
    PriorityLevel.URGENT: 85,
}


_SEGMENT_MAP = {
    "gold": CustomerSegment.ENTERPRISE,
    "standard": CustomerSegment.SMALL_BUSINESS,
    "at_risk": CustomerSegment.MID_MARKET,
    "new": CustomerSegment.INDIVIDUAL,
}
_TIER_MAP = {
    "gold": CustomerTier.GOLD,
    "standard": CustomerTier.STANDARD,
    "at_risk": CustomerTier.WATCH_LIST,
    "new": CustomerTier.STANDARD,
}


class BackendContextProvider:
    """ContextProvider backed by the running FastAPI service."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.backend_base_url).rstrip("/")
        # Queue items already contain the complete invoice shape.  Retaining
        # them avoids a second lookup for every row (and keeps one render tied
        # to one consistent backend snapshot).
        self._invoices: dict[str, Invoice] = {}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = httpx.request(method, f"{self.base_url}{path}", timeout=15.0, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404 and path.startswith("/api/customers/"):
                raise CustomerNotFoundError(path) from exc
            if exc.response.status_code == 404 and path.startswith("/api/invoices/"):
                raise InvoiceNotFoundError(path) from exc
            raise BackendAPIError(f"Backend request failed ({exc.response.status_code}): {path}") from exc
        except httpx.HTTPError as exc:
            raise BackendAPIError(
                f"Cannot reach BakiClear API at {self.base_url}. Start the backend and check BACKEND_BASE_URL."
            ) from exc

    @staticmethod
    def _customer(payload: dict[str, Any]) -> CustomerProfile:
        segment = payload["segment"]
        tenure = int(payload.get("tenure_months", 0))
        return CustomerProfile(
            customer_id=payload["customer_id"],
            name=payload["name"],
            segment=_SEGMENT_MAP[segment],
            tier=_TIER_MAP[segment],
            customer_since=date.today() - timedelta(days=tenure * 30),
            lifetime_value=payload["lifetime_value"],
            contact_email=payload.get("email"),
            contact_phone=payload.get("phone"),
        )

    @staticmethod
    def _invoice(payload: dict[str, Any]) -> Invoice:
        return Invoice(
            invoice_id=payload["invoice_id"],
            customer_id=payload["customer_id"],
            amount_due=payload["amount"],
            due_date=payload["due_date"],
            days_overdue=payload["days_overdue"],
        )

    def get_customer(self, customer_id: str) -> CustomerProfile:
        return self._customer(self.request("GET", f"/api/customers/{customer_id}"))

    def get_invoice(self, invoice_id: str) -> Invoice:
        if invoice_id in self._invoices:
            return self._invoices[invoice_id]
        return self._invoice(self.request("GET", f"/api/invoices/{invoice_id}"))

    def list_overdue_invoices(self) -> list[Invoice]:
        payload = self.request("GET", "/api/invoices", params={"status": "overdue", "limit": 500})
        invoices = [self._invoice(invoice) for invoice in payload]
        self._invoices.update({invoice.invoice_id: invoice for invoice in invoices})
        return invoices

    def get_collection_queue(self) -> list[dict[str, Any]]:
        """Dashboard-ready queue data, served by the backend without N+1 calls."""
        return self.request("GET", "/api/invoices/queue")

    def get_payment_history(self, customer_id: str) -> list[PaymentRecord]:
        history = self.request("GET", f"/api/customers/{customer_id}/history")
        promises = self.request("GET", "/api/promises", params={"customer_id": customer_id})
        broken_invoice_ids = {p["invoice_id"] for p in promises if p["status"] == "broken"}
        return [
            PaymentRecord(
                invoice_id=row["invoice_id"],
                due_date=row["due_date"],
                paid_date=row.get("paid_date"),
                amount=row["amount"],
                was_disputed=row["disputed"],
                broken_promise=row["invoice_id"] in broken_invoice_ids,
            )
            for row in history["records"]
        ]

    def get_policy(self) -> MerchantPolicy:
        payload_by_segment = {
            policy["segment"]: policy for policy in self.request("GET", "/api/policy")
        }
        rules: dict[CustomerTier, TierPolicyRule] = {}
        for segment in ("gold", "standard", "at_risk", "new"):
            policy = payload_by_segment.get(segment)
            if not policy:
                continue
            tier = _TIER_MAP[policy["segment"]]
            # New accounts share the standard tier, so retain standard's
            # explicit policy rather than overwriting it with the fallback.
            if tier in rules:
                continue
            rules[tier] = TierPolicyRule(
                tier=tier,
                max_extension_days=policy["max_extension_days"],
                max_discount_pct=policy["max_discount_percent"],
                requires_human_approval_if_disputed=policy["requires_human_approval"],
                requires_human_approval_if_broken_promises_gte=1 if tier == CustomerTier.WATCH_LIST else 2,
            )
        return MerchantPolicy(policy_id="database-policy", rules_by_tier=rules)

    def get_precomputed_assessment(self, customer_id: str, invoice_id: str) -> PrecomputedAssessment:
        """Defer to the backend's own deterministic risk/behavior computation
        instead of recomputing it locally in ai/agents/risk_engine.py.

        One call replaces what would otherwise be a customer fetch, a policy
        fetch, and an independently-computed risk score — and it means the AI
        layer reports the exact same numbers as anything else built against
        this backend. See ai/orchestration/pipeline.py: assess_invoice() uses
        this when the provider offers it, and only falls back to local
        computation in mock mode, where no such backend exists to defer to.

        invoice_id is always passed explicitly — omitting it makes the
        backend guess "the most overdue invoice for this customer", which is
        wrong the moment a customer has more than one.
        """
        ctx = self.request(
            "GET", f"/api/customers/{customer_id}/context", params={"invoice_id": invoice_id}
        )

        cust = ctx["customer"]
        segment = cust["segment"]
        customer = CustomerProfile(
            customer_id=cust["customer_id"],
            name=cust["name"],
            segment=_SEGMENT_MAP[segment],
            tier=_TIER_MAP[segment],
            # Unused downstream once precomputed intelligence is in play — a
            # placeholder, not a fact anything reads.
            customer_since=date.today() - timedelta(days=int(cust.get("tenure_months", 0)) * 30),
            lifetime_value=cust["lifetime_value"],
        )

        intelligence = CustomerIntelligence(
            customer_id=customer.customer_id,
            tenure_months=cust["tenure_months"],
            lifetime_value=cust["lifetime_value"],
            segment=customer.segment,
            tier=customer.tier,
            relationship_criticality=cust["relationship_criticality"].title(),
            relationship_summary=(
                f"{cust['tenure_months']} months as a {segment} segment customer, lifetime value "
                f"{cust['lifetime_value']:,.0f} ({cust['relationship_criticality']} criticality)."
            ),
        )

        ph = ctx["payment_history"]
        behavior = PaymentBehavior(
            customer_id=customer.customer_id,
            total_invoices=ph["total_payments_recorded"],
            on_time_payment_pct=ph["on_time_percentage"],
            average_delay_days=ph["average_payment_delay"],
            dispute_count=ph["disputes"],
            broken_promise_count=ph["broken_promises"],
            behavioral_summary=summarize_payment_behavior(ph["on_time_percentage"], ph["broken_promises"]),
        )

        risk_data = ctx["risk_assessment"]
        breakdown = risk_data["score_breakdown"]
        factors: list[str] = []
        if breakdown.get("overdue_component", 0) > 0:
            factors.append(f"{ctx['invoice']['days_overdue']} days overdue")
        if breakdown.get("reliability_deficit_component", 0) > 0:
            factors.append(f"{ph['on_time_percentage']}% on-time payment rate")
        if ph["disputes"] > 0:
            factors.append(f"{ph['disputes']} dispute(s) on record")
        if ph["broken_promises"] > 0:
            factors.append(f"{ph['broken_promises']} broken promise(s)")
        if breakdown.get("segment_modifier", 0):
            sign = "+" if breakdown["segment_modifier"] > 0 else ""
            factors.append(f"{segment} segment adjustment ({sign}{breakdown['segment_modifier']} pts)")
        if not factors:
            factors.append("clean payment history")

        priority_level = _BACKEND_PRIORITY_MAP[risk_data["priority"]]
        if risk_data["risk_tier"] == "critical" and priority_level == PriorityLevel.HIGH:
            priority_level = PriorityLevel.URGENT

        risk = RiskAssessment(
            customer_id=customer.customer_id,
            invoice_id=invoice_id,
            risk_score=round(risk_data["risk_score"]),
            risk_level=RiskLevel(risk_data["risk_tier"]),
            priority_score=_PRIORITY_SCORE_PROXY[priority_level],
            priority_level=priority_level,
            contributing_factors=factors,
        )

        pb = ctx["policy_bounds"]
        policy = MerchantPolicy(
            policy_id="backend-context",
            rules_by_tier={
                customer.tier: TierPolicyRule(
                    tier=customer.tier,
                    max_extension_days=pb["max_extension_days"],
                    max_discount_pct=pb["max_discount_percent"],
                    requires_human_approval_if_disputed=pb["requires_human_approval"],
                    requires_human_approval_if_broken_promises_gte=(
                        1 if customer.tier == CustomerTier.WATCH_LIST else 2
                    ),
                )
            },
        )

        return PrecomputedAssessment(
            customer=customer, intelligence=intelligence, behavior=behavior, risk=risk, policy=policy
        )
