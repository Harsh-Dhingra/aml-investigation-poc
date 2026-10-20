"""Load operational data. Evaluation labels are deliberately absent from this module."""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .models import Transaction


class Dataset:
    def __init__(self, path: Path):
        self.path = path
        self.customers = self._index("customers", "customer_id")
        self.accounts = self._index("accounts", "account_id")
        self.counterparties = self._index("counterparties", "counterparty_id")
        policy_bytes = (path / "policy_patterns.json").read_bytes()
        self.policy_hash = hashlib.sha256(policy_bytes).hexdigest()
        self.policy = json.loads(policy_bytes)
        self.patterns = {p["pattern_id"]: p for p in self.policy["patterns"]}
        self.enabled = {k: p for k, p in self.patterns.items() if p["enabled_for_initial_synthesis"]}
        supported = {"TM-01", "TM-03", "TM-04", "TM-07", "TM-08", "TM-09"}
        if self.enabled.keys() - supported:
            raise ValueError("Unsupported enabled detectors: " + str(self.enabled.keys() - supported))
        required = {
            "TM-01": {
                "near_threshold_floor_usd",
                "near_threshold_ceiling_usd",
                "min_txn_count",
                "window_days",
                "min_aggregate_usd",
            },
            "TM-03": {
                "min_distinct_out_of_state_states",
                "min_deposit_count",
                "window_days",
                "min_out_of_region_share",
            },
            "TM-04": {"max_hours_deposit_to_outflow", "min_outflow_to_inflow_ratio"},
            "TM-07": {"amount_tolerance_pct", "max_days_between", "min_pairs", "min_amount_usd"},
            "TM-08": {
                "quiet_days_before",
                "active_burst_days_max",
                "quiet_days_after",
                "min_burst_wire_count",
                "min_burst_total_usd",
            },
            "TM-09": {"min_round_wire_share", "min_wire_count", "lookback_days", "new_counterparty_days"},
        }
        for key, pattern in self.enabled.items():
            thresholds = pattern["demo_thresholds"]
            if required[key] - thresholds.keys():
                raise ValueError(f"Missing policy thresholds for {key}")
            for field in required[key]:
                if not isinstance(thresholds[field], (int, float)) or thresholds[field] <= 0:
                    raise ValueError(f"Invalid positive threshold: {key}.{field}")
        self.history = self.read_transactions(path / "transactions.csv")
        self.start = self.history[0].txn_ts

    def _index(self, filename, key):
        entries = json.loads((self.path / f"{filename}.json").read_text())[filename]
        indexed = {r[key]: r for r in entries}
        if len(indexed) != len(entries):
            raise ValueError(f"Duplicate {filename} IDs")
        return indexed

    def validate_transaction(self, transaction: Transaction):
        if transaction.customer_id not in self.customers:
            raise ValueError("Customer profile missing; event rejected for manual review")
        account = self.accounts.get(transaction.account_id)
        if not account or account["customer_id"] != transaction.customer_id:
            raise ValueError("Account does not belong to customer")

    def read_transactions(self, path):
        with Path(path).open(newline="") as handle:
            rows = [Transaction.model_validate(row) for row in csv.DictReader(handle)]
        if not rows:
            raise ValueError("Transaction input is empty")
        if len({r.transaction_id for r in rows}) != len(rows):
            raise ValueError("Transaction IDs must be unique")
        for row in rows:
            self.validate_transaction(row)
        return sorted(rows, key=lambda r: (r.txn_ts, r.transaction_id))


def by_customer(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row.customer_id].append(row)
    return groups
