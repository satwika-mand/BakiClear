"""Outcome measurement. Backs the Metrics screen and GET /api/metrics/summary."""

from pydantic import BaseModel, Field


class MetricsSummary(BaseModel):
    total_invoices_processed: int
    total_amount_due: float
    total_amount_promised: float
    recovery_rate_pct: float = Field(default=0.0, description="amount promised / amount due")
    promise_keeping_rate_pct: float = Field(
        default=0.0, description="kept / (kept + broken) among resolved promises"
    )
    human_escalations: int
    guardrail_rejections: int
    guardrail_modifications: int
