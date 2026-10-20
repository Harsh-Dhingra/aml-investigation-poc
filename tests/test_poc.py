import copy
import csv
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aml_poc.api import create_app
from aml_poc.config import DATA
from aml_poc.data import Dataset
from aml_poc.evaluate import evaluate
from aml_poc.models import ReviewDecision, Transaction
from aml_poc.service import Service
from aml_poc.workflow import citation_defects


@pytest.fixture(scope="module")
def dataset():
    return Dataset(DATA)


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    svc = Service(DATA, tmp_path_factory.mktemp("runtime"), "demo")
    yield svc
    svc.close()


def tx(dataset, customer="C001", **values):
    original = next(r for r in dataset.history if r.customer_id == customer)
    row = original.model_dump(mode="json")
    row.update(values)
    return Transaction.model_validate(row)


def test_historical_and_future_coverage(dataset):
    history = evaluate(dataset)
    combined = evaluate(dataset, True)
    assert history["detected_groups"] == history["scenario_pattern_groups"] == 31
    assert combined["detected_groups"] == combined["scenario_pattern_groups"] == 37
    assert combined["agent_quality"].startswith("Not measured")


def test_stream_contract(dataset):
    rows = dataset.read_transactions(DATA / "stream_transactions.csv")
    with (DATA / "stream_labels.csv").open() as handle:
        labels = list(csv.DictReader(handle))
    assert len(rows) == len(labels) == 1000
    assert sum(r["label"] == "SUSPICIOUS" for r in labels) == 46
    assert len({r["scenario_id"] for r in labels if r["scenario_id"]}) == 5
    assert min(r.txn_ts for r in rows) > max(r.txn_ts for r in dataset.history)
    normal_invoices = [r.invoice_id for r in rows if r.transaction_id.startswith("STR-N") and r.invoice_id]
    assert len(normal_invoices) == len(set(normal_invoices))


def test_labels_are_not_runtime_inputs(dataset, tmp_path):
    import shutil

    for filename in [
        "customers.json",
        "accounts.json",
        "counterparties.json",
        "policy_patterns.json",
        "transactions.csv",
        "stream_transactions.csv",
    ]:
        shutil.copyfile(DATA / filename, tmp_path / filename)
    loaded = Dataset(tmp_path)
    assert len(loaded.history) == 4815
    from aml_poc.rules import DetectorEngine

    engine = DetectorEngine(loaded)
    assert engine.detect(
        "C001", [r for r in loaded.history if r.customer_id == "C001"], loaded.history[-1].txn_ts
    )


def test_stream_pause_restart_and_event_idempotency(service, dataset):
    row = service.stream[0]
    assert service.ingest(row)["inserted"]
    assert not service.ingest(row)["inserted"]
    changed = row.model_copy(update={"amount": row.amount + 1})
    with pytest.raises(ValueError, match="different contents"):
        service.ingest(changed)
    late = row.model_copy(update={"transaction_id": "LATE", "txn_ts": row.txn_ts - timedelta(days=2)})
    with pytest.raises(ValueError, match="Late event"):
        service.ingest(late)
    assert service.status()["stream_processed"] == 1


def test_unknown_customer_and_wrong_account_rejected(service, dataset):
    row = dataset.history[-1].model_dump(mode="json")
    row["customer_id"] = "UNKNOWN"
    with pytest.raises(ValueError, match="Customer profile missing"):
        service.ingest(row)
    row["customer_id"] = "C001"
    row["account_id"] = "ACC-C005-01"
    with pytest.raises(ValueError, match="Account does not belong"):
        service.ingest(row)


def test_no_lookahead_before_threshold(dataset):
    from aml_poc.rules import DetectorEngine

    engine = DetectorEngine(dataset)
    start = dataset.start + timedelta(days=3)
    rows = [
        tx(
            dataset,
            transaction_id=f"TEST-{i}",
            txn_type="cash_deposit",
            cash_flag=True,
            direction="INCOMING",
            amount="9000.00",
            txn_ts=(start + timedelta(days=i)).isoformat(),
        )
        for i in range(3)
    ]
    assert not engine.detect("C001", rows, rows[1].txn_ts)
    found = engine.detect("C001", rows, rows[2].txn_ts)
    assert len(found) == 1 and found[0]["detected_at"] == rows[2].txn_ts.isoformat()


def test_funnel_allocations_never_reuse_dollars(dataset):
    from aml_poc.data import by_customer
    from aml_poc.rules import DetectorEngine

    rows = dataset.history + dataset.read_transactions(DATA / "stream_transactions.csv")
    groups = by_customer(rows)
    alerts = DetectorEngine(dataset).detect("C002", groups["C002"], max(r.txn_ts for r in rows))
    amounts = {r.transaction_id: float(r.amount) for r in rows}
    for alert in alerts:
        if alert["family"] != "TM-03":
            continue
        assert 0 <= alert["metrics"]["outflow_ratio"] <= 1
        for field in ["deposit_id", "outflow_id"]:
            for key in {r[field] for r in alert["metrics"]["allocations"]}:
                assert (
                    sum(r["amount"] for r in alert["metrics"]["allocations"] if r[field] == key)
                    <= amounts[key] + 0.01
                )


