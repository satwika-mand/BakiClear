"""BakiClear FastAPI Application Entrypoint.

Architecture principle:
LLM proposes. Policy decides. Backend executes. Database records.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import backend.app.models as _models  # noqa: F401
from backend.app.config import settings
from backend.app.database import Base, engine, get_db
from backend.app.models.invoice import Invoice
from backend.app.routers import (
    actions,
    customers,
    invoices,
    metrics,
    negotiations,
    policy,
    promises,
)
from backend.app.services.razorpay_adapter import razorpay_adapter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database schema is created on application startup."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="BakiClear API",
    version="0.1.0",
    description="AI-Powered Collections Strategy & Negotiation Backend API",
    lifespan=lifespan,
)

# Configure CORS for Streamlit frontend and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(invoices.router)
app.include_router(customers.router)
app.include_router(negotiations.router)
app.include_router(promises.router)
app.include_router(policy.router)
app.include_router(actions.router)
app.include_router(metrics.router)


# Health Check
@app.get("/api/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Verify backend and database operational readiness."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "status": "healthy",
        "database": db_status,
        "version": "0.1.0",
        "environment": settings.environment,
    }


# Razorpay Payment Link Generation (Isolated behind Adapter)
class PaymentLinkRequest(BaseModel):
    invoice_id: str
    description: str = "BakiClear Overdue Invoice Settlement"


@app.post("/api/payments/create-link", tags=["Payments"])
def create_invoice_payment_link(
    payload: PaymentLinkRequest,
    db: Session = Depends(get_db),
):
    """Generate a Razorpay payment link for an invoice via the isolated RazorpayAdapter."""
    inv = db.get(Invoice, payload.invoice_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{payload.invoice_id}' not found.",
        )

    link_info = razorpay_adapter.create_payment_link(
        invoice_id=inv.invoice_id,
        amount=inv.amount,
        customer_name=inv.customer.name,
        customer_email=inv.customer.email,
        customer_phone=inv.customer.phone,
        description=payload.description,
    )
    return link_info


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
