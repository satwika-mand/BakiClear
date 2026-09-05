"""Shared enums used across schemas. Kept in one place so agents, guardrails,
and the frontend all reference the same vocabulary."""

from enum import StrEnum


class CustomerSegment(StrEnum):
    ENTERPRISE = "enterprise"
    MID_MARKET = "mid_market"
    SMALL_BUSINESS = "small_business"
    INDIVIDUAL = "individual"


class CustomerTier(StrEnum):
    """Merchant-defined relationship tier. Drives which MerchantPolicy limits apply."""

    GOLD = "gold"
    STANDARD = "standard"
    WATCH_LIST = "watch_list"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PriorityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CollectionChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    VOICE_CALL = "voice_call"
    IN_APP = "in_app"


class CollectionTone(StrEnum):
    GENTLE_REMINDER = "gentle_reminder"
    FIRM = "firm"
    EMPATHETIC = "empathetic"
    FORMAL_NOTICE = "formal_notice"


class NegotiationIntent(StrEnum):
    WILLING_TO_PAY = "willing_to_pay"
    REQUESTS_EXTENSION = "requests_extension"
    REQUESTS_DISCOUNT = "requests_discount"
    DISPUTES_AMOUNT = "disputes_amount"
    REFUSES = "refuses"
    UNCLEAR = "unclear"


class ActionType(StrEnum):
    CREATE_PAYMENT_LINK = "create_payment_link"
    RECORD_PROMISE = "record_promise"
    SCHEDULE_FOLLOW_UP = "schedule_follow_up"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    NO_ACTION = "no_action"


class GuardrailVerdict(StrEnum):
    ALLOW = "allow"
    MODIFY = "modify"
    REJECT = "reject"
    HUMAN_APPROVAL = "human_approval"


class PromiseStatus(StrEnum):
    PENDING = "pending"
    KEPT = "kept"
    BROKEN = "broken"
    PARTIALLY_KEPT = "partially_kept"
