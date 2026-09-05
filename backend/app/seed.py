"""Synthetic data generator for BakiClear demo and testing.

Generates realistic collections data with deterministic variance:
- 200 customers across gold, standard, at_risk, and new segments.
- 300 invoices with amounts ₹5,000 - ₹4,00,000 and overdue days 1 - 90.
- Realistic payment histories, disputes, and broken promises.
- Preconfigured merchant policy rules.
"""

import random
from datetime import date, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.database import Base, SessionLocal, engine
from backend.app.models.action_log import ActionLog
from backend.app.models.customer import Customer
from backend.app.models.invoice import Invoice
from backend.app.models.negotiation import NegotiationSession, NegotiationTurn
from backend.app.models.payment_history import PaymentHistory
from backend.app.models.policy import PolicyConfig
from backend.app.models.promise import PromiseToPay

FIRST_NAMES = [
    "Aarav", "Aditi", "Rohan", "Priya", "Vikram", "Neha", "Rahul", "Ananya", "Sanjay", "Kavita",
    "Deepak", "Pooja", "Arjun", "Sneha", "Karan", "Sunita", "Amit", "Meera", "Rajesh", "Divya",
    "Suresh", "Ishaan", "Ritu", "Manish", "Preeti", "Naveen", "Swati", "Alok", "Shreya", "Gaurav",
    "Nidhi", "Tarun", "Tanvi", "Sachin", "Bhavna", "Kunal", "Simran", "Varun", "Shruti", "Harish",
]

COMPANY_SUFFIXES = [
    "Enterprises", "Logistics", "Tech Solutions", "Retailers", "Textiles", "Industries",
    "Consulting", "Electronics", "Foods", "Trading Co", "Motors", "Healthcare", "Infotech",
    "Exports", "Media", "Packaging", "Supplies", "Engineering", "Digital", "Pharma",
]


def seed_policy_configs(db: Session) -> None:
    """Seed merchant policy bounds for each segment."""
    default_policies = [
        PolicyConfig(
            segment="gold",
            max_discount_percent=3.0,
            max_extension_days=10,
            requires_human_approval=False,
            enabled=True,
        ),
        PolicyConfig(
            segment="standard",
            max_discount_percent=2.0,
            max_extension_days=7,
            requires_human_approval=False,
            enabled=True,
        ),
        PolicyConfig(
            segment="at_risk",
            max_discount_percent=0.0,
            max_extension_days=3,
            requires_human_approval=True,
            enabled=True,
        ),
        PolicyConfig(
            segment="new",
            max_discount_percent=1.0,
            max_extension_days=5,
            requires_human_approval=False,
            enabled=True,
        ),
    ]
    for policy in default_policies:
        db.merge(policy)


