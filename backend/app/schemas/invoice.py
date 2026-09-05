"""Invoice Pydantic Schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class InvoiceBase(BaseModel):
    invoice_id: str
    customer_id: str
    amount: float
    issue_date: date
    due_date: date
    paid_date: date | None = None
    status: str
    days_overdue: int


class InvoiceResponse(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime


class InvoiceDetailResponse(InvoiceResponse):
    customer_name: str
    customer_segment: str
    customer_email: str
    customer_phone: str
