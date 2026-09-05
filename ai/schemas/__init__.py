"""Public contracts for the whole AI pipeline. Import from here, not from the
individual submodules, e.g. `from ai.schemas import CollectionStrategy`."""

from ai.schemas.customer import CustomerIntelligence, CustomerProfile
from ai.schemas.enums import (
    ActionType,
    CollectionChannel,
    CollectionTone,
    CustomerSegment,
    CustomerTier,
    GuardrailVerdict,
    NegotiationIntent,
    PriorityLevel,
    PromiseStatus,
    RiskLevel,
)
from ai.schemas.guardrail import ActionProposal, CustomerFacts, GuardrailDecision
from ai.schemas.invoice import Invoice
from ai.schemas.negotiation import NegotiationResult, NegotiationTurn
from ai.schemas.payment_history import PaymentBehavior, PaymentRecord
from ai.schemas.policy import MerchantPolicy, TierPolicyRule
from ai.schemas.promise import PromiseToPay
from ai.schemas.risk import RiskAssessment
from ai.schemas.strategy import CollectionStrategy

__all__ = [
    "ActionProposal",
    "ActionType",
    "CollectionChannel",
    "CollectionStrategy",
    "CollectionTone",
    "CustomerFacts",
    "CustomerIntelligence",
    "CustomerProfile",
    "CustomerSegment",
    "CustomerTier",
    "GuardrailDecision",
    "GuardrailVerdict",
    "Invoice",
    "MerchantPolicy",
    "NegotiationIntent",
    "NegotiationResult",
    "NegotiationTurn",
    "PaymentBehavior",
    "PaymentRecord",
    "PriorityLevel",
    "PromiseStatus",
    "PromiseToPay",
    "RiskAssessment",
    "RiskLevel",
    "TierPolicyRule",
]
