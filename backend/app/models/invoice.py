"""Invoice SQLAlchemy 2.0 Model."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.action_log import ActionLog
    from backend.app.models.customer import Customer
    from backend.app.models.negotiation import NegotiationSession
    from backend.app.models.promise import PromiseToPay

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    customer_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, overdue, paid, in_negotiation
    days_overdue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="invoices")
    promises: Mapped[list[PromiseToPay]] = relationship(
        "PromiseToPay", back_populates="invoice", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[NegotiationSession]] = relationship(
        "NegotiationSession", back_populates="invoice", cascade="all, delete-orphan"
    )
    actions: Mapped[list[ActionLog]] = relationship(
        "ActionLog", back_populates="invoice", cascade="all, delete-orphan"
    )
