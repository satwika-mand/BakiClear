"""Promise To Pay SQLAlchemy 2.0 Model."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.customer import Customer
    from backend.app.models.invoice import Invoice

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    promise_id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    invoice_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    promised_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )  # pending, kept, broken
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="promises")
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="promises")
