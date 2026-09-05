"""Append-only audit trace for AI proposals and backend execution."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class AgentTrace(Base):
    __tablename__ = "agent_trace"

    trace_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.invoice_id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
