# BakiClear Backend API Contracts & Integration Guide

> **Audience**: Person 2 (AI/Agent/Frontend Engineer)  
> **Source of Truth**: Person 1 (Backend/Data Engineer)  
> **Base URL**: `http://localhost:8000`  
> **Interactive Swagger UI**: `http://localhost:8000/docs`

---

## 1. Quickstart & Running the Backend

### Start the Server
```bash
# Using uv (or directly with .venv)
uv run uvicorn backend.main:app --reload --port 8000
# or
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

### Reseed Database (CLI or API)
```bash
# Via CLI
.venv/bin/python -m backend.app.seed

# Via API
curl -X POST http://localhost:8000/api/invoices/seed
```
*Seeds 200 diverse customers, 300 invoices, 600+ payment ledger records, 4 merchant policy tiers, and sample negotiation records.*

---

## 2. Core Integration Endpoints for Person 2

### A. AI Context Endpoint (High Value)
**Route**: `GET /api/customers/{customer_id}/context?invoice_id={invoice_id}`  
**Purpose**: Primary data payload for Gemini collections strategy and negotiation agents. All arithmetic is deterministic.

#### Sample Request
```bash
curl http://localhost:8000/api/customers/CUS_1001/context
```

#### Sample Response
```json
{
  "invoice": {
    "invoice_id": "INV_2001",
    "amount": 185000.0,
    "days_overdue": 17,
    "status": "overdue"
  },
  "customer": {
    "customer_id": "CUS_1001",
    "name": "Aarav Tech Solutions",
    "segment": "gold",
    "tenure_months": 38,
    "lifetime_value": 1850000.0,
    "relationship_criticality": "high"
  },
  "payment_history": {
    "on_time_percentage": 92.5,
    "average_payment_delay": 1.8,
    "disputes": 0,
    "broken_promises": 0,
    "total_payments_recorded": 5
  },
  "risk_assessment": {
    "risk_score": 31.2,
    "risk_tier": "medium",
    "priority": "medium",
    "recommended_action": "Standard reminder with small grace extension",
    "score_breakdown": {
      "overdue_component": 7.5,
      "amount_component": 9.2,
      "reliability_deficit_component": 1.9,
      "behavioral_penalty_component": 0.0,
      "segment_modifier": -10.0
    }
  },
  "policy_bounds": {
    "max_discount_percent": 3.0,
    "max_extension_days": 10,
    "requires_human_approval": false,
    "enabled": true
  }
}
```

---

### B. Negotiation Sessions & Turns
**Initiate / Get Session**: `POST /api/negotiate/{invoice_id}`  
Automatically switches invoice status to `in_negotiation` and returns existing active session or initializes a new one.

```json
{
  "session_id": "SES_1A2B3C4D",
  "invoice_id": "INV_2001",
  "customer_id": "CUS_1001",
  "channel": "chat",
  "status": "active",
  "turns": []
}
```

**Append Dialogue Turn**: `POST /api/negotiations/{session_id}/turn`
```json
// Request
{
  "speaker": "ai", // "ai", "customer", or "system"
  "message": "We can offer a 2% discount if settled by this Friday.",
  "intent": "offer_discount"
}

// Response: 201 Created with persisted turn ID and timestamp
```

**Get Session Transcript**: `GET /api/negotiations/{session_id}`

---

### C. Financial Actions & Guardrail Audit Log (Idempotent)
**Route**: `POST /api/actions`  
**Purpose**: Persist every financial offer/decision made during negotiations. Guarantees deduplication via `idempotency_key`.

#### Request
```json
{
  "invoice_id": "INV_2001",
  "session_id": "SES_1A2B3C4D",
  "action_type": "discount_offer",
  "decision": "approved", // "approved", "rejected", "escalated"
  "reason": "Requested 2.0% within gold segment limit of 3.0%",
  "actor": "policy_engine", // "ai_agent", "policy_engine", "human_agent"
  "requested_value": "2.0%",
  "approved_value": "2.0%",
  "idempotency_key": "INV_2001:discount_offer:2026-09-05"
}
```

#### Idempotency Behavior
If an action with the specified `idempotency_key` already exists, the API returns the existing record rather than creating a duplicate financial entry.

---

### D. Promises to Pay Workflow
**Create Promise**: `POST /api/promises`
```json
// Request
{
  "invoice_id": "INV_2001",
  "customer_id": "CUS_1001",
  "amount": 185000.0,
  "promised_date": "2026-09-18"
}

// Response: 201 Created with status "pending"
```

**Mark Promise Paid**: `POST /api/promises/{promise_id}/mark-paid`
- Marks promise status as `"kept"`.
- Automatically transitions underlying invoice status to `"paid"` and resets `days_overdue` to 0.

---

### E. Merchant Policy Configuration
- `GET /api/policy`: List policies across all 4 customer segments (`gold`, `standard`, `at_risk`, `new`).
- `PUT /api/policy/{segment}`: Modify bounds (e.g. increase max discount or change human approval requirement).

---

### F. Metrics & KPI Summary (for Streamlit Dashboard)
**Route**: `GET /api/metrics/summary`  
Returns aggregated operational recovery metrics:
```json
{
  "total_overdue_amount": 42500000.0,
  "total_recovered_amount": 1850000.0,
  "recovery_rate_percent": 4.2,
  "total_invoices_count": 300,
  "overdue_invoices_count": 210,
  "in_negotiation_count": 45,
  "paid_invoices_count": 45,
  "promises_created": 30,
  "promises_kept": 12,
  "promises_broken": 4,
  "promises_pending": 14,
  "human_escalations_count": 5,
  "guardrail_blocks_count": 8,
  "segment_breakdown": {
    "gold": { "total_invoices": 60, "overdue_amount": 8500000.0, "recovered_amount": 1200000.0 },
    "standard": { "total_invoices": 140, "overdue_amount": 21000000.0, "recovered_amount": 500000.0 },
    "at_risk": { "total_invoices": 60, "overdue_amount": 11500000.0, "recovered_amount": 150000.0 },
    "new": { "total_invoices": 40, "overdue_amount": 1500000.0, "recovered_amount": 0.0 }
  }
}
```

---

### G. Razorpay Payment Links (Adapter Pattern)
**Route**: `POST /api/payments/create-link`
```json
// Request
{
  "invoice_id": "INV_2001"
}

// Response
{
  "id": "plink_98a7bc12",
  "invoice_id": "INV_2001",
  "amount": 185000.0,
  "currency": "INR",
  "status": "created",
  "short_url": "https://rzp.io/i/plink_98",
  "is_mock": true
}
```
*(Automatically toggles between Mock and Live when `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are provided in `.env`)*
