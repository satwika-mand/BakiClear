# BakiClear demo runbook

## Scenario A — autonomous, policy-bounded payment

1. Start FastAPI and Streamlit with `CONTEXT_SOURCE=api`.
2. Select a low/medium overdue invoice in **Queue**, then open **Negotiation**.
3. Enter: `I will pay the full amount today.`
4. After ALLOW/MODIFY and a promise, choose **Pay Now**.
5. The UI creates a Razorpay Standard Checkout order and displays the Test Checkout button.

For payable Test Mode checkout, set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
and `RAZORPAY_USE_MOCK=false`, then restart FastAPI. The secret never reaches
the browser; checkout receives only Razorpay's public key and the order ID.

## Scenario B — disputed amount → human queue

Enter: `I dispute this amount; I already made a partial payment.` The AI
extracts `disputes_amount`, persists an escalated action, and the backend
idempotently creates a HumanTask. Show it in **Human Queue**.

## Scenario C — checkout fallback

If Test Checkout is unavailable during a recording, use Swagger at
`http://127.0.0.1:8000/docs`:

1. `POST /api/negotiations/{invoice_id}/create-order`
2. In mock mode, call `POST /api/negotiations/{invoice_id}/verify-payment`
   using the returned order ID, a `pay_mock_*` payment ID, signature
   `mock_signature`, and a unique idempotency key.
3. `GET /api/negotiations/{invoice_id}/status` confirms paid status.

## Batch recovery simulation

Run `python -m ai.batch_recovery`. It writes
`eval_reports/batch_recovery.json` for 15 synthetic cases. Describe it as a
policy-branch simulation, not historical production recovery.
