from datetime import date, timedelta

from backend.app.services.guardrail import policy_for, validate_commitment, validate_concession


def test_concession_exceeding_policy_is_rejected_without_mutation():
    proposal = {"discount_percent": 5, "extension_days": 3}
    verdict = validate_concession(proposal, policy_for("gold"))

    assert verdict["allowed"] is False
    assert verdict["route_to_human"] is False
    assert proposal == {"discount_percent": 5, "extension_days": 3}


def test_commitment_at_fifteen_days_routes_to_human():
    verdict = validate_commitment(
        {
            "amount": 500,
            "invoice_amount": 500,
            "promised_date": date.today() + timedelta(days=1),
            "days_overdue": 15,
            "segment": "standard",
        },
        policy_for("standard"),
    )

    assert verdict == {
        "allowed": False,
        "route_to_human": True,
        "reason": "Overdue/watch-list commitment requires human approval.",
    }


def test_watch_list_commitment_routes_to_human():
    verdict = validate_commitment(
        {
            "amount": 1,
            "invoice_amount": 1,
            "promised_date": date.today(),
            "days_overdue": 1,
            "segment": "watch_list",
        },
        policy_for("watch_list"),
    )

    assert verdict["route_to_human"] is True


def test_dispute_and_broken_promises_route_to_human():
    base = {
        "amount": 100,
        "invoice_amount": 100,
        "promised_date": date.today() + timedelta(days=1),
        "days_overdue": 2,
        "segment": "standard",
    }
    assert validate_commitment({**base, "has_open_dispute": True}, policy_for("standard"))["route_to_human"]
    assert validate_commitment({**base, "broken_promise_count": 2}, policy_for("standard"))["route_to_human"]
