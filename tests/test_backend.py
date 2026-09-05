#DO NOT RUN AGAINST THE DEMO DATABASE
"""Automated Backend Pytest Suite for BakiClear P0 and P1 endpoints."""

import pytest
from fastapi.testclient import TestClient

from backend.app.database import Base, SessionLocal, engine
from backend.app.seed import seed_database
from backend.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure database schema is created and synthetic data is seeded for the test session."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db, reset=True)
    yield


@pytest.fixture
def client():
    """Provide TestClient instance."""
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    """Verify backend and database readiness."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_list_invoices(client):
    """Verify invoice listing and filtering."""
    response = client.get("/api/invoices?limit=10")
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) > 0
    first = invoices[0]
    assert "invoice_id" in first
    assert "amount" in first
    assert "days_overdue" in first
    assert "customer_segment" in first


def test_get_single_invoice(client):
    """Verify single invoice retrieval."""
    # Fetch first invoice
    res_list = client.get("/api/invoices?limit=1")
    inv_id = res_list.json()[0]["invoice_id"]

    res_single = client.get(f"/api/invoices/{inv_id}")
    assert res_single.status_code == 200
    assert res_single.json()["invoice_id"] == inv_id


def test_customer_history(client):
    """Verify customer payment history ledger and calculated metrics."""
    res_cust = client.get("/api/customers/CUS_1001/history")
    assert res_cust.status_code == 200
    data = res_cust.json()
    assert data["customer_id"] == "CUS_1001"
    assert "on_time_percentage" in data
    assert "average_payment_delay" in data
    assert isinstance(data["records"], list)


def test_ai_context_endpoint(client):
    """Verify the AI context endpoint designed for Person 2's AI Workflow."""
    response = client.get("/api/customers/CUS_1001/context")
    assert response.status_code == 200
    context = response.json()

    # Required contract keys
    assert "invoice" in context
    assert "customer" in context
    assert "payment_history" in context
    assert "risk_assessment" in context
    assert "policy_bounds" in context

    # Deterministic risk assessment checks
    assert "risk_score" in context["risk_assessment"]
    assert "risk_tier" in context["risk_assessment"]
    assert 0.0 <= context["risk_assessment"]["risk_score"] <= 100.0

    # Policy bounds
    assert "max_discount_percent" in context["policy_bounds"]
    assert "max_extension_days" in context["policy_bounds"]


def test_policy_crud(client):
    """Verify policy listing and bounds updating."""
    # List policies
    res_list = client.get("/api/policy")
    assert res_list.status_code == 200
    policies = res_list.json()
    assert len(policies) >= 4

    # Update gold policy
    update_data = {
        "max_discount_percent": 3.5,
        "max_extension_days": 12,
    }
    res_update = client.put("/api/policy/gold", json=update_data)
    assert res_update.status_code == 200
    updated = res_update.json()
    assert updated["max_discount_percent"] == 3.5
    assert updated["max_extension_days"] == 12


def test_promise_workflow(client):
    """Verify Promise-to-Pay creation and mark-paid lifecycle."""
    # Get an overdue invoice
    res_inv = client.get("/api/invoices?status=overdue&limit=1")
    assert len(res_inv.json()) > 0
    inv = res_inv.json()[0]

    # Create promise
    promise_data = {
        "invoice_id": inv["invoice_id"],
        "customer_id": inv["customer_id"],
        "amount": inv["amount"],
        "promised_date": "2026-09-20",
    }
    res_create = client.post("/api/promises", json=promise_data)
    assert res_create.status_code == 201
    promise = res_create.json()
    assert promise["status"] == "pending"
    promise_id = promise["promise_id"]

    # Mark paid
    res_paid = client.post(f"/api/promises/{promise_id}/mark-paid")
    assert res_paid.status_code == 200
    assert res_paid.json()["status"] == "kept"

    # Verify invoice status changed to paid
    res_check_inv = client.get(f"/api/invoices/{inv['invoice_id']}")
    assert res_check_inv.json()["status"] == "paid"


def test_action_logging_and_idempotency(client):
    """Verify financial action persistence and idempotency protection."""
    res_inv = client.get("/api/invoices?limit=1")
    inv_id = res_inv.json()[0]["invoice_id"]

    idempotency_key = f"{inv_id}:discount_offer:test_unique_key"
    payload = {
        "invoice_id": inv_id,
        "action_type": "discount_offer",
        "requested_value": "8%",
        "approved_value": "2%",
        "decision": "approved",
        "reason": "Within segment policy limits",
        "actor": "policy_engine",
        "idempotency_key": idempotency_key,
    }

    # First call - inserts record
    res1 = client.post("/api/actions", json=payload)
    assert res1.status_code == 201
    action1 = res1.json()

    # Second call with same idempotency key - returns existing record without duplicating
    res2 = client.post("/api/actions", json=payload)
    assert res2.status_code == 201
    action2 = res2.json()

    assert action1["action_id"] == action2["action_id"]


def test_negotiation_session_and_turns(client):
    """Verify negotiation initiation and conversation turn recording."""
    res_inv = client.get("/api/invoices?limit=1")
    inv_id = res_inv.json()[0]["invoice_id"]

    # Initiate negotiation
    res_ses = client.post(f"/api/negotiate/{inv_id}?channel=chat")
    assert res_ses.status_code == 200
    session_id = res_ses.json()["session_id"]

    # Append customer turn
    turn_data = {
        "speaker": "customer",
        "message": "Can I pay in two installments?",
        "intent": "installment_request",
    }
    res_turn = client.post(f"/api/negotiations/{session_id}/turn", json=turn_data)
    assert res_turn.status_code == 201
    assert res_turn.json()["speaker"] == "customer"

    # Retrieve session transcript
    res_get_ses = client.get(f"/api/negotiations/{session_id}")
    assert res_get_ses.status_code == 200
    turns = res_get_ses.json()["turns"]
    assert any(t["message"] == "Can I pay in two installments?" for t in turns)


def test_metrics_summary(client):
    """Verify aggregated metrics summary calculation."""
    response = client.get("/api/metrics/summary")
    assert response.status_code == 200
    metrics = response.json()

    assert "total_overdue_amount" in metrics
    assert "total_recovered_amount" in metrics
    assert "recovery_rate_percent" in metrics
    assert "promises_created" in metrics
    assert "promises_kept" in metrics
    assert "guardrail_blocks_count" in metrics
    assert "segment_breakdown" in metrics


def test_razorpay_mock_adapter(client):
    """Verify Razorpay payment link generation endpoint."""
    res_inv = client.get("/api/invoices?limit=1")
    inv_id = res_inv.json()[0]["invoice_id"]

    res_link = client.post("/api/payments/create-link", json={"invoice_id": inv_id})
    assert res_link.status_code == 200
    data = res_link.json()
    assert "id" in data
    assert "short_url" in data
    assert data["is_mock"] is True
