"""Metrics Summary Pydantic Schema."""


from pydantic import BaseModel


class SegmentMetrics(BaseModel):
    total_invoices: int
    overdue_amount: float
    recovered_amount: float


class MetricsSummaryResponse(BaseModel):
    total_overdue_amount: float
    total_recovered_amount: float
    recovery_rate_percent: float
    total_invoices_count: int
    overdue_invoices_count: int
    in_negotiation_count: int
    paid_invoices_count: int
    promises_created: int
    promises_kept: int
    promises_broken: int
    promises_pending: int
    human_escalations_count: int
    guardrail_blocks_count: int
    segment_breakdown: dict[str, SegmentMetrics]
