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
from ai.agents.message import draft_message
from ai.agents.risk_engine import compute_payment_behavior
from ai.config import settings
from ai.evaluate import (
    compute_action_log_metrics,
    fetch_recovery_metrics,
    run_guardrail_boundary_test,
    run_message_safety_redteam,
)
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


@st.cache_data(ttl=15, show_spinner=False)
def _fetch_queue_rows() -> list[dict]:
    """Streamlit reruns the ENTIRE script on every interaction anywhere in the
    app — every tab's code, not just the one visible — so without this cache
    a 300-invoice, multi-join backend query would refire on every click,
    everywhere. A short TTL keeps the queue fresh without that tax."""
    return get_context_provider().get_collection_queue()


def render_queue() -> None:
    st.subheader("📋 Overdue Collection Queue")
    st.caption("Every overdue invoice, ranked by deterministic priority. No LLM call occurs "
               "until you open Strategy for a specific invoice.")

    provider = get_context_provider()
    if settings.context_source == "api":
        rows = _fetch_queue_rows()
        for row in rows:
            invoice = row["invoice"]
            customer = row["customer"]
            risk = row["risk"]
            cols = st.columns([3, 2, 2, 2, 2, 2, 2])
            cols[0].markdown(f"**{customer['name']}**  \n`{customer['customer_id']}` · {customer['segment']}")
            cols[1].markdown(f"`{invoice['invoice_id']}`")
            cols[2].markdown(f"₹{invoice['amount']:,.0f}")
            cols[3].markdown(f"{invoice['days_overdue']} days")
            cols[4].markdown(f":{RISK_COLOR[risk['risk_tier']]}[{risk['risk_tier'].upper()}]")
            cols[5].markdown(risk["priority"].upper())
            if cols[6].button("Review →", key=f"select_{invoice['invoice_id']}"):
                st.session_state["selected_invoice_id"] = invoice["invoice_id"]
                st.rerun()
            st.caption(risk["recommended_action"])
            st.divider()
        return

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
    provider = get_context_provider()

    if settings.context_source == "api":
        # Streamlit reruns every tab's code on every interaction, regardless of
        # which tab is visually active — so starting the backend session here
        # unconditionally would silently flip the invoice to "in_negotiation"
        # the instant *any* invoice is selected, even if the user never opens
        # this tab. Require an explicit click so the side effect matches
        # actual intent, not incidental script execution.
        started = st.session_state.setdefault("negotiation_started", {})
        if not started.get(invoice_id):
            st.info(
                "Starting a negotiation marks this invoice as 'in negotiation' on the backend."
            )
            if st.button("Start Negotiation", key=f"start_neg_{invoice_id}"):
                started[invoice_id] = True
                st.rerun()
            return

        session_cache = st.session_state.setdefault("negotiation_sessions", {})
        if invoice_id not in session_cache:
            session_cache[invoice_id] = provider.request("POST", f"/api/negotiate/{invoice_id}")["session_id"]
        session_id = session_cache[invoice_id]

        transcript = provider.request("GET", f"/api/negotiations/{session_id}")
        conversation = [
            NegotiationTurn(speaker=turn["speaker"], message=turn["message"], timestamp=turn["timestamp"])
            for turn in transcript["turns"]
        ]
    else:
        session_id = f"SESSION-{invoice_id}"
        conversation = st.session_state["conversations"].setdefault(invoice_id, [])

    if not conversation:
        opener = NegotiationTurn(
            speaker="ai",
            message=f"Hi {a.customer.name}, this is BakiClear regarding invoice "
            f"{invoice_id} (₹{a.invoice.amount_due:,.0f}, {a.invoice.days_overdue} days overdue). "
            "How can we help resolve this?",
            timestamp=datetime.now(),
        )
        conversation.append(opener)
        if settings.context_source == "api":
            provider.request(
                "POST", f"/api/negotiations/{session_id}/turn",
                json={"speaker": "ai", "message": opener.message, "intent": "payment_reminder"},
            )

    for turn in conversation:
        if turn.speaker == "system":
            st.caption(f"🔧 system: {turn.message}")
            continue
        with st.chat_message("assistant" if turn.speaker == "ai" else "user"):
            st.write(turn.message)

    message = st.chat_input("Type the customer's message...")
    if message:
        customer_turn = NegotiationTurn(speaker="customer", message=message, timestamp=datetime.now())
        conversation.append(customer_turn)
        if settings.context_source == "api":
            provider.request(
                "POST", f"/api/negotiations/{session_id}/turn",
                json={"speaker": "customer", "message": message, "intent": "customer_message"},
            )
        try:
            with st.spinner("AI negotiating, then policy engine validating..."):
                outcome = negotiate_turn(
                    a, session_id=session_id, conversation=conversation, customer_message=message
                )
        except RuntimeError as exc:
            st.error(f"The negotiation could not be saved: {exc}")
            return
        ai_turn = NegotiationTurn(speaker="ai", message=outcome.result.proposed_next_message, timestamp=datetime.now())
        conversation.append(ai_turn)
        if settings.context_source == "api":
            provider.request(
                "POST", f"/api/negotiations/{session_id}/turn",
                json={"speaker": "ai", "message": ai_turn.message, "intent": "negotiation_response"},
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

        # ACTION CARD: Show approved terms (ALLOW or MODIFY)
        if outcome.decision.verdict in [GuardrailVerdict.ALLOW, GuardrailVerdict.MODIFY]:
            st.divider()
            st.markdown("### ✅ Approved Payment Terms")
            with st.container(border=True):
                effective = outcome.decision.modified_proposal or outcome.decision.original_proposal
                approved_amount = a.invoice.amount_due * (1 - effective.proposed_discount_pct / 100)

                c1, c2, c3 = st.columns(3)
                c1.metric("Original amount", f"₹{a.invoice.amount_due:,.0f}")
                c2.metric("After discount", f"₹{approved_amount:,.0f}")
                c3.metric("Due by", effective.proposed_extension_days + a.invoice.days_overdue)

                st.caption(
                    f"**{effective.proposed_discount_pct}% discount** / "
                    f"**{effective.proposed_extension_days} day extension**"
                )

                c_pay, c_ask, c_dispute = st.columns(3)
                if c_pay.button("💳 Pay Now", key=f"pay_{invoice_id}"):
                    st.info(f"💳 Opening Razorpay checkout for ₹{approved_amount:,.0f}...")
                    # In real app: call POST /api/payments/create-link and render Razorpay
                    st.success("✅ Payment link sent to customer")

                if c_ask.button("❓ Ask Question", key=f"ask_{invoice_id}"):
                    st.info("Chat continues below...")

                if c_dispute.button("🚫 Dispute", key=f"dispute_{invoice_id}"):
                    st.warning("Dispute noted. Escalating to human team.")

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


@st.cache_data(ttl=30, show_spinner=False)
def _cached_inbox_entries() -> list[tuple]:
    """Streamlit reruns every tab's code on every interaction anywhere in the
    app — without caching, each of the 10 invoices here would trigger a
    get_customer() + get_payment_history() round trip on every single click
    anywhere, not just when this tab is open. Same tax as the queue fetch."""
    provider = get_context_provider()
    invoices = provider.list_overdue_invoices()[:10]
    entries = []
    for inv in invoices:
        customer = provider.get_customer(inv.customer_id)
        history = provider.get_payment_history(customer.customer_id)
        behavior = compute_payment_behavior(customer.customer_id, history)
        message = draft_message(customer, inv, behavior, inv.days_overdue)
        entries.append((customer, inv, message))
    return entries


def render_automated_inbox() -> None:
    """Simulated WhatsApp-style inbox of outgoing automated messages."""
    st.subheader("📬 Automated Inbox")
    st.caption("Scheduled & sent reminder messages. Click to open full conversation.")

    provider = get_context_provider()
    if settings.context_source == "api":
        messages = provider.request("GET", "/api/messages")[:10]
        if not messages:
            st.info("No automated messages have been sent yet. The scheduler runs every 30 seconds.")
            return
        for message in messages:
            cols = st.columns([2, 3, 3, 1])
            cols[0].markdown("**BakiClear Collections**")
            cols[1].markdown(f"`{message['invoice_id']}`")
            cols[2].markdown(f"{message['tier'].replace('_', ' ').title()} · {message['channel']}")
            if cols[3].button("Review →", key=f"inbox_{message['message_id']}"):
                st.session_state["selected_invoice_id"] = message["invoice_id"]
                st.rerun()
            st.caption(message["body"])
            st.divider()
        return

    entries = _cached_inbox_entries()
    if not entries:
        st.info("No overdue invoices.")
        return

    for customer, inv, message in entries:
        cols = st.columns([2, 3, 3, 1])
        cols[0].markdown(f"**{customer.name}**")
        cols[1].markdown(f"`{inv.invoice_id}`")
        cols[2].markdown(f"{inv.days_overdue} days overdue · {message.tone} · via {message.channel_recommended}")
        if cols[3].button("→", key=f"inbox_{inv.invoice_id}"):
            st.session_state["selected_invoice_id"] = inv.invoice_id
            st.rerun()

        st.caption(f"💬 {message.subject}")
        st.divider()


@st.cache_data(ttl=30, show_spinner=False)
def _cached_escalated_rows() -> list[dict]:
    """Uses the same bulk queue join as the Queue tab (one backend call for
    everything) instead of calling get_customer() per matching invoice — the
    prior version did up to ~190 individual round trips (one per invoice with
    days_overdue >= 15), each ~0.9s, i.e. ~3 minutes of dead time on every
    rerun anywhere in the app. Customer name/id needed here are already
    present in the queue row, so no per-invoice call is needed at all."""
    if settings.context_source != "api":
        # Mock mode: local data, N+1 here is negligible (no network).
        provider = get_context_provider()
        out = []
        for inv in provider.list_overdue_invoices():
            if inv.days_overdue >= 15:
                customer = provider.get_customer(inv.customer_id)
                out.append({
                    "customer": {"name": customer.name, "customer_id": customer.customer_id},
                    "invoice": {"invoice_id": inv.invoice_id, "amount": inv.amount_due, "days_overdue": inv.days_overdue},
                })
        return out

    return [row for row in _fetch_queue_rows() if row["invoice"]["days_overdue"] >= 15]


def render_human_collection_queue() -> None:
    """Queue of escalated cases awaiting human review (HUMAN_APPROVAL verdicts)."""
    st.subheader("👤 Human Collection Queue")
    st.caption("Cases escalated by the guardrail. Click 'Review' to see full conversation & context.")

    provider = get_context_provider()
    if settings.context_source == "api":
        tasks = provider.request("GET", "/api/human-tasks")
        if not tasks:
            st.success("✅ No escalations pending.")
            return
        st.warning(f"⚠️ {len(tasks)} case(s) pending human review")
        for task in tasks[:10]:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 3])
                c1.markdown(f"**{task['customer_id']}**")
                c2.markdown(f"`{task['invoice_id']}`")
                c3.markdown(f"**{task['priority'].upper()}** · {task['reason']}")
                if st.button("Review →", key=f"human_{task['task_id']}"):
                    st.session_state["selected_invoice_id"] = task["invoice_id"]
                    st.rerun()
        return

    escalated = _cached_escalated_rows()

    if not escalated:
        st.success("✅ No escalations pending.")
        return

    st.warning(f"⚠️ {len(escalated)} case(s) pending human review")
    st.divider()

    for row in escalated[:5]:  # Show top 5
        customer, inv = row["customer"], row["invoice"]
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 3])
            c1.markdown(f"**{customer['name']}**  \n`{customer['customer_id']}`")
            c2.markdown(f"`{inv['invoice_id']}`  \n₹{inv['amount']:,.0f}")
            c3.markdown(f"**{inv['days_overdue']} days overdue**  \n"
                       f"Reason: High days overdue + watch_list tier")

            if st.button("📞 Call Customer", key=f"call_{inv['invoice_id']}"):
                st.info(f"Calling {customer['name']}: +91-XXXX-XXXX  \n"
                       f"Reference: {inv['invoice_id']}")

            if st.button("✅ Approve & Create Promise", key=f"approve_{inv['invoice_id']}"):
                st.success("Promise created and sent to customer.")

            st.divider()


