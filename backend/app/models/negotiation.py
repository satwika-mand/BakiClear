"""Negotiation Sessions and Turns SQLAlchemy 2.0 Models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.action_log import ActionLog
    from backend.app.models.invoice import Invoice

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class NegotiationSession(Base):
    __tablename__ = "negotiation_sessions"

    session_id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    invoice_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(50), default="chat", nullable=False)  # voice, chat, email
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False, index=True
    )  # active, concluded, escalated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="sessions")
    turns: Mapped[list[NegotiationTurn]] = relationship(
        "NegotiationTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="NegotiationTurn.timestamp",
    )
    actions: Mapped[list[ActionLog]] = relationship(
        "ActionLog", back_populates="session"
    )


class NegotiationTurn(Base):
    __tablename__ = "negotiation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("negotiation_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
    )
    speaker: Mapped[str] = mapped_column(String(50), nullable=False)  # ai, customer, system
    message: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    session: Mapped[NegotiationSession] = relationship("NegotiationSession", back_populates="turns")