def test_wire_burst_provisional_and_timer_confirmation(dataset):
    from aml_poc.rules import DetectorEngine

    engine = DetectorEngine(dataset)
    rows = dataset.history + dataset.read_transactions(DATA / "stream_transactions.csv")
    rows = [r for r in rows if r.customer_id == "C005"]
    end = max(r.txn_ts for r in rows)
    provisional = next(a for a in engine.detect("C005", rows, end) if a["window_start"].startswith("2026-10"))
    assert provisional["signal_status"] == "provisional"
    due = __import__("datetime").datetime.fromisoformat(provisional["metrics"]["confirmation_due"])
    confirmed = next(a for a in engine.detect("C005", rows, due) if a["alert_id"] == provisional["alert_id"])
    assert confirmed["signal_status"] == "confirmed"


def test_report_finishes_before_human_gate(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True)
    assert case["status"] == "awaiting_review"
    assert case["report"] and case["decision"] is None
    assert case["missing"] and case["recommendation"] is None
    state = service.workflow.graph.get_state({"configurable": {"thread_id": case["case_id"]}})
    assert state.next == ("human_review",)
    assert len({s["agent"] for s in case["steps"]}) == 8
    assert "assigned_pattern_ids" not in case["profile"]


def test_complete_report_review_and_sar_edit(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    service.add_demo_packet(alert["alert_id"])
    case = service.investigate(alert["alert_id"], force=True)
    assert not case["missing"]
    assert case["recommendation"] == "escalate"
    assert case["critic"]["passed"]
    assert case["sar_draft"] and not citation_defects(case)
    result = service.review(
        alert["alert_id"],
        {
            "case_id": case["case_id"],
            "investigator": "Test Investigator",
            "reason": "Reviewed the synthetic evidence and approved escalation.",
            "action": "escalate",
            "sar_narrative": "Investigator edited draft. Synthetic test only.",
        },
    )
    assert result["status"] == "reviewed"
    assert result["sar_narrative"] == "Investigator edited draft. Synthetic test only."
    assert "Human reviewed SAR narrative" in result["report"]
    assert "Investigator edited draft. Synthetic test only." in result["report"]
    assert result["decision"]["agrees_with_agents"]
    with pytest.raises(ValueError, match="not waiting"):
        service.review(alert["alert_id"], result["decision"])


def test_human_override_clear_retains_no_final_sar(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True)
    result = service.review(
        alert["alert_id"],
        {
            "case_id": case["case_id"],
            "investigator": "Analyst",
            "reason": "Documented source explains these transactions.",
            "action": "clear",
        },
    )
    assert result["sar_narrative"] is None
    assert "No SAR narrative retained" in result["report"]
    assert not result["decision"]["agrees_with_agents"]


def test_new_evidence_blocks_stale_decision(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True)
    service.add_document(
        {
            "document_id": "TEST-NEW-EVIDENCE",
            "customer_id": alert["customer_id"],
            "title": "New explanation",
            "content": "Additional synthetic source information.",
            "evidence_types": [alert["evidence_required"][0]],
        }
    )
    with pytest.raises(ValueError, match="Evidence changed"):
        service.review(
            alert["alert_id"],
            {
                "case_id": case["case_id"],
                "investigator": "Analyst",
                "reason": "Reviewed this evidence",
                "action": "clear",
            },
        )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_profile",
        "transaction_unavailable",
        "missing_document",
        "unreadable_document",
        "policy_conflict",
    ],
)
def test_failure_paths_end_with_incomplete_human_report(service, failure):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")
    case = service.investigate(alert["alert_id"], force=True, failure=failure)
    assert case["status"] == "awaiting_review"
    assert case["recommendation"] is None
    assert case["completeness"] == "incomplete" and case["missing"]
    assert case["report"]


def test_citation_and_numeric_guards():
    case = {
        "evidence": [{"id": "E1", "value": {"amount": 100}}],
        "findings": [{"text": "Amount is 200", "evidence_ids": ["E1"]}],
    }
    assert "number absent" in citation_defects(case)[0]
    case["findings"][0]["evidence_ids"] = ["MISSING"]
    assert "unknown evidence" in citation_defects(case)[0]


def test_decision_reason_cannot_be_whitespace():
    with pytest.raises(ValidationError):
        ReviewDecision(action="clear", reason="     ", investigator="Analyst", case_id="case")


def test_audit_is_append_only_and_verified(service):
    assert service.store.verify_audit()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        service.store.db.execute("DELETE FROM audit")
    service.store.db.rollback()


