"""Negotiation Sessions and Conversation Turns Router."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.database import get_db
from backend.app.models.invoice import Invoice
from backend.app.models.negotiation import NegotiationSession, NegotiationTurn
from backend.app.schemas.negotiation import SessionResponse, TurnCreate, TurnResponse

router = APIRouter(tags=["Negotiations"])


@router.post("/api/negotiate/{invoice_id}", response_model=SessionResponse, status_code=status.HTTP_200_OK)
def initiate_or_get_negotiation(
    invoice_id: str,
    channel: str = "chat",
    db: Session = Depends(get_db),
):
    """Initiate a new negotiation session for an invoice or retrieve the existing active session."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' not found.",
        )

    # Check for active session
    stmt = (
        select(NegotiationSession)
        .where(
            NegotiationSession.invoice_id == invoice_id,
            NegotiationSession.status == "active",
        )
        .options(joinedload(NegotiationSession.turns))
    )
    existing_session = db.scalars(stmt).first()
    if existing_session:
        return existing_session

    # Create new session
    session_id = f"SES_{uuid.uuid4().hex[:8].upper()}"
    new_session = NegotiationSession(
        session_id=session_id,
        invoice_id=invoice_id,
        customer_id=inv.customer_id,
        channel=channel,
        status="active",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(new_session)

    # Update invoice status to in_negotiation if currently overdue
    if inv.status == "overdue":
        inv.status = "in_negotiation"

    db.commit()
    db.refresh(new_session)
    return new_session


@router.get("/api/negotiations/{session_id}", response_model=SessionResponse)
def get_negotiation_session(session_id: str, db: Session = Depends(get_db)):
    """Retrieve negotiation session state and conversation transcript."""
    stmt = (
        select(NegotiationSession)
        .where(NegotiationSession.session_id == session_id)
        .options(joinedload(NegotiationSession.turns))
    )
    session = db.scalars(stmt).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Negotiation session '{session_id}' not found.",
        )
    return session


@router.post("/api/negotiations/{session_id}/turn", response_model=TurnResponse, status_code=status.HTTP_201_CREATED)
def append_negotiation_turn(
    session_id: str,
    turn_in: TurnCreate,
    db: Session = Depends(get_db),
):
    """Append a dialogue turn (from AI agent, customer, or system) to the negotiation transcript."""
    session = db.get(NegotiationSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Negotiation session '{session_id}' not found.",
        )

    turn = NegotiationTurn(
        session_id=session_id,
        speaker=turn_in.speaker,
        message=turn_in.message,
        intent=turn_in.intent,
        timestamp=datetime.now(),
    )
    db.add(turn)
    session.updated_at = datetime.now()
    db.commit()
    db.refresh(turn)
    return turn
