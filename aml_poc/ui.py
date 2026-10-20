"""Streamlit review console. All mutations go through the Python API."""

import json
import os
import uuid

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from aml_poc.config import ROOT
from aml_poc.ui_design import (
    badge,
    detail_rows,
    entity_header,
    finding_card,
    metrics,
    note,
    page_header,
    section_heading,
    style_queue,
    text,
)

load_dotenv(ROOT / ".env")
API = os.environ.get("AML_API_URL", "http://127.0.0.1:8001")
st.set_page_config(page_title="AML Operations | Investigation Console", page_icon="◈", layout="wide")
st.html(f"<style>{(ROOT / 'aml_poc' / 'console.css').read_text()}</style>")


def render_kyc(data):
    components.iframe(f"{API}/kyc/{data['customer']['customer_id']}", height=1000, scrolling=True)


def api(path, body=None):
    try:
        response = (
            requests.get(API + path, timeout=120)
            if body is None
            else requests.post(API + path, json=body, timeout=180)
        )
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            st.error(str(detail))
            return None
        return response.json()
    except requests.RequestException:
        st.error("The Python API is unavailable. Start both services with ./run.sh.")
        return None


SCENARIOS = {
    "TM-01": "Cash structuring",
    "TM-03": "Funnel account",
    "TM-04": "Rapid movement of funds",
    "TM-07": "Pass-through activity",
    "TM-08": "Unusual activity burst",
    "TM-09": "International wire activity",
}


def scenario_label(ids):
    return " / ".join(SCENARIOS.get(item, item) for item in ids)


def alerts(scope="all"):
    return api(f"/alerts?scope={scope}") or []


header_status = api("/status") or {}
model_label = {"claude": "Claude API", "openai": "OpenAI API"}.get(
    header_status.get("mode"), "Rules-based demo"
)

with st.sidebar:
    st.html(
        '<div class="brand"><div class="brand-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/><path d="m8 12 3 3 5-6"/></svg></div><div><div class="brand-name">AML Operations</div><div class="brand-subtitle">Investigation workspace</div></div></div><div class="sidebar-label">INVESTIGATION WORKSPACE</div>'
    )
    page = st.radio(
        "Navigation",
        [
            "Alert queue",
            "Customer profiles",
            "Live stream",
            "Case workbench",
            "Audit trail",
            "Evaluation & policy",
        ],
        format_func=lambda value: {
            "Case workbench": "Investigations",
            "Live stream": "Monitoring",
            "Evaluation & policy": "Policies & validation",
        }.get(value, value),
        label_visibility="collapsed",
        key="navigation",
    )
    st.html(
        f'<div class="sidebar-footer">{badge("DEMONSTRATION ENVIRONMENT", "gold")}<p><strong>Investigator workspace</strong><br>{text(model_label)} · Synthetic data</p><p>All dispositions require investigator review and a recorded rationale.</p></div>'
    )

st.html(
    f'<div class="utility-bar"><div>Financial crime compliance <span style="color:#555e6a;padding:0 8px">/</span><strong>Transaction monitoring</strong></div><div class="utility-right">{badge(model_label, "gold")}<span class="utility-rule"></span><span>USD · Event time in UTC</span></div></div>'
)


