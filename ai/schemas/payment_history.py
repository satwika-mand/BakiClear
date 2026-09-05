"""Payment history: raw records (input) and PaymentBehavior (agent output)."""

from datetime import date

from pydantic import BaseModel, Field


class PaymentRecord(BaseModel):
    """One past invoice's outcome. Raw input used by the Payment History Agent."""

    invoice_id: str
    due_date: date
    paid_date: date | None = None
    amount: float
    was_disputed: bool = False
    broken_promise: bool = Field(
        default=False, description="A prior promise-to-pay on this invoice was not honored"
    )


class PaymentBehavior(BaseModel):
    """Output of the Payment History Agent. All numeric fields are computed
    deterministically in Python from PaymentRecord history — never by the LLM.
    `behavioral_summary` is the only LLM-authored field."""

    customer_id: str
    total_invoices: int
    on_time_payment_pct: float = Field(ge=0, le=100)
    average_delay_days: float
    dispute_count: int
    broken_promise_count: int
    behavioral_summary: str = Field(
        description="One or two sentences summarizing payment reliability in plain language"
    )
