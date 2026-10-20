import copy
import hashlib
import threading
import uuid
from datetime import datetime

from .config import DATA, RUNTIME, agent_mode
from .data import Dataset, by_customer
from .models import EvidenceDocument, ReviewDecision, Transaction
from .rules import DetectorEngine
from .store import Store, dump, now
from .workflow import Workflow


class Service:
    def __init__(self, data_path=DATA, runtime_path=RUNTIME, mode=None):
        self.lock = threading.RLock()
        self.graph_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.error = None
        self.data = Dataset(data_path)
        self.store = Store(runtime_path, lock=self.lock)
        self.mode = mode or agent_mode()
        known_hash = self.store.metadata("policy_hash")
        if known_hash and known_hash != self.data.policy_hash:
            self.store.close()
            raise ValueError(
                "Policy changed. Use a new AML_RUNTIME_DIR to preserve the existing policy-versioned audit run."
            )
        self.store.set_metadata("policy_hash", self.data.policy_hash)
        if not self.store.metadata("history_loaded", False):
            self.store.add_events(self.data.history, "history")
            self.store.set_metadata("history_loaded", True)
        self.rows = self.store.all_transactions()
        self.groups = by_customer(self.rows)
        self.clock = max(
            max(r.txn_ts for r in self.rows),
            datetime.fromisoformat(self.store.metadata("clock", "2000-01-01T00:00:00")),
        )
        self.engine = DetectorEngine(self.data)
        self.workflow = Workflow(self.data, self.store, runtime_path, self.mode)
        self.reconcile()
        for case in self.store.all_cases():
            if (
                case["status"] == "awaiting_review"
                and self.store.latest_case(case["alert"]["alert_id"])["case_id"] != case["case_id"]
            ):
                case["status"] = "superseded"
                self.store.put_case(case)
                continue
            if case["status"] != "reviewed":
                state = self.workflow.graph.get_state({"configurable": {"thread_id": case["case_id"]}})
                if state.values and state.values["case"].get("decision"):
                    self._save_review(state.values["case"])
        self.stream = (
            self.data.read_transactions(data_path / "stream_transactions.csv")
            if (data_path / "stream_transactions.csv").exists()
            else []
        )
        self.stream_ids = {r.transaction_id for r in self.stream}
        self.stream_done = len(self.stream_ids.intersection(r.transaction_id for r in self.rows))

    def reconcile(self, customer=None):
        for cid in [customer] if customer else list(self.groups):
            active = self.engine.detect(cid, self.groups[cid], self.clock)
            active_ids = {a["alert_id"] for a in active}
            for payload in active:
                self.store.put_alert(payload)
            # A provisional burst can be invalidated by continued wire activity.
            for old in self.store.alerts():
                if (
                    old["customer_id"] == cid
                    and old["alert_id"] not in active_ids
                    and old["signal_status"] != "withdrawn"
                ):
                    self.store.put_alert(
                        {
                            **{k: v for k, v in old.items() if k not in {"revision", "updated_at"}},
                            "signal_status": "withdrawn",
                            "priority": "low",
                        }
                    )

    def ingest(self, row):
        row = Transaction.model_validate(row) if not isinstance(row, Transaction) else row
        self.data.validate_transaction(row)
        with self.lock:
            old = self.store.transaction(row.transaction_id)
            if old:
                if old.model_dump(mode="json") != row.model_dump(mode="json"):
                    raise ValueError("Transaction ID reused with different contents")
                return {"inserted": False, "transaction_id": row.transaction_id}
            if row.txn_ts < self.clock:
                raise ValueError(
                    "Late event rejected: event time precedes the watermark; replay in order or start a new run"
                )
            self.store.add_events([row], "stream" if row.transaction_id in self.stream_ids else "external")
            self.rows.append(row)
            self.groups[row.customer_id].append(row)
            self.clock = row.txn_ts
            self.reconcile(row.customer_id)
            # Timer-driven rules progress even if the next event belongs to another customer.
            for cid in self.groups:
                if cid != row.customer_id and any(
                    a["customer_id"] == cid and a["family"] == "TM-08" and a["signal_status"] == "provisional"
                    for a in self.store.alerts()
                ):
                    self.reconcile(cid)
            self.stream_done = len(self.stream_ids.intersection(r.transaction_id for r in self.rows))
            return {"inserted": True, "transaction_id": row.transaction_id}

    def advance_clock(self, target):
        stamp = datetime.fromisoformat(target)
        with self.lock:
            if stamp < self.clock:
                raise ValueError("Event clock cannot move backwards")
            self.clock = stamp
            self.store.set_metadata("clock", target)
            self.reconcile()
            self.store.audit("replay_clock", "clock_advanced", {"as_of": target})
        return self.status()

    def list_alerts(self, scope="all"):
        with self.lock:
            output = []
            for alert in self.store.alerts():
                is_stream = any(i in self.stream_ids for i in alert["transaction_ids"])
                if scope == "stream" and not is_stream or scope == "history" and is_stream:
                    continue
                case = self.store.latest_case(alert["alert_id"])
                profile = self.data.customers[alert["customer_id"]]
                output.append(
                    {
                        **alert,
                        "customer_name": profile.get("business_name") or profile["fake_name"],
                        "source": "stream" if is_stream else "history",
                        "case_id": case["case_id"] if case else None,
                        "case_status": case["status"] if case else "not_started",
                        "recommendation": case.get("recommendation") if case else None,
                        "report_stale": bool(
                            case
                            and (
                                case["alert"]["revision"] != alert["revision"]
                                or case.get("document_version") != self.document_version(alert["customer_id"])
                            )
                        ),
                    }
                )
            return sorted(output, key=lambda a: a["detected_at"], reverse=True)

    def investigate(self, alert_id, failure="none", force=False):
        with self.graph_lock:
            with self.lock:
                alert = self.store.get_alert(alert_id)
                if not alert:
                    raise ValueError("Unknown alert")
                previous = self.store.latest_case(alert_id)
                if (
                    previous
                    and not force
                    and failure == "none"
                    and previous["alert"]["revision"] == alert["revision"]
                    and previous["mode"] == self.mode
                    and previous["document_version"] == self.document_version(alert["customer_id"])
                    and previous["status"] in {"reviewed", "awaiting_review"}
                ):
                    return previous
                case_id = f"CASE-{alert_id[4:]}-R{alert['revision']}-{uuid.uuid4().hex[:6]}"
                if previous and previous["status"] in {"awaiting_review", "investigating"}:
                    previous["status"] = "superseded"
                    self.store.put_case(previous)
                case = {
                    "case_id": case_id,
                    "alert": copy.deepcopy(alert),
                    "as_of": self.clock.isoformat(),
                    "mode": self.mode,
                    "created_at": now(),
                    "status": "investigating",
                    "active_agent": "orchestrator",
                    "failure": failure,
                    "evidence": [],
                    "missing": [],
                    "errors": [],
                    "steps": [],
                    "decision": None,
                    "recommendation": None,
                    "document_version": self.document_version(alert["customer_id"]),
                }
                self.store.put_case(case)
                self.store.audit(
                    "orchestrator",
                    "investigation_started",
                    {"alert_revision": alert["revision"], "mode": self.mode, "failure_simulation": failure},
                    case_id,
                )
            # Each store operation is serialized; model latency must not block monitoring reads.
            result = self.workflow.run(case)
            self.store.put_case(result)
            return result

    def document_version(self, customer_id):
        return hashlib.sha256(dump(self.store.documents(customer_id)).encode()).hexdigest()

    def add_document(self, document):
        doc = EvidenceDocument.model_validate(document).model_dump()
        if doc["customer_id"] not in self.data.customers:
            raise ValueError("Unknown customer")
        with self.lock:
            for transaction_id in doc["transaction_ids"]:
                row = self.store.transaction(transaction_id)
                if not row or row.customer_id != doc["customer_id"]:
                    raise ValueError("Document references an unknown or different customer's transaction")
            self.store.put_document(doc)
        return doc

    def add_demo_packet(self, alert_id, complete=True, resolution="unresolved"):
        with self.lock:
            alert = self.store.get_alert(alert_id)
            if not alert:
                raise ValueError("Unknown alert")
            required = alert["evidence_required"]
            doc = {
                "document_id": f"DEMO-{alert_id}-R{alert['revision']}-{'FULL' if complete else 'PART'}-{resolution}",
                "customer_id": alert["customer_id"],
                "title": "Synthetic supporting evidence packet",
                "content": "SYNTHETIC FIXTURE: source-of-funds explanation, counterparty relationships and business-purpose records supplied for demonstrating the review workflow. This packet is not independent verification and must never support a real filing.",
                "evidence_types": required if complete else required[:1],
                "transaction_ids": alert["transaction_ids"],
                "readable": True,
                "extraction_confidence": 1.0,
                "origin": "synthetic_fixture",
                "demonstration_resolution": resolution,
            }
            self.add_document(doc)
            return doc

    def _save_review(self, case):
        prior = self.store.get_case(case["case_id"])
        self.store.put_case(case)
        if not prior or prior["status"] != "reviewed":
            self.store.audit(
                case["decision"]["investigator"], "human_decision", case["decision"], case["case_id"]
            )

    def review(self, alert_id, decision):
        decision = ReviewDecision.model_validate(decision).model_dump()
        if len(decision["reason"].strip()) < 5:
            raise ValueError("A reason of at least five characters is required")
        with self.graph_lock, self.lock:
            case = self.store.get_case(decision["case_id"])
            alert = self.store.get_alert(alert_id)
            if not case or not alert or case["alert"]["alert_id"] != alert_id:
                raise ValueError("Case does not belong to this alert")
            if case["status"] != "awaiting_review":
                raise ValueError("Case is not waiting for review")
            if self.store.latest_case(alert_id)["case_id"] != case["case_id"]:
                raise ValueError("A newer report exists. Review the latest case version.")
            if case["alert"]["revision"] != alert["revision"] or case[
                "document_version"
            ] != self.document_version(alert["customer_id"]):
                raise ValueError("Evidence changed. Generate a fresh report before recording a decision.")
            result = self.workflow.resume(case["case_id"], decision)
            self._save_review(result)
            return result

    def status(self):
        with self.lock:
            alerts = self.store.alerts()
            cases = self.store.all_cases()
            return {
                "mode": self.mode,
                "model": self.workflow.model_name,
                "event_clock": self.clock.isoformat(),
                "history_rows": len(self.data.history),
                "transactions": len(self.rows),
                "stream_total": len(self.stream),
                "stream_processed": self.stream_done,
                "running": bool(self.worker and self.worker.is_alive() and not self.stop_event.is_set()),
                "alerts": len(alerts),
                "stream_alerts": sum(any(i in self.stream_ids for i in a["transaction_ids"]) for a in alerts),
                "awaiting_review": sum(c["status"] == "awaiting_review" for c in cases),
                "reviewed": sum(c["status"] == "reviewed" for c in cases),
                "error": self.error,
                "policy_hash": self.data.policy_hash,
                "audit_integrity": self.store.verify_audit(),
                "tracing": __import__("os").environ.get("LANGSMITH_TRACING", "false").lower() == "true",
            }

    def start(self, events_per_second=50, auto_investigate=True):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError("Replay worker is active; pause and wait for it to stop")
            if not self.stream:
                raise ValueError("Generate the stream first with aml-poc prepare")
            self.stop_event.clear()
            self.error = None
            self.store.audit(
                "replay",
                "stream_started",
                {"events_per_second": events_per_second, "auto_investigate": auto_investigate},
            )
            self.worker = threading.Thread(
                target=self._replay, args=(events_per_second, auto_investigate), daemon=True
            )
            self.worker.start()
        return self.status()

    def _replay(self, rate, investigate):
        try:
            for transaction in self.stream:
                if self.stop_event.is_set():
                    break
                with self.lock:
                    exists = self.store.transaction(transaction.transaction_id)
                if exists:
                    continue
                self.ingest(transaction)
                if self.stop_event.wait(1 / rate):
                    break
            if investigate and not self.stop_event.is_set():
                for alert in self.list_alerts("stream"):
                    if self.stop_event.is_set():
                        break
                    self.investigate(alert["alert_id"])
        except Exception as error:  # noqa: BLE001 - worker failures are surfaced in status and audit
            self.error = f"{type(error).__name__}: {error}"
        finally:
            with self.lock:
                self.store.audit(
                    "replay",
                    "stream_paused" if self.stop_event.is_set() else "stream_finished",
                    {"processed": self.stream_done, "error": self.error},
                )

    def pause(self):
        self.stop_event.set()
        return self.status()

    def recent(self, limit=30):
        with self.lock:
            return [r.model_dump(mode="json") for r in self.rows[-limit:]][::-1]

    def close(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=180)
            if self.worker.is_alive():
                raise RuntimeError("Worker did not stop; database left open to avoid corrupting active work")
        self.workflow.close()
        self.store.close()
