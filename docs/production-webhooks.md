# Production Razorpay webhook approach

The demo intentionally verifies Razorpay Standard Checkout from the client
callback and does not register a webhook. Before production, register a
Razorpay `payment.captured` webhook endpoint over HTTPS.

The endpoint should verify the `X-Razorpay-Signature` against the raw request
body using the webhook secret, then locate the promise by Razorpay order ID.
It must make the same atomic state transition used by
`POST /api/negotiations/{invoice_id}/verify-payment`: mark the promise kept,
mark the invoice paid, record the payment id, write the payment history and
audit trace. Store Razorpay's event ID as a unique idempotency key, returning
2xx for a repeat delivery only after confirming the already-recorded result.

Do not trust client-side success callbacks as the production source of truth;
use the webhook and reconcile it periodically with Razorpay's Orders/Payments
APIs. Keep `RAZORPAY_KEY_SECRET` and the webhook secret server-side only.
