"""30-second demo scheduler for durable simulated WhatsApp reminders."""

import asyncio
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ai.agents.message import draft_message
from ai.agents.risk_engine import compute_payment_behavior
from ai.schemas import CustomerProfile, CustomerSegment, CustomerTier, PaymentRecord
from ai.schemas import Invoice as AIInvoice
from backend.app.database import SessionLocal
from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.models.message import Message
from backend.app.services.handoff import create_human_task


def run_message_cycle(db: Session) -> int:
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.status.in_(["overdue", "in_negotiation"]), Invoice.days_overdue >= 1
        ).options(
            joinedload(Invoice.customer).selectinload(Customer.payment_records),
            joinedload(Invoice.customer).selectinload(Customer.promises),
        )
    ).all()
    sent = 0
    for invoice in invoices:
        now = datetime.now()
        if invoice.last_contact_at and invoice.last_contact_at.replace(tzinfo=None) >= now - timedelta(seconds=30):
            continue
        customer = invoice.customer
        tier = "tier_3" if invoice.days_overdue >= 15 or customer.segment == "watch_list" else ("tier_2" if invoice.days_overdue >= 4 else "tier_1")
        profile = CustomerProfile(customer_id=customer.customer_id, name=customer.name,
            segment={"gold": CustomerSegment.ENTERPRISE, "standard": CustomerSegment.SMALL_BUSINESS, "at_risk": CustomerSegment.MID_MARKET, "new": CustomerSegment.INDIVIDUAL}.get(customer.segment, CustomerSegment.INDIVIDUAL),
            tier=CustomerTier.WATCH_LIST if customer.segment == "watch_list" else (CustomerTier.GOLD if customer.segment == "gold" else CustomerTier.STANDARD),
            customer_since=customer.created_at.date(), lifetime_value=customer.lifetime_value)
        history = [
            PaymentRecord(
                invoice_id=record.invoice_id,
                due_date=record.due_date,
                paid_date=record.paid_date,
                amount=record.amount,
                was_disputed=record.disputed,
                broken_promise=any(
                    promise.invoice_id == record.invoice_id and promise.status == "broken"
                    for promise in customer.promises
                ),
            )
            for record in customer.payment_records
        ]
        behavior = compute_payment_behavior(customer.customer_id, history)
        draft = draft_message(profile, AIInvoice(invoice_id=invoice.invoice_id, customer_id=invoice.customer_id,
            amount_due=invoice.amount, due_date=invoice.due_date, days_overdue=invoice.days_overdue), behavior, invoice.days_overdue)
        db.add(Message(message_id=f"MSG_{uuid.uuid4().hex[:12].upper()}", invoice_id=invoice.invoice_id,
            channel="whatsapp_sim", direction="outbound", tier=tier, body=draft.body))
        invoice.last_contact_at, invoice.contact_tier = now, tier
        if tier == "tier_3":
            create_human_task(db, invoice_id=invoice.invoice_id, customer_id=invoice.customer_id,
                reason="15+ days overdue or watch-list customer", priority="urgent")
        sent += 1
    db.commit()
    return sent


async def scheduler_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        # The scheduler uses synchronous SQLAlchemy. Running it in a worker
        # keeps an expensive 300-invoice demo cycle from blocking FastAPI's
        # event loop and making unrelated API requests time out.
        def run_cycle() -> None:
            with SessionLocal() as db:
                run_message_cycle(db)

        await asyncio.to_thread(run_cycle)
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            pass
