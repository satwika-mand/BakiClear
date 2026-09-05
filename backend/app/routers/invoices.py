"""Invoices API Router."""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.database import get_db
from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.schemas.invoice import InvoiceDetailResponse
from backend.app.seed import seed_database

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])


@router.get("", response_model=list[InvoiceDetailResponse])
def list_invoices(
    status: str | None = Query(None, description="Filter by status: overdue, in_negotiation, paid, pending"),
    segment: str | None = Query(None, description="Filter by customer segment: gold, standard, at_risk, new"),
    min_days_overdue: int | None = Query(None, ge=0, description="Minimum days overdue"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List invoices with optional filters for collections management."""
    stmt = (
        select(Invoice)
        .join(Customer, Invoice.customer_id == Customer.customer_id)
        .options(joinedload(Invoice.customer))
    )

    if status:
        stmt = stmt.where(Invoice.status == status)
    if segment:
        stmt = stmt.where(Customer.segment == segment)
    if min_days_overdue is not None:
        stmt = stmt.where(Invoice.days_overdue >= min_days_overdue)

    stmt = stmt.order_by(Invoice.days_overdue.desc(), Invoice.amount.desc()).offset(offset).limit(limit)
    invoices = db.scalars(stmt).all()

    results = []
    for inv in invoices:
        results.append(
            InvoiceDetailResponse(
                invoice_id=inv.invoice_id,
                customer_id=inv.customer_id,
                amount=inv.amount,
                issue_date=inv.issue_date,
                due_date=inv.due_date,
                paid_date=inv.paid_date,
                status=inv.status,
                days_overdue=inv.days_overdue,
                created_at=inv.created_at,
                updated_at=inv.updated_at,
                customer_name=inv.customer.name,
                customer_segment=inv.customer.segment,
                customer_email=inv.customer.email,
                customer_phone=inv.customer.phone,
            )
        )
    return results


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single invoice."""
    stmt = (
        select(Invoice)
        .where(Invoice.invoice_id == invoice_id)
        .options(joinedload(Invoice.customer))
    )
    inv = db.scalars(stmt).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' not found.",
        )

    return InvoiceDetailResponse(
        invoice_id=inv.invoice_id,
        customer_id=inv.customer_id,
        amount=inv.amount,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        paid_date=inv.paid_date,
        status=inv.status,
        days_overdue=inv.days_overdue,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        customer_name=inv.customer.name,
        customer_segment=inv.customer.segment,
        customer_email=inv.customer.email,
        customer_phone=inv.customer.phone,
    )


@router.post("/seed", status_code=status.HTTP_201_CREATED)
def trigger_seed(
    reset: bool = Query(True, description="Wipe existing records before seeding"),
    db: Session = Depends(get_db),
):
    """Seed synthetic realistic dataset (200 customers, 300 invoices)."""
    result = seed_database(db, reset=reset)
    return result
