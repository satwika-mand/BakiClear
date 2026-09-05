"""Customer SQLAlchemy 2.0 Model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.invoice import Invoice
    from backend.app.models.payment_history import PaymentHistory
    from backend.app.models.promise import PromiseToPay

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # gold, standard, at_risk, new
    tenure_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    relationship_criticality: Mapped[str] = mapped_column(String(50), default="medium", nullable=False)  # high, medium, low
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice", back_populates="customer", cascade="all, delete-orphan"
    )
    payment_records: Mapped[list[PaymentHistory]] = relationship(
        "PaymentHistory", back_populates="customer", cascade="all, delete-orphan"
    )
    promises: Mapped[list[PromiseToPay]] = relationship(
        "PromiseToPay", back_populates="customer", cascade="all, delete-orphan"
    )
