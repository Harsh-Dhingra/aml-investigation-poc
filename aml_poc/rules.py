"""Event-time rules. No labels, scenario IDs, descriptions, or model calls are used.

Episode grouping is an operational deduplication choice, not a regulatory threshold.
TM-07 and TM-09 use 30 days of indicator inactivity to separate episodes.
"""

import hashlib
from datetime import timedelta
from decimal import Decimal


def cents(value):
    return Decimal(str(value))


def total(rows):
    return sum((r.amount for r in rows), Decimal(0))


def clusters(rows, gap_days):
    groups = []
    for row in sorted(rows, key=lambda r: (r.txn_ts, r.transaction_id)):
        if not groups or row.txn_ts - groups[-1][-1].txn_ts > timedelta(days=gap_days):
            groups.append([])
        groups[-1].append(row)
    return groups


class DetectorEngine:
    def __init__(self, dataset):
        self.data = dataset

    def thresholds(self, pattern):
        return self.data.enabled[pattern]["demo_thresholds"]

    def alert(self, customer, family, rows, patterns, metrics, detected, status="confirmed"):
        rows = sorted(
            {r.transaction_id: r for r in rows}.values(), key=lambda r: (r.txn_ts, r.transaction_id)
        )
        key = f"{customer}:{family}:{rows[0].transaction_id}"
        alert_id = "ALR-" + hashlib.sha256(key.encode()).hexdigest()[:12].upper()
        evidence = list(
            dict.fromkeys(e for p in patterns for e in self.data.patterns[p]["evidence_required"])
        )
        priority = "high" if len(patterns) > 1 or family in {"TM-01", "TM-07"} else "medium"
        if status == "provisional":
            priority = "low"
        return {
            "alert_id": alert_id,
            "customer_id": customer,
            "family": family,
            "pattern_ids": patterns,
            "window_start": rows[0].txn_ts.isoformat(),
            "window_end": rows[-1].txn_ts.isoformat(),
            "detected_at": detected.isoformat(),
            "transaction_ids": [r.transaction_id for r in rows],
            "amount": float(total(rows)),
            "metrics": metrics,
            "priority": priority,
            "signal_status": status,
            "policy_hash": self.data.policy_hash,
            "thresholds": {p: self.thresholds(p) for p in patterns},
            "evidence_required": evidence,
        }

    def detect(self, customer_id, rows, as_of):
        rows = sorted((r for r in rows if r.txn_ts <= as_of), key=lambda r: (r.txn_ts, r.transaction_id))
        if not rows:
            return []
        customer = self.data.customers[customer_id]
        result = []
        if "TM-01" in self.data.enabled:
            p = self.thresholds("TM-01")
            cash = [
                r
                for r in rows
                if r.cash_flag
                and p["near_threshold_floor_usd"] <= r.amount <= cents(p["near_threshold_ceiling_usd"])
            ]
            for group in clusters(cash, p["window_days"]):
                trigger = None
                for row in group:
                    window = [
                        r
                        for r in group
                        if row.txn_ts - timedelta(days=p["window_days"]) <= r.txn_ts <= row.txn_ts
                    ]
                    if len(window) >= p["min_txn_count"] and total(window) > p["min_aggregate_usd"]:
                        trigger = row.txn_ts
                        break
                if trigger:
                    result.append(
                        self.alert(
                            customer_id,
                            "TM-01",
                            group,
                            ["TM-01"],
                            {
                                "near_threshold_count": len(group),
                                "cash_total": float(total(group)),
                                "expected_monthly_cash_max": customer["expected_cash_activity"][
                                    "monthly_cash_deposit_total_usd"
                                ]["max"],
                            },
                            trigger,
                        )
                    )
        if "TM-03" in self.data.enabled:
            p = self.thresholds("TM-03")
            cash = [r for r in rows if r.cash_flag and r.direction == "INCOMING" and r.amount < 10000]
            outside = [
                r
                for r in cash
                if r.branch_state and r.branch_state not in customer["expected_operating_states"]
            ]
            for group in clusters(outside, p["window_days"]):
                trigger = None
                for row in group:
                    window = [
                        r
                        for r in cash
                        if row.txn_ts - timedelta(days=p["window_days"]) <= r.txn_ts <= row.txn_ts
                    ]
                    out = [
                        r
                        for r in window
                        if r.branch_state and r.branch_state not in customer["expected_operating_states"]
                    ]
                    states = {r.branch_state for r in out}
                    if (
                        len(out) >= p["min_deposit_count"]
                        and len(states) >= p["min_distinct_out_of_state_states"]
                        and len(out) / len(window) >= p["min_out_of_region_share"]
                    ):
                        trigger = row.txn_ts
                        break
                if not trigger:
                    continue
                patterns = ["TM-03"]
                matched, allocations = [], []
                allocated = Decimal(0)
                if "TM-04" in self.data.enabled:
                    q = self.thresholds("TM-04")
                    # FIFO attribution heuristic. A dollar of an outgoing payment is never reused.
                    remaining = {r.transaction_id: r.amount for r in group}
                    for outflow in rows:
                        if outflow.direction != "OUTGOING" or outflow.txn_type not in {"wire_out", "check"}:
                            continue
                        available = outflow.amount
                        used = Decimal(0)
                        for deposit in group:
                            hours = (outflow.txn_ts - deposit.txn_ts).total_seconds() / 3600
                            if 0 <= hours <= q["max_hours_deposit_to_outflow"]:
                                portion = min(available, remaining[deposit.transaction_id])
                                if portion:
                                    allocations.append(
                                        {
                                            "deposit_id": deposit.transaction_id,
                                            "outflow_id": outflow.transaction_id,
                                            "amount": float(portion),
                                            "hours": round(hours, 2),
                                        }
                                    )
                                    available -= portion
                                    remaining[deposit.transaction_id] -= portion
                                    allocated += portion
                                    used += portion
                        if used:
                            matched.append(outflow)
                    if allocated / total(group) >= cents(q["min_outflow_to_inflow_ratio"]):
                        patterns.append("TM-04")
                result.append(
                    self.alert(
                        customer_id,
                        "TM-03",
                        group + matched,
                        patterns,
                        {
                            "out_of_region_count": len(group),
                            "deposit_total": float(total(group)),
                            "states": sorted({r.branch_state for r in group}),
                            "allocated_outflow": float(allocated),
                            "outflow_ratio": float(allocated / total(group)),
                            "attribution_method": "FIFO within 72h; capped by each deposit; heuristic, not proof of funds provenance",
                            "allocations": allocations,
                        },
                        trigger,
                    )
                )
        if "TM-07" in self.data.enabled:
            p = self.thresholds("TM-07")
            incoming = [r for r in rows if r.direction == "INCOMING" and r.amount >= p["min_amount_usd"]]
            outgoing = [
                r
                for r in rows
                if r.direction == "OUTGOING" and r.txn_type in {"wire_out", "check", "ach_debit"}
            ]
            pairs, used = [], set()
            for credit in incoming:
                possible = [
                    r
                    for r in outgoing
                    if r.transaction_id not in used
                    and 0 <= (r.txn_ts - credit.txn_ts).total_seconds() <= p["max_days_between"] * 86400
                    and abs(r.amount - credit.amount) / credit.amount <= cents(p["amount_tolerance_pct"])
                ]
                if possible:
                    debit = min(
                        possible, key=lambda r: (abs(r.amount - credit.amount), r.txn_ts, r.transaction_id)
                    )
                    used.add(debit.transaction_id)
                    pairs.append((credit, debit))
            mapping = {a.transaction_id: b for a, b in pairs}
            for group in clusters([a for a, _ in pairs], 30):
                if len(group) < p["min_pairs"]:
                    continue
                paired = [mapping[a.transaction_id] for a in group]
                detected = sorted(paired, key=lambda r: r.txn_ts)[p["min_pairs"] - 1].txn_ts
                result.append(
                    self.alert(
                        customer_id,
                        "TM-07",
                        group + paired,
                        ["TM-07"],
                        {
                            "pair_count": len(group),
                            "incoming_total": float(total(group)),
                            "outgoing_total": float(total(paired)),
                            "pairs": [
                                {
                                    "incoming": a.transaction_id,
                                    "outgoing": mapping[a.transaction_id].transaction_id,
                                    "ratio": float(mapping[a.transaction_id].amount / a.amount),
                                    "hours": round(
                                        (mapping[a.transaction_id].txn_ts - a.txn_ts).total_seconds() / 3600,
                                        2,
                                    ),
                                }
                                for a in group
                            ],
                            "matching_method": "one-to-one nearest amount, then earliest payment",
                        },
                        detected,
                    )
                )
        if "TM-08" in self.data.enabled:
            p = self.thresholds("TM-08")
            wires = [r for r in rows if r.txn_type in {"wire_in", "wire_out"}]
            groups = clusters(wires, p["quiet_days_before"])
            previous = self.data.start
            for group in groups:
                quiet_before = (group[0].txn_ts - previous).total_seconds() / 86400
                duration = (group[-1].txn_ts - group[0].txn_ts).total_seconds() / 86400
                previous = group[-1].txn_ts
                conflict = len(group) > customer["expected_wire_activity"]["monthly_wire_count"]["max"]
                if (
                    quiet_before < p["quiet_days_before"]
                    or duration > p["active_burst_days_max"]
                    or len(group) < p["min_burst_wire_count"]
                    or total(group) < p["min_burst_total_usd"]
                    or not conflict
                ):
                    continue
                threshold_row = next(
                    r
                    for i, r in enumerate(group)
                    if i + 1 >= p["min_burst_wire_count"]
                    and total(group[: i + 1]) >= p["min_burst_total_usd"]
                )
                quiet_after = max(0, (as_of - group[-1].txn_ts).total_seconds() / 86400)
                status = "confirmed" if quiet_after >= p["quiet_days_after"] else "provisional"
                result.append(
                    self.alert(
                        customer_id,
                        "TM-08",
                        group,
                        ["TM-08"],
                        {
                            "wire_count": len(group),
                            "wire_total": float(total(group)),
                            "burst_days": round(duration, 2),
                            "quiet_days_before": round(quiet_before, 2),
                            "quiet_days_after": round(quiet_after, 2),
                            "confirmation_due": (
                                group[-1].txn_ts + timedelta(days=p["quiet_days_after"])
                            ).isoformat(),
                        },
                        threshold_row.txn_ts,
                        status,
                    )
                )
        if "TM-09" in self.data.enabled:
            p = self.thresholds("TM-09")
            wires = [
                r
                for r in rows
                if r.txn_type in {"wire_in", "wire_out"} and r.counterparty_country not in {"", "US"}
            ]

            def anomalies(r):
                known = self.data.counterparties.get(r.counterparty_id, {}).get(
                    "is_known_counterparty", False
                )
                return (
                    not r.purpose_field
                    or not r.invoice_id
                    or not known
                    or r.counterparty_country not in customer["expected_countries"]
                )

            indicators = [r for r in wires if anomalies(r)]
            # Missing information gets grouped by indicator inactivity. Normal wires don't bridge episodes.
            groups = clusters(indicators, 30)
            # A round-only signal is also supported, even when all payment fields are populated.
            for group in clusters([r for r in wires if r.is_round_amount and not anomalies(r)], 30):
                if group:
                    groups.append(group)
            for group in groups:
                trigger = None
                for row in group:
                    window = [
                        r
                        for r in wires
                        if row.txn_ts - timedelta(days=p["lookback_days"]) <= r.txn_ts <= row.txn_ts
                    ]
                    share = sum(r.is_round_amount for r in window) / len(window)
                    if len(window) >= p["min_wire_count"] and (
                        any(anomalies(r) for r in window) or share >= p["min_round_wire_share"]
                    ):
                        trigger = row.txn_ts
                        break
                if trigger:
                    # Keep source windows bounded even when a long-lived indicator episode is deduplicated.
                    selected = [
                        r for r in group if r.txn_ts >= group[-1].txn_ts - timedelta(days=p["lookback_days"])
                    ]
                    result.append(
                        self.alert(
                            customer_id,
                            "TM-09",
                            group,
                            ["TM-09"],
                            {
                                "indicator_wire_count": len(group),
                                "latest_window_indicator_count": len(selected),
                                "round_share": sum(r.is_round_amount for r in group) / len(group),
                                "missing_purpose_count": sum(not r.purpose_field for r in group),
                                "missing_invoice_count": sum(not r.invoice_id for r in group),
                                "countries": sorted({r.counterparty_country for r in group}),
                            },
                            trigger,
                        )
                    )
        return result
