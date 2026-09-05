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

from ai.schemas import (
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
        self._audit_log.append(AuditLogEntry(timestamp=datetime.now(), decision=decision))  # noqa: DTZ005
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
        due_date = max(invoice.due_date, date.today()) + timedelta(  # noqa: DTZ011
            days=effective.proposed_extension_days
        )

        promise = PromiseToPay(
            promise_id=f"PROM-{uuid.uuid4().hex[:8].upper()}",
            invoice_id=invoice.invoice_id,
            customer_id=invoice.customer_id,
            amount=round(amount, 2),
            due_date=due_date,
            status=PromiseStatus.PENDING,
            created_at=datetime.now(),  # noqa: DTZ005
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


@lru_cache
def get_action_executor() -> ActionExecutor:
    """Singleton for the process — every screen in one Streamlit session shares
    the same in-memory store so Outcome/Metrics reflect what Negotiation did."""
    return MockActionExecutor()
