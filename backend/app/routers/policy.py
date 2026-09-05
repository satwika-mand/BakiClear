"""Policy Configuration API Router."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.policy import PolicyConfig
from backend.app.schemas.policy import PolicyConfigResponse, PolicyConfigUpdate

router = APIRouter(prefix="/api/policy", tags=["Policy Engine Bounds"])


@router.get("", response_model=list[PolicyConfigResponse])
def list_policies(db: Session = Depends(get_db)):
    """Retrieve all merchant policy bounds across customer segments."""
    stmt = select(PolicyConfig).order_by(PolicyConfig.segment.asc())
    policies = db.scalars(stmt).all()
    return policies


@router.get("/{segment}", response_model=PolicyConfigResponse)
def get_policy(segment: str, db: Session = Depends(get_db)):
    """Retrieve policy limits for a specific segment."""
    policy = db.get(PolicyConfig, segment.lower())
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy configuration for segment '{segment}' not found.",
        )
    return policy


@router.put("/{segment}", response_model=PolicyConfigResponse)
def update_policy(
    segment: str,
    update_in: PolicyConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update policy configuration bounds (max discount, max extension, approval requirement)."""
    policy = db.get(PolicyConfig, segment.lower())
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy configuration for segment '{segment}' not found.",
        )

    if update_in.max_discount_percent is not None:
        policy.max_discount_percent = update_in.max_discount_percent
    if update_in.max_extension_days is not None:
        policy.max_extension_days = update_in.max_extension_days
    if update_in.requires_human_approval is not None:
        policy.requires_human_approval = update_in.requires_human_approval
    if update_in.enabled is not None:
        policy.enabled = update_in.enabled

    policy.updated_at = datetime.now()
    db.commit()
    db.refresh(policy)
    return policy
