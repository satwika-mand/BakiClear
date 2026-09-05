"""Action Executor (agent #7). Runs ONLY after the Guardrail has ruled.

ALLOW/MODIFY -> a PromiseToPay is recorded, using the (possibly modified)
terms — never the original ask. REJECT/HUMAN_APPROVAL -> no promise, but
still logged, so nothing is ever decided silently.

Same swap pattern as ContextProvider: agents call get_action_executor(), never
MockActionExecutor directly, so Phase 5 (real POST /api/promises calls) is a
new class, not a rewrite.
"""

import uuid
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Protocol, runtime_checkable

import httpx

from ai.config import settings
from ai.schemas import (
    ActionProposal,
    ActionType,
    AuditLogEntry,
    GuardrailDecision,
    GuardrailVerdict,
    Invoice,
    MetricsSummary,
    PromiseStatus,
    PromiseToPay,
)


@runtime_checkable
class ActionExecutor(Protocol):
    def execute(self, decision: GuardrailDecision, invoice: Invoice) -> PromiseToPay | None: ...

    def mark_promise_status(self, promise_id: str, status: PromiseStatus) -> None: ...

    def list_promises(self) -> list[PromiseToPay]: ...

    def list_audit_log(self) -> list[AuditLogEntry]: ...

    def list_pending_approvals(self) -> list[GuardrailDecision]: ...

    def compute_metrics(self) -> MetricsSummary: ...


class MockActionExecutor:
    """In-memory store. Lives for the process lifetime — fine for a hackathon
    demo/session; Phase 5 replaces this with real backend calls, same interface."""

    def __init__(self) -> None:
        self._promises: dict[str, PromiseToPay] = {}
        self._audit_log: list[AuditLogEntry] = []
        self._pending_approvals: list[GuardrailDecision] = []
        self._invoices_seen: dict[str, float] = {}  # invoice_id -> amount_due, for recovery_rate

    def execute(self, decision: GuardrailDecision, invoice: Invoice) -> PromiseToPay | None:
        self._audit_log.append(AuditLogEntry(timestamp=datetime.now(), decision=decision))
        self._invoices_seen[invoice.invoice_id] = invoice.amount_due

        if decision.verdict == GuardrailVerdict.HUMAN_APPROVAL:
            self._pending_approvals.append(decision)
            return None
        if decision.verdict == GuardrailVerdict.REJECT:
            return None

        effective = decision.modified_proposal or decision.original_proposal
        amount = effective.proposed_amount
        if amount is None:
            amount = invoice.amount_due * (1 - effective.proposed_discount_pct / 100)
        # The extension is measured from today, not the (already-passed) original
        # due date — "10 more days" means 10 days from now for an overdue invoice.
        due_date = max(invoice.due_date, date.today()) + timedelta(
            days=effective.proposed_extension_days
        )

        promise = PromiseToPay(
            promise_id=f"PROM-{uuid.uuid4().hex[:8].upper()}",
            invoice_id=invoice.invoice_id,
            customer_id=invoice.customer_id,
            amount=round(amount, 2),
            due_date=due_date,
            status=PromiseStatus.PENDING,
            created_at=datetime.now(),
            guardrail_decision_reason=decision.reason,
        )
        self._promises[promise.promise_id] = promise
        return promise

    def mark_promise_status(self, promise_id: str, status: PromiseStatus) -> None:
        if promise_id in self._promises:
            self._promises[promise_id] = self._promises[promise_id].model_copy(
                update={"status": status}
            )

    def list_promises(self) -> list[PromiseToPay]:
        return list(self._promises.values())

    def list_audit_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def list_pending_approvals(self) -> list[GuardrailDecision]:
        return list(self._pending_approvals)

    def compute_metrics(self) -> MetricsSummary:
        promises = self.list_promises()
        total_due = sum(self._invoices_seen.values())
        total_promised = sum(p.amount for p in promises)
        resolved = [p for p in promises if p.status in (PromiseStatus.KEPT, PromiseStatus.BROKEN)]
        kept = sum(1 for p in resolved if p.status == PromiseStatus.KEPT)

        rejections = sum(1 for e in self._audit_log if e.decision.verdict == GuardrailVerdict.REJECT)
        modifications = sum(
            1 for e in self._audit_log if e.decision.verdict == GuardrailVerdict.MODIFY
        )

        return MetricsSummary(
            total_invoices_processed=len(self._invoices_seen),
            total_amount_due=total_due,
            total_amount_promised=total_promised,
            recovery_rate_pct=round(total_promised / total_due * 100, 1) if total_due else 0.0,
            promise_keeping_rate_pct=round(kept / len(resolved) * 100, 1) if resolved else 0.0,
            human_escalations=len(self._pending_approvals),
            guardrail_rejections=rejections,
            guardrail_modifications=modifications,
        )


