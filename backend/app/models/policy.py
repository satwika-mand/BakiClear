"""Policy Configuration SQLAlchemy 2.0 Model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class PolicyConfig(Base):
    __tablename__ = "policy_config"

    segment: Mapped[str] = mapped_column(String(50), primary_key=True)  # gold, standard, at_risk, new
    max_discount_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_extension_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