def test_document_upload_text_and_blank_pdf(service):
    from io import BytesIO

    from pypdf import PdfWriter

    alert = next(a for a in service.list_alerts() if a["family"] == "TM-09")
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/documents/extract",
            files={
                "file": (
                    "explanation.txt",
                    b"Synthetic supplier contract and payment explanation.",
                    "text/plain",
                )
            },
            data={
                "alert_id": alert["alert_id"],
                "evidence_types": __import__("json").dumps(alert["evidence_required"]),
            },
        )
        assert response.status_code == 200
        assert response.json()["source_sha256"]
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buffer = BytesIO()
        writer.write(buffer)
        response = client.post(
            "/documents/extract",
            files={"file": ("unreadable.pdf", buffer.getvalue(), "application/pdf")},
            data={
                "alert_id": alert["alert_id"],
                "evidence_types": __import__("json").dumps(alert["evidence_required"]),
            },
        )
        assert response.status_code == 200
        assert not response.json()["readable"]
        case = service.investigate(alert["alert_id"], force=True)
        assert case["recommendation"] is None
        assert any("Unreadable" in item for item in case["missing"])


def test_model_exception_fails_closed(service):
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")

    class UnavailableModel:
        def with_structured_output(self, schema):
            raise RuntimeError("Synthetic provider outage")

    service.workflow.model = UnavailableModel()
    try:
        case = service.investigate(alert["alert_id"], force=True)
        assert case["status"] == "awaiting_review"
        assert case["recommendation"] is None
        assert case["errors"]
        assert not case["critic"]["passed"]
    finally:
        service.workflow.model = None


def test_unsupported_model_claims_retry_then_reach_human(service):
    from aml_poc.models import Assessment
    from aml_poc.workflow import Critique, Narrative

    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")

    class UngroundedModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        def invoke(self, messages):
            if self.schema is Assessment:
                return Assessment(
                    summary="Synthetic assessment",
                    summary_evidence_ids=["E1"],
                    findings=[{"text": "Amount is 99999999999999", "evidence_ids": ["E1"]}],
                    innocent_explanation="A documented sale may explain the activity.",
                    recommendation="escalate",
                )
            if self.schema is Narrative:
                return Narrative(sentences=[{"text": "Amount is 99999999999999", "evidence_ids": ["E1"]}])
            return Critique(defects=[])

    service.workflow.model = UngroundedModel()
    try:
        case = service.investigate(alert["alert_id"], force=True)
        assert case["critique_attempts"] == 2
        assert case["recommendation"] is None
        assert case["status"] == "awaiting_review"
        assert not case["critic"]["passed"]
    finally:
        service.workflow.model = None


def test_monitoring_reads_stay_responsive_during_model_calls(service):
    import threading
    import time

    started, release = threading.Event(), threading.Event()
    alert = next(a for a in service.list_alerts() if a["family"] == "TM-01")

    class WaitingModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            started.set()
            release.wait(10)
            raise RuntimeError("Synthetic provider failure after wait")

    service.workflow.model = WaitingModel()
    thread = threading.Thread(target=service.investigate, args=(alert["alert_id"],), kwargs={"force": True})
    try:
        thread.start()
        assert started.wait(5)
        begin = time.monotonic()
        assert service.status()["transactions"] > 0
        assert time.monotonic() - begin < 1
    finally:
        release.set()
        thread.join(15)
        service.workflow.model = None
    assert not thread.is_alive()


def test_api_validation_and_reports(service):
    with TestClient(create_app(service)) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/replay/start", json={"events_per_second": -1}).status_code == 422
        assert client.get("/alerts/unknown").status_code == 404
        alert = client.get("/alerts").json()[0]
        response = client.post(
            f"/alerts/{alert['alert_id']}/investigate",
            json={"failure": "transaction_unavailable", "force": True},
        )
        assert response.status_code == 200
        case = response.json()
        assert client.get(f"/cases/{case['case_id']}/report").status_code == 200


def test_entire_stream_and_durable_restart(tmp_path):
    svc = Service(DATA, tmp_path, "demo")
    for row in svc.stream:
        svc.ingest(row)
    status = svc.status()
    stream_alerts = svc.list_alerts("stream")
    assert status["stream_processed"] == 1000
    assert {p for a in stream_alerts for p in a["pattern_ids"]} == {
        "TM-01",
        "TM-03",
        "TM-04",
        "TM-07",
        "TM-08",
        "TM-09",
    }
    alert = next(a for a in stream_alerts if a["family"] == "TM-08")
    svc.add_demo_packet(alert["alert_id"])
    case = svc.investigate(alert["alert_id"], force=True)
    assert case["recommendation"] == "request_info"
    before = copy.deepcopy(status)
    svc.close()
    svc = Service(DATA, tmp_path, "demo")
    assert svc.status()["transactions"] == before["transactions"]
    assert svc.status()["stream_processed"] == 1000
    loaded = svc.store.get_case(case["case_id"])
    assert loaded["report"] == case["report"]
    result = svc.review(
        alert["alert_id"],
        {
            "case_id": case["case_id"],
            "investigator": "Restart Analyst",
            "reason": "Requesting supporting contracts before a decision.",
            "action": "request_info",
        },
    )
    assert result["status"] == "reviewed"
    svc.advance_clock("2027-03-01T00:00:00")
    assert svc.store.get_alert(alert["alert_id"])["signal_status"] == "confirmed"
    assert svc.store.verify_audit()
    svc.close()
    svc = Service(DATA, tmp_path, "demo")
    assert svc.status()["event_clock"] == "2027-03-01T00:00:00"
    svc.close()