class BackendActionExecutor:
    """Persists all negotiation outcomes through the FastAPI backend."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.backend_base_url).rstrip("/")

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = httpx.request(method, f"{self.base_url}{path}", timeout=15.0, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"BakiClear API request failed: {method} {path}") from exc

    @staticmethod
    def _to_promise(payload: dict, reason: str = "Recorded by backend") -> PromiseToPay:
        return PromiseToPay(
            promise_id=payload["promise_id"],
            invoice_id=payload["invoice_id"],
            customer_id=payload["customer_id"],
            amount=payload["amount"],
            due_date=payload["promised_date"],
            status=PromiseStatus(payload["status"]),
            created_at=payload["created_at"],
            guardrail_decision_reason=reason,
        )

    def execute(self, decision: GuardrailDecision, invoice: Invoice) -> PromiseToPay | None:
        effective = decision.modified_proposal or decision.original_proposal
        decision_map = {
            GuardrailVerdict.ALLOW: "approved",
            GuardrailVerdict.MODIFY: "approved",
            GuardrailVerdict.REJECT: "rejected",
            GuardrailVerdict.HUMAN_APPROVAL: "escalated",
        }
        requested = decision.original_proposal
        self._request(
            "POST",
            "/api/actions",
            json={
                "invoice_id": invoice.invoice_id,
                "action_type": effective.action_type.value,
                "decision": decision_map[decision.verdict],
                "reason": decision.reason,
                "actor": "policy_engine",
                "requested_value": f"{requested.proposed_discount_pct}% discount / {requested.proposed_extension_days}d extension",
                "approved_value": (
                    f"{effective.proposed_discount_pct}% discount / {effective.proposed_extension_days}d extension"
                    if decision.verdict in {GuardrailVerdict.ALLOW, GuardrailVerdict.MODIFY}
                    else None
                ),
                "idempotency_key": f"{invoice.invoice_id}:{effective.action_type.value}:{uuid.uuid4().hex}",
            },
        )
        if decision.verdict in {GuardrailVerdict.REJECT, GuardrailVerdict.HUMAN_APPROVAL}:
            return None

        amount = effective.proposed_amount
        if amount is None:
            amount = invoice.amount_due * (1 - effective.proposed_discount_pct / 100)
        promised_date = max(invoice.due_date, date.today()) + timedelta(
            days=effective.proposed_extension_days
        )
        payload = self._request(
            "POST",
            "/api/promises",
            json={
                "invoice_id": invoice.invoice_id,
                "customer_id": invoice.customer_id,
                "amount": round(amount, 2),
                "promised_date": promised_date.isoformat(),
            },
        )
        return self._to_promise(payload, decision.reason)

    def mark_promise_status(self, promise_id: str, status: PromiseStatus) -> None:
        if status == PromiseStatus.KEPT:
            self._request("POST", f"/api/promises/{promise_id}/mark-paid", json={})
        elif status == PromiseStatus.BROKEN:
            self._request("PATCH", f"/api/promises/{promise_id}/status", params={"status_value": "broken"})
        else:
            self._request("PATCH", f"/api/promises/{promise_id}/status", params={"status_value": status.value})

    def list_promises(self) -> list[PromiseToPay]:
        return [self._to_promise(row) for row in self._request("GET", "/api/promises")]

    @staticmethod
    def _audit_entry(row: dict) -> AuditLogEntry:
        """The backend only stores "approved"/"rejected"/"escalated" — MODIFY
        collapses into "approved" there. Recover the distinction the same way
        the backend's own schema intends it: requested_value != approved_value
        on an "approved" row means the guardrail clamped the ask, not allowed
        it outright."""
        if row["decision"] == "approved":
            verdict = (
                GuardrailVerdict.MODIFY
                if row.get("requested_value") != row.get("approved_value")
                else GuardrailVerdict.ALLOW
            )
        else:
            verdict = {
                "rejected": GuardrailVerdict.REJECT,
                "escalated": GuardrailVerdict.HUMAN_APPROVAL,
            }[row["decision"]]
        proposal = ActionProposal(
            invoice_id=row["invoice_id"], customer_id="database", action_type=ActionType.RECORD_PROMISE,
            source_agent="policy_engine", rationale=row["reason"],
        )
        return AuditLogEntry(timestamp=row["timestamp"], decision=GuardrailDecision(
            verdict=verdict, original_proposal=proposal, reason=row["reason"]
        ))

    def list_audit_log(self) -> list[AuditLogEntry]:
        return [self._audit_entry(row) for row in self._request("GET", "/api/actions")]

    def list_pending_approvals(self) -> list[GuardrailDecision]:
        return [entry.decision for entry in self.list_audit_log() if entry.decision.verdict == GuardrailVerdict.HUMAN_APPROVAL]

    def compute_metrics(self) -> MetricsSummary:
        summary = self._request("GET", "/api/metrics/summary")
        promises = self._request("GET", "/api/promises")
        resolved = [p for p in promises if p["status"] in {"kept", "broken"}]
        kept = sum(p["status"] == "kept" for p in resolved)
        modifications = sum(
            1 for entry in self.list_audit_log() if entry.decision.verdict == GuardrailVerdict.MODIFY
        )
        return MetricsSummary(
            total_invoices_processed=summary["total_invoices_count"],
            total_amount_due=summary["total_overdue_amount"],
            total_amount_promised=round(sum(p["amount"] for p in promises), 2),
            recovery_rate_pct=summary["recovery_rate_percent"],
            promise_keeping_rate_pct=round(kept / len(resolved) * 100, 1) if resolved else 0.0,
            human_escalations=summary["human_escalations_count"],
            guardrail_rejections=summary["guardrail_blocks_count"],
            guardrail_modifications=modifications,
        )


@lru_cache
def get_action_executor() -> ActionExecutor:
    """Singleton for the process — every screen in one Streamlit session shares
    the same in-memory store so Outcome/Metrics reflect what Negotiation did."""
    if settings.context_source == "api":
        return BackendActionExecutor()
    return MockActionExecutor()