@st.fragment(run_every="2s")
def live_stream():
    status = api("/status")
    if not status:
        return
    page_header(
        "MONITORING / OPERATIONS",
        "Transaction monitoring",
        "Monitor incoming activity, detection signals and investigation readiness.",
    )
    metrics(
        [
            (
                "STREAM EVENTS",
                f"{status['stream_processed']:,}",
                f"of {status['stream_total']:,} scheduled events",
                "gold",
            ),
            (
                "DETECTION SIGNALS",
                status["stream_alerts"],
                "Alerts raised from the current stream",
                "neutral",
            ),
            ("AWAITING REVIEW", status["awaiting_review"], "Reports pending investigator decision", "gold"),
            ("DISPOSITIONS", status["reviewed"], "Completed human reviews", "green"),
        ]
    )
    st.progress(status["stream_processed"] / max(status["stream_total"], 1))
    state_label = (
        "Running"
        if status["running"]
        else "Finished"
        if status["stream_processed"] == status["stream_total"]
        else "Paused / ready"
    )
    st.caption(
        f"{state_label} · Event clock {status['event_clock']} UTC · Agent mode: {status['mode'].upper()}"
    )
    if status["error"]:
        st.error(status["error"])
    with st.expander("Stream controls", expanded=status["stream_processed"] == 0):
        a, b, c, d = st.columns([2, 2, 1, 1])
        rate = a.select_slider("Events per second", [5, 20, 50, 100, 250], value=50)
        investigate = b.checkbox("Build reports when replay finishes", value=True)
        if c.button("Start / resume", type="primary", disabled=status["running"]):
            api("/replay/start", {"events_per_second": rate, "auto_investigate": investigate})
            st.rerun(scope="fragment")
        if d.button("Pause", disabled=not status["running"]):
            api("/replay/pause", {})
            st.rerun(scope="fragment")
    if status["mode"] == "demo":
        st.caption(
            "Demonstration mode · Assessments use deterministic templates; live model quality is not measured."
        )
    left, right = st.columns([1.7, 1])
    with left:
        section_heading("Transaction ledger", "Most recent activity")
        rows = api("/transactions?limit=16") or []
        if rows:
            ledger = pd.DataFrame(rows)[["txn_ts", "customer_id", "txn_type", "direction", "amount"]]
            ledger["amount"] = pd.to_numeric(ledger["amount"])
            ledger.columns = ["Event time", "Customer", "Type", "Direction", "Amount (USD)"]
            st.dataframe(
                ledger,
                hide_index=True,
                width="stretch",
                height=450,
                column_config={"Amount (USD)": st.column_config.NumberColumn(format="dollar")},
            )
    with right:
        section_heading("Detection activity", "Current stream")
        for alert in alerts("stream")[:5]:
            with st.container(border=True):
                st.html(
                    badge(alert["priority"] + " priority", alert["priority"])
                    + " "
                    + badge(
                        alert["signal_status"],
                        "gold" if alert["signal_status"] == "provisional" else "neutral",
                    )
                )
                st.markdown(f"**{alert['customer_name']}**")
                st.caption(
                    f"{' + '.join(alert['pattern_ids'])} · {alert['signal_status']} · {alert['priority']} priority"
                )
                st.write(
                    f"${alert['amount']:,.2f} across {len(alert['transaction_ids'])} evidence transactions"
                )


