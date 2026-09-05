"""Promise To Pay Pydantic Schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PromiseCreate(BaseModel):
    invoice_id: str
    customer_id: str
    amount: float = Field(gt=0.0)
    promised_date: date


class PromiseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    promise_id: str
    invoice_id: str
    customer_id: str
    amount: float
    promised_date: date
    status: str
    created_at: datetime
    updated_at: datetime


class PromiseMarkPaid(BaseModel):
    paid_date: date | None = None
    payment_reference: str | None = None