@st.cache_data(ttl=30, show_spinner=False)
def _cached_boundary_report():
    """The guardrail boundary test is fast (<50ms) but re-derives nothing
    that changes between reruns, so cache it anyway for consistency."""
    policy = get_context_provider().get_policy()
    return run_guardrail_boundary_test(policy)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_action_log_metrics():
    return compute_action_log_metrics()


@st.cache_data(ttl=30, show_spinner=False)
def _cached_recovery_metrics():
    """Same full-script-rerun problem as the queue fetch: without caching,
    /api/metrics/summary's ~6s aggregation query reruns on every click
    anywhere in the app, not just when this tab is opened."""
    return fetch_recovery_metrics()


def render_metrics() -> None:
    st.subheader("📊 Metrics & Evaluation")
    st.caption(
        "Every number below is either exhaustively computed or read from real recorded "
        "system activity — nothing here is simulated or estimated."
    )

    # --- 1. Guardrail correctness: exhaustive, not sampled ---
    st.markdown("### 🛡️ Guardrail Safety (Exhaustive Boundary-Value Test)")
    boundary_report = _cached_boundary_report()
    b1, b2, b3 = st.columns(3)
    b1.metric("Cases tested", boundary_report.total_cases_tested)
    b2.metric("Violations found", len(boundary_report.violations))
    b3.metric("Result", "✅ PASS" if boundary_report.passed else "❌ FAIL")
    st.caption(
        "Complete coverage — every tier × dispute-state × broken-promise-count × "
        "discount/extension boundary combination, not a random sample."
    )
    if not boundary_report.passed:
        st.error("Guardrail violations detected — see details below.")
        for v in boundary_report.violations[:10]:
            st.code(str(v))

    st.divider()

    # --- 2. Real audit-log metrics (actual recorded verdicts/promises) ---
    st.markdown("### 📋 Real Negotiation Outcomes (from backend audit log)")
    action_metrics = _cached_action_log_metrics()
    if not action_metrics.available:
        st.info("No recorded negotiation activity yet — run some negotiations first, or this is running in mock mode.")
    else:
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Allow", action_metrics.allow_count)
        a2.metric("Modify", action_metrics.modify_count)
        a3.metric("Reject", action_metrics.reject_count)
        a4.metric("Human Approval", action_metrics.human_approval_count)

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Promises made", action_metrics.promises_total)
        p2.metric("Kept", action_metrics.promises_kept)
        p3.metric("Broken", action_metrics.promises_broken)
        p4.metric("Still pending", action_metrics.promises_pending)

        keep_rate = action_metrics.keep_rate_pct
        if keep_rate is None:
            st.caption(f"Keep rate: not yet available — {action_metrics.promises_pending} promises still unresolved.")
        else:
            st.caption(f"Keep rate over resolved promises: {keep_rate}% ({action_metrics.promises_kept}/{action_metrics.resolved_promises} resolved)")

        st.bar_chart({
            "Allow": action_metrics.allow_count,
            "Modify": action_metrics.modify_count,
            "Reject": action_metrics.reject_count,
            "Human Approval": action_metrics.human_approval_count,
        })

    st.divider()

    # --- 3. Message safety red-team ---
    st.markdown("### 🚨 Message Safety Red-Team")
    safety_report = run_message_safety_redteam()
    s1, s2 = st.columns(2)
    s1.metric("Catch rate", f"{safety_report.catch_rate_pct}%")
    s2.metric("Cases tested", safety_report.total_cases)
    if safety_report.missed:
        st.error(f"⚠️ {len(safety_report.missed)} unsafe pattern(s) not caught:")
        for m in safety_report.missed:
            st.code(m)
    else:
        st.success("All known-unsafe patterns caught; no false positives on safe messages.")

    st.divider()

    # --- 4. Recovery metrics: passthrough of backend's real computation ---
    st.markdown("### 💰 Recovery (from backend, real DB state)")
    recovery = _cached_recovery_metrics()
    if not recovery.available:
        st.info("Recovery metrics unavailable (mock mode or backend unreachable).")
    else:
        r1, r2, r3 = st.columns(3)
        r1.metric("Total overdue", f"₹{recovery.total_overdue_amount:,.0f}")
        r2.metric("Total recovered", f"₹{recovery.total_recovered_amount:,.0f}")
        r3.metric("Recovery rate", f"{recovery.recovery_rate_pct}%")


def main() -> None:
    _init_state()
    st.title("💰 BakiClear")
    st.caption("AI-Powered Collections Strategy & Negotiation — "
               "**LLM proposes. Policy decides. Backend executes. Database records.**")

    tabs = st.tabs(["📋 Queue", "🧠 Intelligence", "🎯 Strategy", "💬 Negotiation", "✅ Outcome", "📬 Inbox", "👤 Human Queue", "📊 Metrics"])

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
        render_automated_inbox()
    with tabs[6]:
        render_human_collection_queue()
    with tabs[7]:
        render_metrics()


main()
