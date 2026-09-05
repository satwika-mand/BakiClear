"""The overdue invoice being worked. Input model, sourced from backend/mock."""

from datetime import date

from pydantic import BaseModel


class Invoice(BaseModel):
    invoice_id: str
    customer_id: str
    amount_due: float
    currency: str = "INR"
    due_date: date
    days_overdue: int
    description: str | None = None