def alert_queue():
    page_header(
        "CASE MANAGEMENT / ALERTS",
        "Alert queue",
        "Select an alert to review the customer, investigate activity and record a decision.",
    )
    all_rows = alerts()
    stream_rows = [r for r in all_rows if r["source"] == "stream"]
    metrics(
        [
            ("STREAM ALERTS", len(stream_rows), "Current monitoring stream", "neutral"),
            (
                "HIGH PRIORITY",
                sum(r["priority"] == "high" for r in stream_rows),
                "Cases requiring focused review",
                "high",
            ),
            (
                "AWAITING REVIEW",
                sum(r["case_status"] == "awaiting_review" for r in stream_rows),
                "Complete or incomplete reports",
                "gold",
            ),
            (
                "PROVISIONAL SIGNALS",
                sum(r["signal_status"] == "provisional" for r in stream_rows),
                "Observation period still open",
                "neutral",
            ),
        ]
    )
    with st.container(border=True):
        a, b, c, d = st.columns([2.3, 1, 1, 1.3])
        query = a.text_input("Search customer or alert", placeholder="Customer name, ID or alert reference")
        scope = b.selectbox(
            "Source",
            ["stream", "all", "history"],
            format_func=lambda x: {
                "stream": "Current stream",
                "all": "All activity",
                "history": "Historical",
            }[x],
        )
        priority = c.selectbox("Priority", ["All", "high", "medium", "low"], format_func=lambda x: x.title())
        workflow = d.selectbox(
            "Workflow status",
            ["All", "awaiting_review", "not_started", "reviewed"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        with st.expander("More filters"):
            a, b = st.columns(2)
            pattern = a.selectbox(
                "Detection scenario", ["All", "TM-01", "TM-03", "TM-04", "TM-07", "TM-08", "TM-09"]
            )
            signal = b.selectbox(
                "Signal status",
                ["All", "confirmed", "provisional", "withdrawn"],
                format_func=lambda x: x.title(),
            )
    rows = [
        r
        for r in all_rows
        if (scope == "all" or r["source"] == scope)
        and (priority == "All" or r["priority"] == priority)
        and (workflow == "All" or r["case_status"] == workflow)
        and (pattern == "All" or pattern in r["pattern_ids"])
        and (signal == "All" or r["signal_status"] == signal)
        and (
            not query.strip()
            or query.strip().lower() in f"{r['customer_name']} {r['customer_id']} {r['alert_id']}".lower()
        )
    ]
    rows.sort(
        key=lambda row: ({"high": 0, "medium": 1, "low": 2}.get(row["priority"], 3), row["detected_at"])
    )
    section_heading("Investigation queue", f"{len(rows):02} matching alerts · Select a row to inspect")
    if not rows:
        st.html(
            '<div class="queue-empty">No alerts match the selected criteria. Adjust the filters to continue.</div>'
        )
        return
    left, right = st.columns([3.4, 1.15], gap="large")
    with left:
        table = pd.DataFrame(
            [
                {
                    "Alert reference": r["alert_id"],
                    "Customer": r["customer_name"],
                    "Scenario": scenario_label(r["pattern_ids"]),
                    "Priority": r["priority"].upper(),
                    "Workflow": "Evidence updated"
                    if r["report_stale"]
                    else r["case_status"].replace("_", " ").title(),
                    "Transaction value": r["amount"],
                    "Detected (UTC)": r["detected_at"].replace("T", " ")[:16],
                }
                for r in rows
            ]
        )
        selection = st.dataframe(
            style_queue(table),
            hide_index=True,
            width="stretch",
            height=390,
            on_select="rerun",
            selection_mode="single-row",
            key="queue_results",
            column_config={
                "Customer": st.column_config.TextColumn(width="large"),
                "Transaction value": st.column_config.NumberColumn(format="dollar"),
            },
        )
        selected_index = selection.selection.rows[0] if selection.selection.rows else 0
        chosen = rows[min(selected_index, len(rows) - 1)]
        st.caption(
            "Transaction value is the sum of cited evidence transactions, including both directions. It is not an estimate of loss."
        )
        st.download_button(
            "Export filtered queue", table.to_csv(index=False), "aml-alert-queue.csv", "text/csv"
        )
    with right:
        st.html(
            badge(chosen["priority"] + " priority", chosen["priority"])
            + " "
            + badge(
                chosen["signal_status"], "gold" if chosen["signal_status"] == "provisional" else "neutral"
            )
        )
        st.markdown(f"**{chosen['customer_name']}**")
        st.caption(chosen["alert_id"])
        detail_rows(
            [
                ("Customer reference", chosen["customer_id"]),
                ("Detection scenario", scenario_label(chosen["pattern_ids"])),
                ("Transaction value", f"${chosen['amount']:,.2f}"),
                ("Evidence transactions", len(chosen["transaction_ids"])),
                ("Workflow", chosen["case_status"].replace("_", " ").title()),
            ]
        )

        def open_selected_case():
            st.session_state["selected_alert"] = chosen["alert_id"]
            st.session_state["navigation"] = "Case workbench"

        st.button("Open investigation", type="primary", on_click=open_selected_case, width="stretch")
        st.caption("A disposition is recorded only after investigator review.")


def workbench():
    page_header(
        "CASE MANAGEMENT / INVESTIGATIONS",
        "Case investigation",
        "Review the alert, examine the evidence, then record your decision.",
    )
    rows = alerts()
    if not rows:
        st.info("No alert is available yet.")
        return
    keys = [r["alert_id"] for r in rows]
    initial = st.session_state.get("selected_alert", keys[0])
    with st.expander("Switch investigation"):
        selected = st.selectbox(
            "Case",
            keys,
            index=keys.index(initial) if initial in keys else 0,
            format_func=lambda key: next(
                f"{r['customer_name']} · {' + '.join(r['pattern_ids'])} · {key}"
                for r in rows
                if r["alert_id"] == key
            ),
        )
    st.session_state["selected_alert"] = selected
    alert = next(r for r in rows if r["alert_id"] == selected)
    case = api(f"/alerts/{selected}/case")
    kyc = api(f"/customers/{alert['customer_id']}/kyc")
    entity_header(alert, kyc["customer"] if kyc else (case.get("profile") if case else None))
    steps = [
        ("Detection", "done"),
        ("Evidence collection", "done" if case else ""),
        ("Assessment", "done" if case and case.get("recommendation") else ""),
        (
            "Investigator review",
            "active"
            if case and case["status"] == "awaiting_review"
            else "done"
            if case and case.get("decision")
            else "",
        ),
        ("Disposition", "done" if case and case.get("decision") else ""),
    ]
    st.html(
        '<div class="workflow-strip">'
        + "".join(
            f'<div class="workflow-step {state}"><span>{index:02}</span>{label}</div>'
            for index, (label, state) in enumerate(steps, 1)
        )
        + "</div>"
    )
    if not case or alert["report_stale"]:
        if alert["report_stale"]:
            st.warning("Evidence has changed. Update the investigation before recording a decision.")
        if st.button("Update investigation" if case else "Start investigation", type="primary"):
            with st.spinner("Reviewing the customer and transaction evidence…"):
                if api(f"/alerts/{selected}/investigate", {"force": False}):
                    st.rerun()
    report_tab, kyc_tab, evidence_tab, documents_tab, decision_tab, trace_tab = st.tabs(
        ["Overview", "Customer KYC", "Transactions & evidence", "Documents", "Decision", "Activity"]
    )
    with kyc_tab:
        if kyc:
            render_kyc(kyc)
    with report_tab:
        if not case:
            section_heading("Why this alert was raised")
            note("DETECTION SCENARIO", scenario_label(alert["pattern_ids"]))
            detail_rows(
                [
                    ("Evidence transactions", len(alert["transaction_ids"])),
                    ("Transaction value", f"${alert['amount']:,.2f}"),
                    ("Detected (UTC)", alert["detected_at"].replace("T", " ")),
                ]
            )
            st.info(
                "Select Start investigation to assemble the customer profile, supporting evidence and assessment."
            )
        if case:
            st.caption(f"{case['case_id']} · {case['status'].replace('_', ' ').title()}")
            main, context = st.columns([2.15, 1], gap="large")
            with main:
                if case.get("completeness", "incomplete") == "incomplete":
                    note(
                        "EVIDENCE REQUIRED",
                        "This report is incomplete. No agent recommendation has been made. Review the outstanding evidence before deciding on the next action.",
                        "gold",
                    )
                    with st.expander(f"Outstanding evidence ({len(case['missing'])})", expanded=True):
                        for missing in case["missing"]:
                            st.markdown(f"- {missing}")
                else:
                    recommendation = case.get("recommendation", "request_info").replace("_", " ").upper()
                    note(
                        "SUGGESTED NEXT ACTION",
                        recommendation
                        + " · Review the evidence, then open Decision to record your assessment.",
                        "gold",
                    )
                section_heading("Investigation findings", f"{len(case.get('findings', [])):02} findings")
                st.caption(case.get("summary", "Report in progress.").replace("$", r"\$"))
                for index, finding in enumerate(case.get("findings", []), 1):
                    finding_card(index, finding)
                note("ALTERNATIVE EXPLANATION", case.get("innocent_explanation", "Pending assessment"))
                critic = case.get("critic", {})
                if critic.get("defects"):
                    with st.expander("Quality review exceptions", expanded=True):
                        for defect in critic["defects"]:
                            st.markdown(f"- {defect}")
                exports = st.columns(2)
                exports[0].download_button(
                    "Download investigation report",
                    case.get("report", ""),
                    f"{case['case_id']}.md",
                    mime="text/markdown",
                    width="stretch",
                )
                exports[1].download_button(
                    "Export case record",
                    json.dumps(case, indent=2),
                    f"{case['case_id']}.json",
                    mime="application/json",
                    width="stretch",
                )
            with context:
                section_heading("Review readiness")
                quality = case.get("critic", {})
                detail_rows(
                    [
                        ("Report status", case.get("completeness", "in progress").title()),
                        ("Evidence records", len(case["evidence"])),
                        ("Outstanding items", len(case["missing"])),
                        (
                            "Citation / numeric checks",
                            "Passed" if quality.get("passed") else "Attention required",
                        ),
                        (
                            "Assessment mode",
                            {"claude": "Claude API", "openai": "OpenAI API"}.get(
                                case["mode"], "Deterministic demo"
                            ),
                        ),
                        ("Investigator decision", "Recorded" if case["decision"] else "Pending"),
                    ]
                )
                section_heading("Customer profile")
                profile = case.get("profile", {})
                detail_rows(
                    [
                        ("Customer type", profile.get("customer_type", "Unavailable").title()),
                        ("Occupation / industry", profile.get("occupation_or_industry", "Unavailable")),
                        ("Customer risk rating", profile.get("risk_rating", "Unavailable")),
                        (
                            "Operating region",
                            ", ".join(profile.get("expected_operating_states", [])) or "Unavailable",
                        ),
                        ("Transaction value", f"${alert['amount']:,.2f}"),
                    ]
                )
                st.caption(quality.get("scope", "Quality review pending"))
    with decision_tab:
        if not case:
            st.info("Start the investigation to prepare the evidence for review.")
        else:
            if case["decision"]:
                section_heading("Recorded disposition")
                decision = case["decision"]
                note(
                    decision["action"].replace("_", " ").upper(),
                    f"{decision['reason']} — {decision['investigator']}",
                    "green",
                )
                if case.get("sar_narrative"):
                    st.text_area(
                        "Final human-reviewed SAR narrative", case["sar_narrative"], height=220, disabled=True
                    )
            elif case["status"] == "awaiting_review":
                st.divider()
                section_heading("Investigator disposition", "A rationale is required for every decision")
                if alert["report_stale"]:
                    st.warning("Evidence has changed. Generate a fresh report before recording a decision.")
                with st.form(f"review-{case['case_id']}"):
                    a, b = st.columns(2)
                    investigator = a.text_input(
                        "Investigator name", placeholder="Enter reviewing investigator"
                    )
                    actions = ["clear", "request_info", "escalate"]
                    default = case.get("recommendation") or "request_info"
                    action = b.selectbox(
                        "Disposition",
                        actions,
                        index=actions.index(default),
                        format_func=lambda value: {
                            "clear": "Clear / close",
                            "request_info": "Request information",
                            "escalate": "Escalate for further review",
                        }[value],
                    )
                    a, b = st.columns([1, 1.4])
                    reason = a.text_area(
                        "Decision rationale",
                        placeholder="Document your assessment and the evidence supporting this decision.",
                        height=220,
                    )
                    sar = b.text_area(
                        "SAR narrative draft — editable before escalation",
                        case.get("sar_draft") or "",
                        height=220,
                    )
                    submitted = st.form_submit_button("Record investigator decision", type="primary")
                if submitted:
                    if len(investigator.strip()) < 2 or len(reason.strip()) < 5:
                        st.error("Enter the investigator name and a rationale of at least five characters.")
                    elif (
                        api(
                            f"/alerts/{selected}/review",
                            {
                                "case_id": case["case_id"],
                                "action": action,
                                "reason": reason,
                                "investigator": investigator,
                                "sar_narrative": sar or None,
                            },
                        )
                        is not None
                    ):
                        st.rerun()
    with evidence_tab:
        section_heading("Detection evidence", "Computed values and configured thresholds")
        with st.expander("Scenario calculations and thresholds"):
            st.json(alert["metrics"], expanded=1)
        if case:
            for item in case["evidence"]:
                with st.expander(f"{item['id']} · {item['kind'].upper()} · {item['title']}"):
                    st.caption(item["source"])
                    if (
                        isinstance(item["value"], list)
                        and item["value"]
                        and isinstance(item["value"][0], dict)
                        and "transaction_id" in item["value"][0]
                    ):
                        st.dataframe(pd.DataFrame(item["value"]), hide_index=True)
                    else:
                        st.json(item["value"])
    with documents_tab:
        with st.expander("Demonstration evidence controls"):
            st.caption("Synthetic fixtures for demonstrating complete and incomplete investigations.")
            if (
                st.button("Attach synthetic demo packet")
                and api(f"/alerts/{selected}/demo-packet", {}) is not None
            ):
                st.success("Synthetic supporting evidence attached. Run a fresh investigation.")

            if (
                st.button("Demonstrate a documented legitimate explanation")
                and api(f"/alerts/{selected}/demo-packet?resolution=documented_legitimate", {}) is not None
            ):
                st.success(
                    "A synthetic legitimate-explanation fixture was attached. Run a fresh investigation to demonstrate a clear recommendation."
                )
        with st.expander("Upload PDF, text or an image"):
            st.caption(
                "PDF text is extracted locally. Image extraction uses your configured model provider in live mode. Scanned PDFs require OCR or a verified transcription."
            )
            upload = st.file_uploader(
                "Supporting document",
                type=["pdf", "txt", "png", "jpg", "jpeg", "webp"],
                key=f"upload-{selected}",
            )
            upload_coverage = st.multiselect(
                "Evidence requirements this document supports",
                alert["evidence_required"],
                key=f"upload-coverage-{selected}",
            )
            if st.button("Extract and attach document"):
                if upload is None or not upload_coverage:
                    st.error("Select a file and its evidence requirements.")
                else:
                    try:
                        response = requests.post(
                            API + "/documents/extract",
                            files={"file": (upload.name, upload.getvalue(), upload.type)},
                            data={"alert_id": selected, "evidence_types": json.dumps(upload_coverage)},
                            timeout=180,
                        )
                        if response.ok:
                            st.success("Document extracted and attached. Run a fresh investigation.")
                            st.json(response.json())
                        else:
                            st.error(response.json().get("detail", "Extraction failed"))
                    except requests.RequestException:
                        st.error("Document intake is unavailable. Check that the Python API is running.")
        with st.expander("Enter document text manually"):
            st.caption(
                "Structured document intake. These records are investigator-supplied evidence; this POC does not claim to verify their authenticity."
            )
            with st.form(f"doc-{selected}"):
                title = st.text_input("Document title")
                content = st.text_area("Document text / verified extraction")
                coverage = st.multiselect("Evidence requirements supported", alert["evidence_required"])
                readable = st.checkbox("Document is readable", value=True)
                confidence = st.slider("Extraction confidence", 0.0, 1.0, 1.0)
                save = st.form_submit_button("Attach evidence")
            if save:
                if not title.strip() or not content.strip() or not coverage:
                    st.error("Provide a title, content and at least one evidence requirement.")
                elif (
                    api(
                        "/documents",
                        {
                            "document_id": "DOC-" + uuid.uuid4().hex[:12],
                            "customer_id": alert["customer_id"],
                            "title": title,
                            "content": content,
                            "evidence_types": coverage,
                            "transaction_ids": alert["transaction_ids"],
                            "readable": readable,
                            "extraction_confidence": confidence,
                        },
                    )
                    is not None
                ):
                    st.success("Evidence attached. Run a fresh investigation to review it.")
    with trace_tab:
        with st.expander("Report generation controls"):
            st.caption(
                "Existing reports are reused when the evidence and model provider are unchanged. Regenerate only when a new assessment is needed."
            )
            if st.button("Regenerate report"):
                with st.spinner("Generating a new investigation assessment…"):
                    api(f"/alerts/{selected}/investigate", {"force": True})
                    st.rerun()
        if case:
            for index, step in enumerate(case["steps"], 1):
                with st.container(border=True):
                    st.markdown(f"**{index:02} · {step['agent'].replace('_', ' ').title()}**")
                    st.caption(
                        f"{step['mode']} · {step['evidence_count']} evidence entries · {step['finished_at']}"
                    )
            st.info(
                "The investigation remains pending until an investigator records a decision in the Decision tab."
            )

        with st.expander("Demonstration failure scenarios"):
            failure = st.selectbox(
                "Failure simulation",
                [
                    "none",
                    "missing_document",
                    "missing_profile",
                    "transaction_unavailable",
                    "unreadable_document",
                    "policy_conflict",
                ],
            )
            if failure != "none" and st.button("Run failure path"):
                with st.spinner("Running the selected failure scenario…"):
                    api(f"/alerts/{selected}/investigate", {"force": True, "failure": failure})
                    st.rerun()


def customer_profiles():
    page_header(
        "CUSTOMER DUE DILIGENCE",
        "Customer profiles",
        "Identity, expected activity and KYC records in one customer view.",
    )
    customers = api("/customers") or []
    if not customers:
        st.info("No customer records available.")
        return
    names = {c["customer_id"]: c.get("business_name") or c["fake_name"] for c in customers}
    selected = st.selectbox("Customer", list(names), format_func=lambda key: f"{names[key]} · {key}")
    data = api(f"/customers/{selected}/kyc")
    if data:
        st.subheader(names[selected])
        render_kyc(data)


def audit_trail():
    page_header(
        "GOVERNANCE / ACTIVITY",
        "Audit trail",
        "Review investigation activity, evidence provenance and recorded human decisions.",
    )
    result = api("/audit")
    if not result:
        return
    events = result["events"]
    metrics(
        [
            ("AUDIT EVENTS", f"{len(events):,}", "Recorded activities in this run", "neutral"),
            (
                "AGENT EXECUTIONS",
                sum(r["event"] == "agent_completed" for r in events),
                "Completed workflow steps",
                "neutral",
            ),
            (
                "HUMAN DECISIONS",
                sum(r["event"] == "human_decision" for r in events),
                "Attributed investigator dispositions",
                "gold",
            ),
            (
                "CHAIN INTEGRITY",
                "Verified" if result["valid"] else "Failed",
                "Append-only event sequence",
                "green" if result["valid"] else "high",
            ),
        ]
    )
    a, b, c = st.columns([1, 1.2, 2])
    selected = a.selectbox("Actor", ["All", *sorted({r["actor"] for r in events})])
    activity = b.selectbox(
        "Activity",
        ["All", *sorted({r["event"] for r in events})],
        format_func=lambda x: x.replace("_", " ").title(),
    )
    reference = c.text_input("Case reference", placeholder="Filter by case ID")
    filtered = [
        r
        for r in events
        if (selected == "All" or r["actor"] == selected)
        and (activity == "All" or r["event"] == activity)
        and (not reference or reference.lower() in (r["case_id"] or "").lower())
    ]
    section_heading("Activity register", f"{len(filtered):,} records")
    display = pd.DataFrame(
        [
            {
                "Sequence": r["seq"],
                "Event time (UTC)": r["ts"][:19].replace("T", " "),
                "Actor": r["actor"].replace("_", " ").title(),
                "Activity": r["event"].replace("_", " ").title(),
                "Case reference": r["case_id"] or "Monitoring run",
                "Integrity digest": r["hash"][:16],
            }
            for r in filtered[::-1]
        ]
    )
    st.dataframe(display, hide_index=True, width="stretch", height=440)
    st.download_button(
        "Export audit register", json.dumps(filtered, indent=2), "aml-audit.json", "application/json"
    )
    st.caption(
        "The local hash chain detects record changes. Production retention and administrative access controls are outside this demonstration."
    )


def evaluation():
    page_header(
        "GOVERNANCE / VALIDATION",
        "Evaluation & policy",
        "Inspect detector validation, scenario definitions and the policy version used for each alert.",
    )
    metrics = api("/metrics") or {}
    if metrics:
        a, b, c = st.columns(3)
        a.metric(
            "Historical group coverage",
            f"{metrics['history']['detected_groups']} / {metrics['history']['scenario_pattern_groups']}",
        )
        b.metric(
            "History + stream group coverage",
            f"{metrics['combined']['detected_groups']} / {metrics['combined']['scenario_pattern_groups']}",
        )
        c.metric("Alerts without planted overlap", metrics["combined"]["alerts_without_planted_overlap"])
        st.caption(metrics["combined"]["method"])
        st.info(metrics["combined"]["agent_quality"])
        st.dataframe(pd.DataFrame(metrics["combined"]["matches"]), hide_index=True, width="stretch")
        st.download_button(
            "Download evaluation", json.dumps(metrics, indent=2), "evaluation.json", "application/json"
        )
    else:
        st.info("Run ./run.sh prepare to compute detector evaluation.")
    policies = api("/policies")
    if policies:
        section_heading("Detection scenario library", "Enabled policy definitions")
        st.caption("All demo thresholds are synthetic configuration. Alerts retain the exact policy hash.")
        st.code(policies["hash"])
        for pattern in policies["patterns"]:
            with st.expander(f"{pattern['pattern_id']} · {pattern['pattern_name']}"):
                st.write(pattern["detection_logic"])
                st.json(pattern["demo_thresholds"])
                for source in pattern["source_refs"]:
                    st.link_button(source["source_id"], source["url"])


if page == "Customer profiles":
    customer_profiles()
elif page == "Case workbench":
    workbench()
elif page == "Live stream":
    live_stream()
elif page == "Alert queue":
    alert_queue()
elif page == "Audit trail":
    audit_trail()
else:
    evaluation()
