"""ContextProvider backed by data/*.json. Lets the entire AI pipeline run with
no backend and no database — the default until Phase 5 wires up the real API."""

import json
from pathlib import Path

from ai.schemas import CustomerProfile, Invoice, MerchantPolicy, PaymentRecord

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class CustomerNotFoundError(KeyError):
    pass


class InvoiceNotFoundError(KeyError):
    pass


class MockContextProvider:
    """Loads all fixtures once at construction. Fine for hackathon scale
    (a handful of customers/invoices) — no caching layer needed."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self._customers = {
            c["customer_id"]: CustomerProfile.model_validate(c)
            for c in json.loads((data_dir / "customers.json").read_text())
        }
        self._invoices = {
            i["invoice_id"]: Invoice.model_validate(i)
            for i in json.loads((data_dir / "invoices.json").read_text())
        }
        raw_history: dict[str, list[dict]] = json.loads(
            (data_dir / "payment_history.json").read_text()
        )
        self._payment_history = {
            customer_id: [PaymentRecord.model_validate(r) for r in records]
            for customer_id, records in raw_history.items()
        }
        self._policy = MerchantPolicy.model_validate(
            json.loads((data_dir / "policy.json").read_text())
        )

    def get_customer(self, customer_id: str) -> CustomerProfile:
        try:
            return self._customers[customer_id]
        except KeyError as exc:
            raise CustomerNotFoundError(customer_id) from exc

    def get_invoice(self, invoice_id: str) -> Invoice:
        try:
            return self._invoices[invoice_id]
        except KeyError as exc:
            raise InvoiceNotFoundError(invoice_id) from exc

    def list_overdue_invoices(self) -> list[Invoice]:
        return sorted(self._invoices.values(), key=lambda inv: -inv.days_overdue)

    def get_payment_history(self, customer_id: str) -> list[PaymentRecord]:
        return self._payment_history.get(customer_id, [])

    def get_policy(self) -> MerchantPolicy:
        return self._policy
