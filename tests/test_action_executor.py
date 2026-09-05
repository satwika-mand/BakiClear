from datetime import date, timedelta

import pytest

from ai.agents.action_executor import ActionExecutor, MockActionExecutor, _build_idempotency_key
from ai.schemas import (
    ActionProposal,
    ActionType,
    GuardrailDecision,
    GuardrailVerdict,
    Invoice,
    PromiseStatus,
)


@pytest.fixture
def executor() -> MockActionExecutor:
    return MockActionExecutor()


@pytest.fixture
def invoice() -> Invoice:
    return Invoice(
        invoice_id="INV-1001",
        customer_id="CUST-001",
        amount_due=500000.0,
        due_date=date(2026, 8, 16),
        days_overdue=20,
    )


def _proposal(**overrides) -> ActionProposal:
    base = {
        "invoice_id": "INV-1001",
        "customer_id": "CUST-001",
        "action_type": ActionType.RECORD_PROMISE,
        "source_agent": "negotiation",
        "rationale": "test",
    }
    base.update(overrides)
    return ActionProposal(**base)


def test_conforms_to_protocol(executor: MockActionExecutor) -> None:
    assert isinstance(executor, ActionExecutor)


def test_allow_creates_promise_with_extension_applied(
    executor: MockActionExecutor, invoice: Invoice
) -> None:
    proposal = _proposal(proposed_extension_days=10)
    decision = GuardrailDecision(
        verdict=GuardrailVerdict.ALLOW, original_proposal=proposal, reason="within limits"
    )

    promise = executor.execute(decision, invoice)

    assert promise is not None
    # Invoice is already overdue, so the extension is measured from today, not
    # the (already-passed) original due date.
    assert promise.due_date == date.today() + timedelta(days=10)
    assert promise.amount == invoice.amount_due
    assert promise.status == PromiseStatus.PENDING
    assert promise in executor.list_promises()


def test_modify_uses_modified_proposal_not_original(
    executor: MockActionExecutor, invoice: Invoice
) -> None:
    original = _proposal(proposed_discount_pct=8)
    modified = original.model_copy(update={"proposed_discount_pct": 2})
    decision = GuardrailDecision(
        verdict=GuardrailVerdict.MODIFY,
        original_proposal=original,
        modified_proposal=modified,
        reason="clamped to policy max",
    )

    promise = executor.execute(decision, invoice)

    assert promise is not None
    assert promise.amount == pytest.approx(invoice.amount_due * 0.98)


def test_reject_creates_no_promise_but_logs_audit(
    executor: MockActionExecutor, invoice: Invoice
) -> None:
    decision = GuardrailDecision(
        verdict=GuardrailVerdict.REJECT, original_proposal=_proposal(), reason="zero tolerance"
    )

    promise = executor.execute(decision, invoice)

    assert promise is None
    assert len(executor.list_promises()) == 0
    assert len(executor.list_audit_log()) == 1


def test_human_approval_queues_for_review_creates_no_promise(
    executor: MockActionExecutor, invoice: Invoice
) -> None:
    decision = GuardrailDecision(
        verdict=GuardrailVerdict.HUMAN_APPROVAL, original_proposal=_proposal(), reason="open dispute"
    )

    promise = executor.execute(decision, invoice)

    assert promise is None
    assert len(executor.list_pending_approvals()) == 1


def test_mark_promise_status_updates_in_place(
    executor: MockActionExecutor, invoice: Invoice
) -> None:
    decision = GuardrailDecision(
        verdict=GuardrailVerdict.ALLOW, original_proposal=_proposal(), reason="ok"
    )
    promise = executor.execute(decision, invoice)

    executor.mark_promise_status(promise.promise_id, PromiseStatus.KEPT)

    assert executor.list_promises()[0].status == PromiseStatus.KEPT


def test_metrics_reflect_mixed_outcomes(executor: MockActionExecutor, invoice: Invoice) -> None:
    executor.execute(
        GuardrailDecision(
            verdict=GuardrailVerdict.ALLOW, original_proposal=_proposal(), reason="ok"
        ),
        invoice,
    )
    executor.execute(
        GuardrailDecision(
            verdict=GuardrailVerdict.REJECT, original_proposal=_proposal(), reason="blocked"
        ),
        invoice,
    )
    executor.execute(
        GuardrailDecision(
            verdict=GuardrailVerdict.HUMAN_APPROVAL, original_proposal=_proposal(), reason="escalate"
        ),
        invoice,
    )

    metrics = executor.compute_metrics()

    assert metrics.guardrail_rejections == 1
    assert metrics.human_escalations == 1
    assert metrics.total_amount_promised == invoice.amount_due


class TestIdempotencyKey:
    """A random suffix (the original bug) would make every submission look
    "new" to the backend, defeating idempotency entirely. These lock in that
    the key is deterministic, and that it distinguishes genuinely different
    outcomes rather than over-deduping by date alone."""

    def _key(self, **overrides):
        base = {
            "invoice_id": "INV-1",
            "action_type": "record_promise",
            "requested_value": "5.0% discount / 0d extension",
            "approved_value": "3.0% discount / 0d extension",
            "decision": "approved",
            "reason": "clamped to policy max",
            "as_of": date(2026, 9, 5),
        }
        base.update(overrides)
        return _build_idempotency_key(**base)

    def test_identical_inputs_produce_identical_key(self):
        assert self._key() == self._key()

    def test_different_reason_produces_different_key(self):
        assert self._key(reason="different reason entirely") != self._key()

    def test_different_requested_value_produces_different_key(self):
        """A second, larger discount ask on the same invoice/action_type/day
        must NOT collide with an earlier smaller ask — a pure date-based key
        would silently drop this second real event."""
        assert self._key(requested_value="15.0% discount / 0d extension") != self._key()

    def test_different_day_produces_different_key(self):
        assert self._key(as_of=date(2026, 9, 6)) != self._key()

    def test_key_contains_invoice_and_action_type_for_readability(self):
        key = self._key()
        assert key.startswith("INV-1:record_promise:2026-09-05:")
