"""Policy Configuration Pydantic Schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyConfigBase(BaseModel):
    segment: str
    max_discount_percent: float = Field(ge=0.0, le=100.0)
    max_extension_days: int = Field(ge=0, le=365)
    requires_human_approval: bool
    enabled: bool = True


class PolicyConfigResponse(PolicyConfigBase):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime


class PolicyConfigUpdate(BaseModel):
    max_discount_percent: float | None = Field(None, ge=0.0, le=100.0)
    max_extension_days: int | None = Field(None, ge=0, le=365)
    requires_human_approval: bool | None = None
    enabled: bool | None = None
