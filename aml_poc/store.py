import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from functools import wraps

import duckdb

from .models import Transaction


def now():
    return datetime.now(UTC).isoformat()


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def synchronized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)

    return guarded


class Store:
    """Owned by one API process; the service serializes access with its lock."""

    def __init__(self, root, lock=None):
        self.lock = lock or threading.RLock()
        root.mkdir(parents=True, exist_ok=True)
        self.events = duckdb.connect(str(root / "transactions.duckdb"))
        self.events.execute(
            "CREATE TABLE IF NOT EXISTS transactions (transaction_id VARCHAR PRIMARY KEY, customer_id VARCHAR, txn_ts TIMESTAMP, direction VARCHAR, amount DECIMAL(18,2), payload VARCHAR, source VARCHAR)"
        )
        self.db = sqlite3.connect(root / "cases.sqlite", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, case_id TEXT, actor TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END;
          CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END;
        """)
        self.db.commit()

    @synchronized
    def close(self):
        self.events.close()
        self.db.close()

    @synchronized
    def add_events(self, rows, source):
        values = [
            (r.transaction_id, r.customer_id, r.txn_ts, r.direction, r.amount, r.model_dump_json(), source)
            for r in rows
        ]
        if values:
            self.events.execute("BEGIN TRANSACTION")
            try:
                self.events.executemany(
                    "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING", values
                )
                self.events.execute("COMMIT")
            except Exception:
                self.events.execute("ROLLBACK")
                raise

    @synchronized
    def transaction(self, transaction_id):
        row = self.events.execute(
            "SELECT payload FROM transactions WHERE transaction_id=?", [transaction_id]
        ).fetchone()
        return Transaction.model_validate_json(row[0]) if row else None

    @synchronized
    def all_transactions(self):
        return [
            Transaction.model_validate_json(r[0])
            for r in self.events.execute(
                "SELECT payload FROM transactions ORDER BY txn_ts, transaction_id"
            ).fetchall()
        ]

    @synchronized
    def baseline(self, customer_id, as_of):
        rows = self.events.execute(
            """SELECT direction, count(*), cast(sum(amount) as double)
          FROM transactions WHERE customer_id=? AND txn_ts<=? GROUP BY direction""",
            [customer_id, as_of],
        ).fetchall()
        return {direction: {"count": count, "amount": amount} for direction, count, amount in rows}

    @synchronized
    def put_alert(self, payload):
        old = self.get_alert(payload["alert_id"])
        clean = json.loads(dump(payload))

        # A ticking clock is not new evidence until the provisional signal changes state.
        def signature(value):
            value = json.loads(dump(value))
            value.pop("revision", None)
            value.pop("updated_at", None)
            value.get("metrics", {}).pop("quiet_days_after", None)
            return dump(value)

        if old and signature(old) == signature(clean):
            return old, False
        revision = (old["revision"] if old else 0) + 1
        clean.update(revision=revision, updated_at=now())
        self.db.execute(
            "INSERT INTO alerts VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, revision=excluded.revision",
            (clean["alert_id"], dump(clean), revision),
        )
        self.db.commit()
        self.audit(
            "rule_engine",
            "alert_updated" if old else "alert_created",
            {"alert_id": clean["alert_id"], "revision": revision, "patterns": clean["pattern_ids"]},
        )
        return clean, True

    @synchronized
    def get_alert(self, alert_id):
        row = self.db.execute("SELECT payload FROM alerts WHERE id=?", (alert_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @synchronized
    def alerts(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM alerts")]

    @synchronized
    def put_case(self, case):
        self.db.execute(
            "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
            (
                case["case_id"],
                case["alert"]["alert_id"],
                case["alert"]["revision"],
                case["status"],
                dump(case),
                case["created_at"],
            ),
        )
        self.db.commit()

    @synchronized
    def get_case(self, case_id):
        row = self.db.execute("SELECT payload FROM cases WHERE id=?", (case_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @synchronized
    def latest_case(self, alert_id):
        row = self.db.execute(
            "SELECT payload FROM cases WHERE alert_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (alert_id,),
        ).fetchone()
        return json.loads(row[0]) if row else None

    @synchronized
    def all_cases(self):
        return [
            json.loads(r[0]) for r in self.db.execute("SELECT payload FROM cases ORDER BY created_at DESC")
        ]

    @synchronized
    def metadata(self, key, default=None):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @synchronized
    def set_metadata(self, key, value):
        self.db.execute(
            "INSERT INTO metadata VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, dump(value)),
        )
        self.db.commit()

    @synchronized
    def documents(self, customer_id):
        return [
            d
            for r in self.db.execute("SELECT payload FROM documents")
            if (d := json.loads(r[0]))["customer_id"] == customer_id
        ]

    @synchronized
    def put_document(self, document):
        # Evidence is immutable; a correction must have a new document ID.
        old = self.db.execute(
            "SELECT payload FROM documents WHERE id=?", (document["document_id"],)
        ).fetchone()
        if old:
            if json.loads(old[0]) != document:
                raise ValueError("Document ID exists; use a new ID for a correction")
            return False
        self.db.execute("INSERT INTO documents VALUES (?, ?)", (document["document_id"], dump(document)))
        self.db.commit()
        self.audit(
            "document_intake",
            "document_added",
            {"document_id": document["document_id"], "customer_id": document["customer_id"]},
        )
        return True

    @synchronized
    def audit(self, actor, event, payload, case_id=None):
        prior = self.db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = prior[0] if prior else "0" * 64
        ts = now()
        serialized = dump(payload)
        digest = hashlib.sha256(dump([ts, case_id, actor, event, serialized, previous]).encode()).hexdigest()
        self.db.execute(
            "INSERT INTO audit(ts, case_id, actor, event, payload, previous_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, case_id, actor, event, serialized, previous, digest),
        )
        self.db.commit()

    @synchronized
    def audit_rows(self, case_id=None):
        query = "SELECT * FROM audit" + (" WHERE case_id=?" if case_id else "") + " ORDER BY seq"
        rows = self.db.execute(query, (case_id,) if case_id else ()).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    @synchronized
    def verify_audit(self):
        previous = "0" * 64
        for r in self.db.execute("SELECT * FROM audit ORDER BY seq"):
            expected = hashlib.sha256(
                dump([r["ts"], r["case_id"], r["actor"], r["event"], r["payload"], previous]).encode()
            ).hexdigest()
            if r["previous_hash"] != previous or r["hash"] != expected:
                return False
            previous = r["hash"]
        return True
