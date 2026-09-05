"""HTTP implementation of the AI context boundary.

This adapter translates FastAPI responses into the domain schemas used by the
AI pipeline, so the frontend never reads fixture JSON when ``CONTEXT_SOURCE``
is set to ``api``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx

from ai.config import settings
from ai.orchestration.mock_provider import CustomerNotFoundError, InvoiceNotFoundError
from ai.schemas import (
    CustomerProfile,
    CustomerSegment,
    CustomerTier,
    Invoice,
    MerchantPolicy,
    PaymentRecord,
    TierPolicyRule,
)


class BackendAPIError(RuntimeError):
    """The configured BakiClear API could not fulfil a request."""


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
