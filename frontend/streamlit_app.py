"""BakiClear demo UI. Demonstrates the architecture, not a separate engineering
project: Queue -> Customer Intelligence -> Strategy -> Negotiation -> Outcome
-> Metrics, with the guardrail's ALLOW/MODIFY/REJECT/HUMAN_APPROVAL split
shown explicitly at every negotiation turn.

"LLM proposes. Policy decides. Backend executes. Database records."
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.agents.action_executor import get_action_executor
from ai.orchestration import get_context_provider
from ai.orchestration.pipeline import Assessment, assess_invoice, negotiate_turn, quick_risk
from ai.schemas import GuardrailVerdict, NegotiationTurn, PromiseStatus

st.set_page_config(page_title="BakiClear", page_icon="💰", layout="wide")

VERDICT_STYLE = {
    GuardrailVerdict.ALLOW: ("✅ ALLOW", "green"),
    GuardrailVerdict.MODIFY: ("✏️ MODIFY", "orange"),
    GuardrailVerdict.REJECT: ("⛔ REJECT", "red"),
    GuardrailVerdict.HUMAN_APPROVAL: ("🙋 HUMAN APPROVAL REQUIRED", "violet"),
}

RISK_COLOR = {"low": "green", "medium": "orange", "high": "red", "critical": "red"}


def _init_state() -> None:
    st.session_state.setdefault("assessments", {})  # invoice_id -> Assessment
    st.session_state.setdefault("conversations", {})  # invoice_id -> list[NegotiationTurn]
    st.session_state.setdefault("selected_invoice_id", None)


def _get_assessment(invoice_id: str) -> Assessment:
    """Cached per Streamlit session — assess_invoice() calls Gemini once for
    the strategy; we never want that re-run on every widget interaction."""
    cache = st.session_state["assessments"]
    if invoice_id not in cache:
        with st.spinner("Running customer intelligence, risk scoring, and AI strategy..."):
            cache[invoice_id] = assess_invoice(invoice_id)
    return cache[invoice_id]


def render_queue() -> None:
    st.subheader("📋 Overdue Collection Queue")
    st.caption("Every overdue invoice, ranked by AI-computed priority. Risk scoring here is "
               "pure Python — no LLM call until you open Strategy for a specific invoice.")

    provider = get_context_provider()
    invoices = provider.list_overdue_invoices()
    rows = [quick_risk(inv.invoice_id) for inv in invoices]
    rows.sort(key=lambda r: -r.risk.priority_score)

    for r in rows:
        cols = st.columns([3, 2, 2, 2, 2, 2, 2])
        cols[0].markdown(f"**{r.customer.name}**  \n`{r.customer.customer_id}` · {r.customer.tier.value}")
        cols[1].markdown(f"`{r.invoice.invoice_id}`")
        cols[2].markdown(f"₹{r.invoice.amount_due:,.0f}")
        cols[3].markdown(f"{r.invoice.days_overdue} days")
        cols[4].markdown(f":{RISK_COLOR[r.risk.risk_level.value]}[{r.risk.risk_level.value.upper()}]")
        cols[5].markdown(f"{r.risk.priority_level.value.upper()}")
        if cols[6].button("Review →", key=f"select_{r.invoice.invoice_id}"):
            st.session_state["selected_invoice_id"] = r.invoice.invoice_id
            st.rerun()
        st.caption(", ".join(r.risk.contributing_factors))
        st.divider()


def render_customer_intelligence(a: Assessment) -> None:
    st.subheader("🧠 Customer Intelligence")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Relationship**")
        st.metric("Lifetime value", f"₹{a.intelligence.lifetime_value:,.0f}")
        st.metric("Tenure", f"{a.intelligence.tenure_months} months")
        st.metric("Criticality", a.intelligence.relationship_criticality)
        st.info(a.intelligence.relationship_summary)
    with col2:
        st.markdown("**Payment Behavior**")
        st.metric("On-time payment rate", f"{a.behavior.on_time_payment_pct}%")
        st.metric("Average delay", f"{a.behavior.average_delay_days} days")
        st.metric("Disputes / Broken promises", f"{a.behavior.dispute_count} / {a.behavior.broken_promise_count}")
        st.info(a.behavior.behavioral_summary)

    st.markdown("**Risk / Priority** (deterministic, not AI-generated)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Risk score", f"{a.risk.risk_score}/100", a.risk.risk_level.value.upper())
    c2.metric("Priority score", f"{a.risk.priority_score}/100", a.risk.priority_level.value.upper())
    c3.metric("Contributing factors", str(len(a.risk.contributing_factors)))
    st.caption(" · ".join(a.risk.contributing_factors))


def render_strategy(a: Assessment) -> None:
    st.subheader("🎯 Collection Strategy")
    st.caption("Gemini's proposal — not yet authorized. Compare against the actual enforced "
               "policy on the right.")

    rule = a.policy.rule_for(a.customer.tier)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🤖 AI Suggestion")
        st.write(f"**Channel:** {a.strategy.recommended_channel.value}")
        st.write(f"**Tone:** {a.strategy.tone.value}")
        st.write(f"**Urgency:** {a.strategy.urgency}")
        st.write(f"**Suggested max extension:** {a.strategy.max_extension_days} days")
        st.write(f"**Suggested max discount:** {a.strategy.max_discount_pct}%")
        st.write(f"**AI thinks human approval needed:** {a.strategy.requires_human_approval}")
    with col2:
        st.markdown(f"#### 🔒 Enforced Policy ({a.customer.tier.value} tier)")
        st.write(f"**Actual max extension:** {rule.max_extension_days} days")
        st.write(f"**Actual max discount:** {rule.max_discount_pct}%")
        st.write(f"**Human approval if disputed:** {rule.requires_human_approval_if_disputed}")
        st.write(
            f"**Human approval if broken promises ≥:** {rule.requires_human_approval_if_broken_promises_gte}"
        )
        if a.strategy.max_extension_days > rule.max_extension_days or a.strategy.max_discount_pct > rule.max_discount_pct:
            st.warning("AI's suggestion exceeds policy — the guardrail will clamp or reject any "
                       "concession beyond these enforced limits, regardless of what the AI proposed.")

    st.markdown("**AI reasoning**")
    st.write(a.strategy.recommended_approach)
    st.caption(a.strategy.reasoning)


def render_negotiation(a: Assessment) -> None:
    st.subheader("💬 Negotiation")
    invoice_id = a.invoice.invoice_id
    conversation: list[NegotiationTurn] = st.session_state["conversations"].setdefault(invoice_id, [])

    if not conversation:
        opener = NegotiationTurn(
            speaker="ai",
            message=f"Hi {a.customer.name}, this is BakiClear regarding invoice "
            f"{invoice_id} (₹{a.invoice.amount_due:,.0f}, {a.invoice.days_overdue} days overdue). "
            "How can we help resolve this?",
            timestamp=datetime.now(),
        )
        conversation.append(opener)

    for turn in conversation:
        with st.chat_message("assistant" if turn.speaker == "ai" else "user"):
            st.write(turn.message)

    message = st.chat_input("Type the customer's message...")
    if message:
        conversation.append(NegotiationTurn(speaker="customer", message=message, timestamp=datetime.now()))
        with st.spinner("AI negotiating, then policy engine validating..."):
            outcome = negotiate_turn(a, session_id=f"SESSION-{invoice_id}", conversation=conversation, customer_message=message)
        conversation.append(
            NegotiationTurn(speaker="ai", message=outcome.result.proposed_next_message, timestamp=datetime.now())
        )
        st.session_state["last_outcome"] = outcome
        st.rerun()

    outcome = st.session_state.get("last_outcome")
    if outcome and outcome.decision.original_proposal.invoice_id == invoice_id:
        st.divider()
        st.markdown("### 🔍 Policy Panel — what just happened")
        label, color = VERDICT_STYLE[outcome.decision.verdict]
        c1, c2, c3 = st.columns(3)
        c1.metric("Customer asked for", f"{outcome.result.requested_extension_days}d ext / {outcome.result.requested_discount_pct}% off")
        rule = a.policy.rule_for(a.customer.tier)
        c2.metric("Policy allows", f"{rule.max_extension_days}d ext / {rule.max_discount_pct}% off")
        c3.markdown(f"### :{color}[{label}]")
        st.info(outcome.decision.reason)
        if outcome.promise:
            st.success(
                f"✅ Promise created: {outcome.promise.promise_id} — ₹{outcome.promise.amount:,.0f} "
                f"due {outcome.promise.due_date}"
            )


def render_outcome() -> None:
    st.subheader("✅ Outcome")
    executor = get_action_executor()

    st.markdown("**Promises to Pay**")
    promises = executor.list_promises()
    if not promises:
        st.caption("No promises recorded yet — negotiate an invoice to ALLOW/MODIFY first.")
    for p in promises:
        cols = st.columns([2, 2, 2, 2, 2])
        cols[0].write(p.promise_id)
        cols[1].write(p.invoice_id)
        cols[2].write(f"₹{p.amount:,.0f}")
        cols[3].write(f"due {p.due_date}")
        cols[4].write(f"status: **{p.status.value}**")
        if p.status == PromiseStatus.PENDING:
            b1, b2 = st.columns(2)
            if b1.button("Mark kept", key=f"kept_{p.promise_id}"):
                executor.mark_promise_status(p.promise_id, PromiseStatus.KEPT)
                st.rerun()
            if b2.button("Mark broken", key=f"broken_{p.promise_id}"):
                executor.mark_promise_status(p.promise_id, PromiseStatus.BROKEN)
                st.rerun()

    st.markdown("**Pending Human Approval**")
    approvals = executor.list_pending_approvals()
    if not approvals:
        st.caption("Nothing escalated yet.")
    for d in approvals:
        st.warning(f"{d.original_proposal.invoice_id}: {d.reason}")

    st.markdown("**Audit Log**")
    for entry in reversed(executor.list_audit_log()):
        label, color = VERDICT_STYLE[entry.decision.verdict]
        st.caption(f"{entry.timestamp:%H:%M:%S} · {entry.decision.original_proposal.invoice_id} · "
                   f":{color}[{label}] · {entry.decision.reason}")


def render_metrics() -> None:
    st.subheader("📊 Metrics")
    metrics = get_action_executor().compute_metrics()

    c1, c2, c3 = st.columns(3)
    c1.metric("Invoices processed", metrics.total_invoices_processed)
    c2.metric("Amount due", f"₹{metrics.total_amount_due:,.0f}")
    c3.metric("Amount promised", f"₹{metrics.total_amount_promised:,.0f}")

    c4, c5, c6, c7 = st.columns(4)
    c4.metric("Recovery rate", f"{metrics.recovery_rate_pct}%")
    c5.metric("Promise-keeping rate", f"{metrics.promise_keeping_rate_pct}%")
    c6.metric("Human escalations", metrics.human_escalations)
    c7.metric("Guardrail rejections", metrics.guardrail_rejections)

    st.bar_chart(
        {
            "Rejections": metrics.guardrail_rejections,
            "Modifications": metrics.guardrail_modifications,
            "Escalations": metrics.human_escalations,
        }
    )


def main() -> None:
    _init_state()
    st.title("💰 BakiClear")
    st.caption("AI-Powered Collections Strategy & Negotiation — "
               "**LLM proposes. Policy decides. Backend executes. Database records.**")

    tabs = st.tabs(["📋 Queue", "🧠 Intelligence", "🎯 Strategy", "💬 Negotiation", "✅ Outcome", "📊 Metrics"])

    with tabs[0]:
        render_queue()

    invoice_id = st.session_state["selected_invoice_id"]
    if invoice_id is None:
        for tab in tabs[1:5]:
            with tab:
                st.info("Select an invoice from the Queue tab first.")
    else:
        assessment = _get_assessment(invoice_id)
        with tabs[1]:
            render_customer_intelligence(assessment)
        with tabs[2]:
            render_strategy(assessment)
        with tabs[3]:
            render_negotiation(assessment)

    with tabs[4]:
        render_outcome()
    with tabs[5]:
        render_metrics()


main()
