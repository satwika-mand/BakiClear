"""Automated message generation for collections follow-up.

Three tiers based on days overdue:
  Tier 1 (1–3 days): Friendly reminder, payment option
  Tier 2 (4–14 days): Consultative, payment plan offer
  Tier 3 (15+ days): Firm, then escalation to human

Safety: Deterministic block on threats, harassment, fabricated penalties.
"""

import re

from pydantic import BaseModel

from ai.schemas import CustomerProfile, CustomerTier, Invoice, PaymentBehavior


class MessageDraft(BaseModel):
    """Structured message ready to send."""

    subject: str
    body: str
    tone: str  # "friendly" | "consultative" | "firm"
    channel_recommended: str  # "email" | "sms" | "voice"
    is_escalation: bool = False  # True if this routes to human, not sent directly


def _safety_check(text: str) -> bool:
    """Deterministic block on prohibited language.

    Returns False if text contains threats, harassment, or fabricated penalties.
    """
    blocklist = [
        r"legal action",
        r"sue you",
        r"court",
        r"blacklist",
        r"credit bureau",
        r"third party",
        r"debt collector",
        r"garnish",  # catches "wage garnishment", "garnish your wages", any word order
        r"if you don't pay",
        r"or else",
    ]
    text_lower = text.lower()
    for pattern in blocklist:
        if re.search(pattern, text_lower):
            return False
    return True


def draft_message(
    customer: CustomerProfile,
    invoice: Invoice,
    behavior: PaymentBehavior,
    days_overdue: int,
) -> MessageDraft:
    """Generate a tier-appropriate, safety-checked message.

    Tier 1 (1–3 days): friendly reminder
    Tier 2 (4–14 days): consultative payment plan
    Tier 3 (15+): firm + escalate to human
    """

    # Determine channel by tier
    if customer.tier == CustomerTier.GOLD:
        channel = "email"  # Gold prefers async
    elif customer.tier == CustomerTier.STANDARD:
        channel = "sms" if days_overdue < 7 else "email"
    else:  # WATCH_LIST
        channel = "sms" if days_overdue < 10 else "voice"

    # Tier 1: 1–3 days
    if days_overdue <= 3:
        subject = f"Payment Reminder: {customer.name}"
        body = f"""Hi {customer.name},

This is a friendly reminder that invoice {invoice.invoice_id} for ₹{invoice.amount_due:,.0f} is due.

We appreciate your prompt payments and would love to keep things smooth.

You can complete payment here: [Payment Link]

Thanks,
BakiClear Collections"""
        tone = "friendly"
        is_escalation = False

    # Tier 2: 4–14 days
    elif days_overdue <= 14:
        on_time_pct = behavior.on_time_payment_pct
        if on_time_pct >= 80:
            opener = "We know you're usually reliable — we just want to check in."
        else:
            opener = "We've noticed a pattern of delayed payments and want to help find a solution."

        subject = f"Let's Resolve: {customer.name} – Invoice {invoice.invoice_id}"
        body = f"""Hi {customer.name},

{opener}

Invoice {invoice.invoice_id} (₹{invoice.amount_due:,.0f}) is now {days_overdue} days overdue.

We can work with you on:
• A small discount for prompt settlement
• A payment extension if cash flow is tight
• A structured payment plan

Reply to this message or call us to discuss options.

Thanks,
BakiClear Collections"""
        tone = "consultative"
        is_escalation = False

    # Tier 3: 15+ days
    else:
        subject = f"URGENT: Invoice {invoice.invoice_id} – Action Required"
        body = f"""Hi {customer.name},

Invoice {invoice.invoice_id} (₹{invoice.amount_due:,.0f}) is now {days_overdue} days overdue and requires immediate attention.

Your account has been escalated to our collections team for direct follow-up.

Please settle immediately or contact us urgently to arrange payment.

Reference: {invoice.invoice_id}

BakiClear Collections"""
        tone = "firm"
        is_escalation = True

    # Safety check
    if not _safety_check(body):
        # Fallback to safe generic
        body = f"Invoice {invoice.invoice_id} (₹{invoice.amount_due:,.0f}) requires your attention. Please contact us to arrange payment."
        tone = "neutral"

    return MessageDraft(
        subject=subject,
        body=body,
        tone=tone,
        channel_recommended=channel,
        is_escalation=is_escalation,
    )
