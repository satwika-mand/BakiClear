"""Output of the deterministic Risk / Priority Engine. Pure Python, no LLM —
this schema exists so the rest of the pipeline has a typed contract to consume,
not because an LLM produces it."""

from pydantic import BaseModel, Field

from ai.schemas.enums import PriorityLevel, RiskLevel


class RiskAssessment(BaseModel):
    customer_id: str
    invoice_id: str
    risk_score: int = Field(ge=0, le=100, description="0=lowest risk, 100=highest risk")
    risk_level: RiskLevel
    priority_score: int = Field(ge=0, le=100, description="0=lowest priority, 100=most urgent")
    priority_level: PriorityLevel
    contributing_factors: list[str] = Field(
        description="Short factor labels, e.g. '45 days overdue', '2 broken promises', "
        "'open dispute' — used to explain the score in the UI"
    )
