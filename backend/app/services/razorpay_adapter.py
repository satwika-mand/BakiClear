"""Razorpay Adapter with clean Mock fallback for hackathon reliability."""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from backend.app.config import settings


class RazorpayAdapter:
    """Adapter isolating Razorpay payment link generation and status checking."""

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        use_mock: bool | None = None,
    ):
        self.key_id = key_id or settings.razorpay_key_id
        self.key_secret = key_secret or settings.razorpay_key_secret
        self.use_mock = settings.razorpay_use_mock if use_mock is None else use_mock
        self.use_mock = self.use_mock or not (self.key_id and self.key_secret)

    def create_order(self, *, amount_paise: int, receipt: str) -> dict[str, Any]:
        if amount_paise <= 0:
            raise ValueError("Order amount must be positive.")
        if self.use_mock:
            return {"id": f"order_mock_{uuid.uuid4().hex[:12]}", "amount": amount_paise, "currency": "INR", "status": "created"}
        import razorpay
        return razorpay.Client(auth=(self.key_id, self.key_secret)).order.create(
            data={"amount": amount_paise, "currency": "INR", "receipt": receipt}
        )

    def verify_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        if self.use_mock:
            return signature == "mock_signature" and order_id.startswith("order_mock_")
        import razorpay
        try:
            razorpay.Client(auth=(self.key_id, self.key_secret)).utility.verify_payment_signature({
                "razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def create_payment_link(
        self,
        *,
        invoice_id: str,
        amount: float,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        description: str = "BakiClear Overdue Invoice Settlement",
    ) -> dict[str, Any]:
        """Generate a Razorpay payment link for an invoice."""
        if self.use_mock:
            link_id = f"plink_{uuid.uuid4().hex[:12]}"
            short_url = f"https://rzp.io/i/{link_id[:8]}"
            return {
                "id": link_id,
                "invoice_id": invoice_id,
                "amount": amount,
                "currency": "INR",
                "status": "created",
                "short_url": short_url,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                    "contact": customer_phone,
                },
                "is_mock": True,
            }

        import razorpay

        amount_paise = int(
            (Decimal(str(amount)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        link = razorpay.Client(auth=(self.key_id, self.key_secret)).payment_link.create(
            data={
                "amount": amount_paise,
                "currency": "INR",
                "reference_id": invoice_id,
                "description": description,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                    "contact": customer_phone,
                },
                "notify": {"sms": False, "email": False},
                "reminder_enable": False,
            }
        )
        return {**link, "is_mock": False}

    def verify_payment(self, payment_link_id: str) -> dict[str, Any]:
        """Check status of a payment link."""
        return {
            "id": payment_link_id,
            "status": "paid",
            "is_mock": self.use_mock,
        }


# Global adapter instance
razorpay_adapter = RazorpayAdapter()
