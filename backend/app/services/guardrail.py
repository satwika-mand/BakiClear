"""Deterministic backend guardrails for financial commitments.

This module deliberately has no dependency on Gemini, HTTP clients, or the AI
orchestration package.  It produces verdict dictionaries that are safe to
persist in the audit trail and never changes a proposed financial value.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def policy_for(segment: str, policies: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return deterministic policy bounds for a customer segment."""
    defaults: dict[str, dict[str, Any]] = {
        "gold": {"max_discount_percent": 3.0, "max_extension_days": 10},
        "standard": {"max_discount_percent": 2.0, "max_extension_days": 7},
        "new": {"max_discount_percent": 1.0, "max_extension_days": 5},
        "at_risk": {"max_discount_percent": 0.0, "max_extension_days": 0},
        "watch_list": {"max_discount_percent": 0.0, "max_extension_days": 0},
    }
    return dict((policies or {}).get(segment, defaults.get(segment, defaults["standard"])))


def _verdict(*, allowed: bool, reason: str, route_to_human: bool = False) -> dict[str, Any]:
    return {"allowed": allowed, "route_to_human": route_to_human, "reason": reason}


def validate_concession(proposal: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Validate, but never mutate, an AI-proposed discount/extension."""
    discount = float(proposal.get("discount_percent", 0))
    extension = int(proposal.get("extension_days", 0))
    if discount < 0 or extension < 0:
        return _verdict(allowed=False, reason="Discount and extension must be non-negative.")
    if discount > float(policy.get("max_discount_percent", 0)):
        return _verdict(allowed=False, reason="Proposed discount exceeds segment policy.")
    if extension > int(policy.get("max_extension_days", 0)):
        return _verdict(allowed=False, reason="Proposed extension exceeds segment policy.")
    return _verdict(allowed=True, reason="Concession is within deterministic policy bounds.")


def validate_commitment(commitment: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Validate a payment commitment and enforce mandatory human routing."""
    amount = float(commitment.get("amount", 0))
    invoice_amount = float(commitment.get("invoice_amount", 0))
    days_overdue = int(commitment.get("days_overdue", 0))
    segment = str(commitment.get("segment", "standard"))
    promised_date = commitment.get("promised_date")
    if amount <= 0 or amount > invoice_amount:
        return _verdict(allowed=False, reason="Commitment amount must be positive and no greater than the invoice amount.")
    if isinstance(promised_date, date) and promised_date < date.today():
        return _verdict(allowed=False, reason="Commitment date cannot be in the past.")
    if days_overdue >= 15 or segment == "watch_list":
        return _verdict(allowed=False, route_to_human=True, reason="Overdue/watch-list commitment requires human approval.")
    return _verdict(allowed=True, reason="Commitment is valid for autonomous processing.")