def seed_database(db: Session, reset: bool = True) -> dict:
    """Seed full synthetic database with 200 customers and 300 invoices."""
    rng = random.Random(42)  # Deterministic seed for reproducible demo datasets
    today = date.today()

    if reset:
        # Clear existing data in reverse order of foreign keys
        db.execute(delete(ActionLog))
        db.execute(delete(NegotiationTurn))
        db.execute(delete(NegotiationSession))
        db.execute(delete(PromiseToPay))
        db.execute(delete(PaymentHistory))
        db.execute(delete(Invoice))
        db.execute(delete(Customer))
        db.execute(delete(PolicyConfig))
        db.commit()

    # 1. Seed Policies
    seed_policy_configs(db)

    # 2. Seed 200 Customers
    # Distribution: 40 gold, 90 standard, 40 at_risk, 30 new
    segments_distribution = (
        ["gold"] * 40 +
        ["standard"] * 90 +
        ["at_risk"] * 40 +
        ["new"] * 30
    )
    rng.shuffle(segments_distribution)

    customers: list[Customer] = []
    for i, seg in enumerate(segments_distribution, start=1001):
        cid = f"CUS_{i}"
        first_name = rng.choice(FIRST_NAMES)
        company = f"{first_name} {rng.choice(COMPANY_SUFFIXES)}"

        if seg == "gold":
            tenure = rng.randint(24, 60)
            ltv = round(rng.uniform(500_000, 2_500_000), 2)
            criticality = rng.choice(["high", "high", "medium"])
        elif seg == "standard":
            tenure = rng.randint(12, 36)
            ltv = round(rng.uniform(150_000, 800_000), 2)
            criticality = rng.choice(["medium", "low"])
        elif seg == "at_risk":
            tenure = rng.randint(6, 24)
            ltv = round(rng.uniform(80_000, 400_000), 2)
            criticality = rng.choice(["medium", "low"])
        else:  # new
            tenure = rng.randint(1, 6)
            ltv = round(rng.uniform(20_000, 150_000), 2)
            criticality = "low"

        cust = Customer(
            customer_id=cid,
            name=company,
            segment=seg,
            tenure_months=tenure,
            lifetime_value=ltv,
            relationship_criticality=criticality,
            email=f"{first_name.lower()}.{cid.lower()}@example.in",
            phone=f"+91 98{rng.randint(10000000, 99999999)}",
        )
        customers.append(cust)
        db.add(cust)

    # 3. Seed 300 Invoices
    # Distribute 300 invoices across the 200 customers.
    # High-value customers may have multiple invoices.
    invoices: list[Invoice] = []
    inv_counter = 2001

    # Ensure every customer gets at least 1 invoice
    for cust in customers:
        inv_id = f"INV_{inv_counter}"
        inv_counter += 1

        # Amounts between ₹5,000 and ₹4,00,000
        if cust.segment == "gold":
            amount = round(rng.uniform(50_000, 400_000), 2)
            days_overdue = rng.randint(1, 20)  # gold has minor overdue
        elif cust.segment == "at_risk":
            amount = round(rng.uniform(30_000, 350_000), 2)
            days_overdue = rng.randint(30, 90)  # at_risk has chronic overdue
        elif cust.segment == "new":
            amount = round(rng.uniform(5_000, 100_000), 2)
            days_overdue = rng.randint(1, 30)
        else:  # standard
            amount = round(rng.uniform(15_000, 250_000), 2)
            days_overdue = rng.randint(5, 45)

        due_d = today - timedelta(days=days_overdue)
        issue_d = due_d - timedelta(days=rng.randint(15, 30))

        # Status: most are overdue, some in_negotiation, some paid
        status_roll = rng.random()
        if status_roll < 0.70:
            status = "overdue"
            paid_d = None
        elif status_roll < 0.85:
            status = "in_negotiation"
            paid_d = None
        else:
            status = "paid"
            paid_d = due_d + timedelta(days=rng.randint(1, 10))
            days_overdue = 0

        inv = Invoice(
            invoice_id=inv_id,
            customer_id=cust.customer_id,
            amount=amount,
            issue_date=issue_d,
            due_date=due_d,
            paid_date=paid_d,
            status=status,
            days_overdue=days_overdue,
        )
        invoices.append(inv)
        db.add(inv)

    # Add remaining 100 invoices to reach 300 total
    while len(invoices) < 300:
        cust = rng.choice(customers)
        inv_id = f"INV_{inv_counter}"
        inv_counter += 1

        amount = round(rng.uniform(10_000, 300_000), 2)
        days_overdue = rng.randint(1, 80) if cust.segment != "gold" else rng.randint(1, 15)
        due_d = today - timedelta(days=days_overdue)
        issue_d = due_d - timedelta(days=rng.randint(15, 30))
        status = rng.choice(["overdue", "overdue", "in_negotiation"])

        inv = Invoice(
            invoice_id=inv_id,
            customer_id=cust.customer_id,
            amount=amount,
            issue_date=issue_d,
            due_date=due_d,
            paid_date=None,
            status=status,
            days_overdue=days_overdue,
        )
        invoices.append(inv)
        db.add(inv)

    # 4. Seed Payment History (600+ records)
    # Giving each customer 2 to 5 historical payment records to form behavioral tracks
    history_records: list[PaymentHistory] = []
    for cust in customers:
        num_records = rng.randint(2, 5) if cust.segment != "new" else rng.randint(0, 2)
        for h_idx in range(num_records):
            hist_inv = f"PAST_{cust.customer_id}_{h_idx + 1}"
            hist_amount = round(rng.uniform(10_000, 200_000), 2)
            past_days_ago = rng.randint(40, 365)
            h_due = today - timedelta(days=past_days_ago)

            if cust.segment == "gold":
                days_to_pay = rng.randint(0, 3)
                status = "on_time"
                disputed = False
            elif cust.segment == "at_risk":
                # High delay / defaulted
                days_to_pay = rng.randint(10, 45)
                status = rng.choice(["delayed", "delayed", "defaulted"])
                disputed = (rng.random() < 0.40)  # 40% dispute rate for at_risk
            elif cust.segment == "standard":
                days_to_pay = rng.randint(0, 10)
                status = "on_time" if days_to_pay <= 3 else "delayed"
                disputed = (rng.random() < 0.10)
            else:  # new
                days_to_pay = rng.randint(0, 7)
                status = "on_time" if days_to_pay <= 3 else "delayed"
                disputed = False

            h_paid = h_due + timedelta(days=days_to_pay) if status != "defaulted" else None

            ph = PaymentHistory(
                customer_id=cust.customer_id,
                invoice_id=hist_inv,
                amount=hist_amount,
                due_date=h_due,
                paid_date=h_paid,
                days_to_pay=days_to_pay,
                status=status,
                disputed=disputed,
            )
            history_records.append(ph)
            db.add(ph)

    # 5. Seed Promises to Pay (30 sample promises)
    sample_promises: list[PromiseToPay] = []
    overdue_invoices = [inv for inv in invoices if inv.status == "overdue"]
    for i in range(min(30, len(overdue_invoices))):
        target_inv = overdue_invoices[i]
        p_status = rng.choice(["pending", "pending", "kept", "broken"])
        p_date = today + timedelta(days=rng.randint(3, 14)) if p_status == "pending" else today - timedelta(days=rng.randint(1, 10))

        p = PromiseToPay(
            promise_id=f"PRM_{100 + i}",
            invoice_id=target_inv.invoice_id,
            customer_id=target_inv.customer_id,
            amount=target_inv.amount,
            promised_date=p_date,
            status=p_status,
        )
        sample_promises.append(p)
        db.add(p)

    # 6. Seed Sample Negotiation Sessions, Turns & Action Logs for demo richness
    customer_segments = {customer.customer_id: customer.segment for customer in customers}
    for i in range(5):
        inv = overdue_invoices[i]
        ses_id = f"SES_{1001 + i}"
        session = NegotiationSession(
            session_id=ses_id,
            invoice_id=inv.invoice_id,
            customer_id=inv.customer_id,
            channel="chat",
            status="active",
        )
        db.add(session)

        t1 = NegotiationTurn(
            session_id=ses_id,
            speaker="ai",
            message=f"Hello, I am reaching out regarding overdue invoice {inv.invoice_id} of ₹{inv.amount:,.2f}. Can we arrange a payment schedule today?",
            intent="payment_reminder",
            timestamp=datetime.now() - timedelta(minutes=15),
        )
        t2 = NegotiationTurn(
            session_id=ses_id,
            speaker="customer",
            message="We faced a cash flow delay from our client. Can you offer a 5% discount or give us 10 more days?",
            intent="request_concession",
            timestamp=datetime.now() - timedelta(minutes=10),
        )
        db.add_all([t1, t2])

        # Action log recording policy enforcement
        action = ActionLog(
            action_id=f"ACT_{1001 + i}",
            session_id=ses_id,
            invoice_id=inv.invoice_id,
            action_type="discount_offer",
            requested_value="5%",
            approved_value="2%" if customer_segments[inv.customer_id] in ["gold", "standard"] else "0%",
            decision="approved" if customer_segments[inv.customer_id] in ["gold", "standard"] else "rejected",
            reason=f"Policy bounded for segment {customer_segments[inv.customer_id]}",
            actor="policy_engine",
            idempotency_key=f"{inv.invoice_id}:discount_offer:{today.isoformat()}",
            timestamp=datetime.now(),
        )
        db.add(action)

    db.commit()

    return {
        "customers_seeded": len(customers),
        "invoices_seeded": len(invoices),
        "payment_history_records_seeded": len(history_records),
        "promises_seeded": len(sample_promises),
        "status": "success",
    }


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db_session:
        result = seed_database(db_session, reset=True)
        print("Database seed completed successfully:")
        print(result)
