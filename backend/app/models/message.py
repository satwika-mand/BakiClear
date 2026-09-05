"""Persisted simulated outbound collection messages."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.invoice_id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="outbound")
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
