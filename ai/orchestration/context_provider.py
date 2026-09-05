"""The one interface the AI pipeline uses to reach customer/invoice/policy
data. Agents and the orchestrator depend on this Protocol only — never on
`MockContextProvider` or an API client directly. That is what makes the whole
pipeline runnable offline (PRINCIPLE 7) and Phase 5 a config change instead of
a rewrite.
"""

from typing import Protocol, runtime_checkable

from ai.schemas import CustomerProfile, Invoice, MerchantPolicy, PaymentRecord


@runtime_checkable
class ContextProvider(Protocol):
    def get_customer(self, customer_id: str) -> CustomerProfile: ...

    def get_invoice(self, invoice_id: str) -> Invoice: ...

    def list_overdue_invoices(self) -> list[Invoice]:
        """All invoices currently overdue — backs the collection queue screen."""
        ...

    def get_payment_history(self, customer_id: str) -> list[PaymentRecord]:
        ...

    def get_policy(self) -> MerchantPolicy:
        """The single active merchant policy. One merchant per demo — no
        multi-tenancy, per PRINCIPLE 6 / the hackathon scope."""
        ...
