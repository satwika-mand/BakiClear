"""Action Audit Log SQLAlchemy 2.0 Model with Idempotency."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.invoice import Invoice
    from backend.app.models.negotiation import NegotiationSession

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class ActionLog(Base):
    __tablename__ = "actions_log"

    action_id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    session_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("negotiation_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # discount_offer, due_date_extension, payment_plan, escalation
    requested_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # approved, rejected, escalated
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # ai_agent, policy_engine, human_agent
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="actions")
    session: Mapped[NegotiationSession | None] = relationship("NegotiationSession", back_populates="actions")
