"""Customer and AI Context Pydantic Schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CustomerBase(BaseModel):
    customer_id: str
    name: str
    segment: str
    tenure_months: int
    lifetime_value: float
    relationship_criticality: str
    email: str
    phone: str


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime


class PaymentHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_id: str
    amount: float
    due_date: str
    paid_date: str | None = None
    days_to_pay: int
    status: str
    disputed: bool


class CustomerHistoryResponse(BaseModel):
    customer_id: str
    total_records: int
    on_time_percentage: float
    average_payment_delay: float
    disputes: int
    broken_promises: int
    records: list[PaymentHistoryItem]


# Context contract specifically designed for Person 2's AI Workflow
class AIInvoiceContext(BaseModel):
    invoice_id: str
    amount: float
    days_overdue: int
    status: str


class AICustomerContext(BaseModel):
    customer_id: str
    name: str
    segment: str
    tenure_months: int
    lifetime_value: float
    relationship_criticality: str


class AIPaymentHistoryContext(BaseModel):
    on_time_percentage: float
    average_payment_delay: float
    disputes: int
    broken_promises: int
    total_payments_recorded: int


class AIRiskAssessmentContext(BaseModel):
    risk_score: float
    risk_tier: str
    priority: str
    recommended_action: str
    score_breakdown: dict[str, Any]


class AIPolicyBoundsContext(BaseModel):
    max_discount_percent: float
    max_extension_days: int
    requires_human_approval: bool
    enabled: bool


class AIContextResponse(BaseModel):
    """Payload consumed by AI Collection Strategy & Negotiation agents."""
    invoice: AIInvoiceContext
    customer: AICustomerContext
    payment_history: AIPaymentHistoryContext
    risk_assessment: AIRiskAssessmentContext
    policy_bounds: AIPolicyBoundsContext
