"""Deterministic 15-invoice recovery simulation for the demo.

This is explicitly a simulation, not a production recovery claim. It exercises
the same Python policy engine used by the app and fixed customer outcomes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from ai.guardrails.policy_engine import evaluate
from ai.orchestration.mock_provider import MockContextProvider
from ai.schemas import ActionProposal, ActionType, CustomerFacts, CustomerTier

_REPORT_PATH = Path(__file__).resolve().parent.parent / "eval_reports" / "batch_recovery.json"


@dataclass(frozen=True)
class Scenario:
    invoice_id: str
    amount: float
    tier: CustomerTier
    days_overdue: int
    discount: float
    extension: int
    disputed: bool
    broken_promises: int
    response: str


@dataclass
class Result:
    invoice_id: str
    amount: float
    verdict: str
    simulated_response: str
    recovered_amount: float


_INPUTS = [
    (42_000, CustomerTier.GOLD, 2, 0, 0, False, 0, "paid"),
    (68_000, CustomerTier.STANDARD, 5, 2, 0, False, 0, "promise_kept"),
    (120_000, CustomerTier.GOLD, 8, 5, 12, False, 0, "promise_kept"),
    (31_000, CustomerTier.STANDARD, 4, 0, 7, False, 0, "promise_broken"),
    (90_000, CustomerTier.WATCH_LIST, 20, 0, 0, True, 2, "human_review"),
    (55_000, CustomerTier.STANDARD, 9, 8, 0, False, 0, "promise_kept"),
    (76_000, CustomerTier.GOLD, 3, 3, 4, False, 0, "paid"),
    (28_000, CustomerTier.STANDARD, 14, 0, 2, False, 1, "promise_broken"),
    (145_000, CustomerTier.WATCH_LIST, 25, 2, 1, False, 0, "human_review"),
    (39_000, CustomerTier.STANDARD, 6, 1, 0, False, 0, "promise_kept"),
    (82_000, CustomerTier.GOLD, 7, 0, 10, False, 0, "promise_kept"),
    (64_000, CustomerTier.STANDARD, 11, 12, 0, False, 0, "promise_broken"),
    (110_000, CustomerTier.WATCH_LIST, 18, 0, 0, False, 3, "human_review"),
    (47_000, CustomerTier.GOLD, 1, 0, 0, False, 0, "paid"),
    (73_000, CustomerTier.STANDARD, 10, 2, 3, False, 0, "promise_kept"),
]
_SCENARIOS = [Scenario(f"SIM-{i:03d}", *values) for i, values in enumerate(_INPUTS, start=1)]


def run_batch_recovery() -> dict:
    """Run fixed scenarios and write an auditable report."""
    policy = MockContextProvider().get_policy()
    results: list[Result] = []
    for scenario in _SCENARIOS:
        proposal = ActionProposal(
            invoice_id=scenario.invoice_id, customer_id="SIMULATED",
            action_type=ActionType.RECORD_PROMISE,
            proposed_discount_pct=scenario.discount,
            proposed_extension_days=scenario.extension,
            source_agent="batch_recovery_simulation", rationale="Fixed simulation scenario.",
        )
        decision = evaluate(
            proposal, policy,
            CustomerFacts(tier=scenario.tier, has_open_dispute=scenario.disputed,
                          broken_promise_count=scenario.broken_promises),
        )
        effective = decision.modified_proposal or proposal
        recovered = (
            round(scenario.amount * (1 - effective.proposed_discount_pct / 100), 2)
            if decision.verdict.value in {"allow", "modify"}
            and scenario.response in {"paid", "promise_kept"}
            else 0.0
        )
        results.append(Result(scenario.invoice_id, scenario.amount, decision.verdict.value,
                              scenario.response, recovered))

    total_due = sum(result.amount for result in results)
    total_recovered = sum(result.recovered_amount for result in results)
    report = {
        "label": "Deterministic recovery simulation — not production performance.",
        "as_of": date.today().isoformat(), "scenario_count": len(results),
        "total_due": total_due, "total_recovered": total_recovered,
        "recovery_rate_pct": round(total_recovered / total_due * 100, 1),
        "verdict_counts": {v: sum(r.verdict == v for r in results)
                           for v in ("allow", "modify", "reject", "human_approval")},
        "results": [asdict(result) for result in results],
    }
    _REPORT_PATH.parent.mkdir(exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    report = run_batch_recovery()
    print(f"Simulated recovery: ₹{report['total_recovered']:,.0f} / ₹{report['total_due']:,.0f} ({report['recovery_rate_pct']}%) across {report['scenario_count']} invoices.")
