"""Operational data adapter for the supplied React KYC dashboard."""

from collections import defaultdict


def customer(service, key):
    c = {k: v for k, v in service.data.customers[key].items() if k != "assigned_pattern_ids"}
    for name in [
        "pep_flag",
        "id_verified",
        "sanctions_status",
        "kyc_last_review_date",
        "kyc_next_review_date",
        "days_until_review",
        "current_balance_usd",
    ]:
        c.setdefault(name, None)
    c["kyc_review_status"] = "UNKNOWN"
    for source, target in [
        ("expected_monthly_transaction_count", "expected_monthly_txn_count"),
        ("expected_monthly_transaction_volume_usd", "expected_monthly_volume_usd"),
    ]:
        for bound in ["min", "max"]:
            c[f"{target}_{bound}"] = c.get(source, {}).get(bound)
    return c


def transactions(service, key):
    with service.lock:
        rows = [r.model_dump(mode="json") for r in service.rows if r.customer_id == key]
    for r in rows:
        cp = service.data.counterparties.get(r.get("counterparty_id"))
        r.update(
            amount=float(r["amount"]),
            party_name=cp["name"] if cp else None,
            party_on_file=bool(cp),
            balance_after=None,
            description=r.get("purpose_field"),
        )
    return rows


def profile(service, key):
    rows = transactions(service, key)
    accounts = []
    for original in service.data.accounts.values():
        if original["customer_id"] != key:
            continue
        a = dict(original)
        for bound in ["min", "max"]:
            a[f"expected_balance_{bound}_usd"] = a.get("expected_balance_range_usd", {}).get(bound)
        a.update(
            current_balance_usd=None,
            current_balance_date=None,
            last_activity_date=rows[-1]["txn_ts"] if rows else None,
        )
        accounts.append(a)
    groups = defaultdict(list)
    for r in rows:
        groups[r["txn_ts"][:7]].append(r)
    monthly = []
    for month, rr in sorted(groups.items()):
        cash = [r for r in rr if r["txn_type"] == "cash_deposit"]
        wires = [r for r in rr if "wire" in r["txn_type"]]
        monthly.append(
            {
                "account_id": rr[0]["account_id"],
                "month": month,
                "is_partial_month": month in [rows[0]["txn_ts"][:7], rows[-1]["txn_ts"][:7]],
                "transaction_count": len(rr),
                "total_in_usd": sum(r["amount"] for r in rr if r["direction"] == "INCOMING"),
                "total_out_usd": sum(r["amount"] for r in rr if r["direction"] == "OUTGOING"),
                "cash_deposit_count": len(cash),
                "cash_deposit_total_usd": sum(r["amount"] for r in cash),
                "wire_count": len(wires),
                "wire_total_usd": sum(r["amount"] for r in wires),
                "month_end_balance_usd": None,
            }
        )
    full = [m for m in monthly if not m["is_partial_month"]]
    actual = {"full_months": len(full)}
    for label, field in [
        ("txn_count", "transaction_count"),
        ("volume_usd", None),
        ("cash_deposit_count", "cash_deposit_count"),
        ("cash_deposit_total_usd", "cash_deposit_total_usd"),
        ("wire_count", "wire_count"),
    ]:
        values = [m[field] if field else max(m["total_in_usd"], m["total_out_usd"]) for m in full]
        actual["avg_" + label] = sum(values) / len(values) if values else None
        actual["max_" + label] = max(values) if values else None

    def breakdown(field, output):
        grouped = defaultdict(list)
        for r in rows:
            grouped[r.get(field) or "UNKNOWN"].append(r)
        return [
            {output: k, "txn_count": len(v), "total_usd": sum(r["amount"] for r in v)}
            for k, v in grouped.items()
        ]

    counterparties = []
    for cp in service.data.counterparties.values():
        if key not in cp.get("associated_customer_ids", []):
            continue
        rr = [r for r in rows if r["counterparty_id"] == cp["counterparty_id"]]
        bounds = cp.get("expected_amount_range_usd", {})
        vals = [r["amount"] for r in rr]
        counterparties.append(
            dict(
                cp,
                txn_count=len(rr),
                total_usd=sum(vals),
                avg_amount_usd=sum(vals) / len(vals) if vals else None,
                max_amount_usd=max(vals) if vals else None,
                expected_amount_min_usd=bounds.get("min"),
                expected_amount_max_usd=bounds.get("max"),
                outside_range_count=sum(
                    v < bounds.get("min", 0) or v > bounds.get("max", float("inf")) for v in vals
                ),
                last_txn_ts=rr[-1]["txn_ts"] if rr else None,
            )
        )
    unknown = [
        {
            "name": r.get("party_name"),
            "country": r.get("counterparty_country"),
            "direction": r["direction"],
            "txn_type": r["txn_type"],
            "first_txn_ts": r["txn_ts"],
            "last_txn_ts": r["txn_ts"],
            "txn_count": 1,
            "total_usd": r["amount"],
        }
        for r in rows
        if "wire" in r["txn_type"] and not r["party_on_file"]
    ]
    return {
        "customer": customer(service, key),
        "accounts": accounts,
        "beneficial_owners": [],
        "monthly_summary": monthly,
        "actual_activity": actual,
        "transaction_types": breakdown("txn_type", "txn_type"),
        "counterparty_countries": breakdown("counterparty_country", "country"),
        "counterparties": counterparties,
        "unknown_parties": unknown,
        "data_period": {
            "first_txn_ts": rows[0]["txn_ts"] if rows else None,
            "last_txn_ts": rows[-1]["txn_ts"] if rows else None,
            "txn_count": len(rows),
        },
    }
