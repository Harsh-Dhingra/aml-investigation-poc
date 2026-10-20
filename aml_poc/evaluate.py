"""Held-out evaluation. This module is never imported by the detector engine."""

import csv
from collections import defaultdict

from .data import by_customer
from .rules import DetectorEngine


def evaluate(data, include_stream=False):
    rows = data.history[:]
    label_paths = [data.path / "golden_labels.csv"]
    if include_stream:
        rows += data.read_transactions(data.path / "stream_transactions.csv")
        label_paths.append(data.path / "stream_labels.csv")
    labels = []
    for path in label_paths:
        with path.open() as f:
            labels += list(csv.DictReader(f))
    engine = DetectorEngine(data)
    as_of = max(r.txn_ts for r in rows)
    alerts = [
        a
        for customer, transactions in by_customer(rows).items()
        for a in engine.detect(customer, transactions, as_of)
    ]
    groups = defaultdict(set)
    normal = set()
    for row in labels:
        if row["label"] == "NORMAL":
            normal.add(row["transaction_id"])
        else:
            groups[(row["scenario_id"], row["pattern_id"])].add(row["transaction_id"])
    matches = []
    for (scenario, pattern), ids in sorted(groups.items()):
        found = [
            a["alert_id"]
            for a in alerts
            if pattern in a["pattern_ids"] and ids.intersection(a["transaction_ids"])
        ]
        matches.append(
            {"scenario": scenario, "pattern": pattern, "detected": bool(found), "alert_ids": found}
        )
    suspicious = set().union(*groups.values()) if groups else set()
    extra = [a for a in alerts if not suspicious.intersection(a["transaction_ids"])]
    flagged_normal = set().union(*(set(a["transaction_ids"]) & normal for a in alerts)) if alerts else set()
    return {
        "dataset": "history + stream" if include_stream else "history",
        "transactions": len(rows),
        "as_of": as_of.isoformat(),
        "alerts": len(alerts),
        "planted_episodes": len({s for s, _ in groups}),
        "scenario_pattern_groups": len(groups),
        "detected_groups": sum(r["detected"] for r in matches),
        "group_recall": sum(r["detected"] for r in matches) / len(groups) if groups else None,
        "alerts_without_planted_overlap": len(extra),
        "normal_rows_in_alert_evidence": len(flagged_normal),
        "normal_row_flag_rate": len(flagged_normal) / len(normal) if normal else None,
        "agent_quality": "Not measured; requires labeled live-model runs and human judgments",
        "method": "A group is detected if an alert cites at least one of its labeled transaction IDs and the same pattern ID. This is group coverage, not row recall or proof of investigator accuracy.",
        "matches": matches,
        "extra_alerts": [
            {k: a[k] for k in ["alert_id", "customer_id", "pattern_ids", "window_start", "window_end"]}
            for a in extra
        ],
    }
