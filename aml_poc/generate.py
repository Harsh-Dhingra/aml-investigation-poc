"""Reproducible synthetic future stream. Only this preparation step reads labels
to resample normal examples; the runtime engine never reads an answer key.
"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate(data_dir: Path, seed=42):
    rng = random.Random(seed)
    with (data_dir / "transactions.csv").open() as f:
        reader = csv.DictReader(f)
        historical, fields = list(reader), reader.fieldnames
    with (data_dir / "golden_labels.csv").open() as f:
        normal_ids = {r["transaction_id"] for r in csv.DictReader(f) if r["label"] == "NORMAL"}
    normal = [r for r in historical if r["transaction_id"] in normal_ids]
    start = datetime.fromisoformat(max(r["txn_ts"] for r in historical)).replace(
        hour=0, minute=0, second=0
    ) + timedelta(days=1)
    rows, annotations = [], {}
    for index in range(954):
        original = rng.choice(normal)
        row = dict(original)
        stamp = start + timedelta(seconds=rng.randrange(60 * 86400))
        # Preserve the planted funnel's policy-required majority. Schedule local cash
        # receipts later in the extension rather than diluting it below 50 percent.
        if (
            original["customer_id"] == "C002"
            and original["cash_flag"] == "true"
            and stamp < start + timedelta(days=19)
        ):
            stamp += timedelta(days=30)
        row.update(transaction_id=f"STR-N-{index + 1:04}", txn_ts=stamp.isoformat())
        if row.get("invoice_id"):
            row["invoice_id"] = f"INV-STREAM-{index + 1:04}"
        rows.append(row)
        annotations[row["transaction_id"]] = ("NORMAL", "", "", "Resampled from normal historical activity")

    def plant(customer, day, amount, txn_type, pattern, scenario, **updates):
        templates = [r for r in historical if r["customer_id"] == customer and r["txn_type"] == txn_type]
        template = templates[0] if templates else next(r for r in historical if r["customer_id"] == customer)
        row = {key: "" for key in fields}
        row.update(template)
        txn_id = f"STR-P-{sum(k.startswith('STR-P') for k in annotations) + 1:03}"
        row.update(
            transaction_id=txn_id,
            customer_id=customer,
            account_id=f"ACC-{customer}-01",
            txn_ts=(start + timedelta(days=day, hours=12)).isoformat(),
            amount=f"{amount:.2f}",
            txn_type=txn_type,
            direction="INCOMING" if txn_type in {"cash_deposit", "wire_in"} else "OUTGOING",
            cash_flag=str(txn_type == "cash_deposit").lower(),
            is_round_amount=str(amount % 1000 == 0).lower(),
            description="Synthetic demonstration transaction",
            invoice_id="",
            purpose_field="",
        )
        row.update(updates)
        rows.append(row)
        annotations[txn_id] = (
            "SUSPICIOUS",
            pattern,
            scenario,
            "Planted synthetic review signal; not confirmed laundering",
        )

    for day in range(4, 9):
        plant(
            "C001",
            day,
            9100 + day * 11,
            "cash_deposit",
            "TM-01",
            "STREAM-C001-01",
            branch_state="CA",
            branch_id="BR-CA-01",
        )
    for index in range(14):
        plant(
            "C002",
            13 + index / 3,
            3200 + index * 20,
            "cash_deposit",
            "TM-03",
            "STREAM-C002-01",
            branch_state=["TX", "MN", "IN"][index % 3],
            branch_id=f"BR-STREAM-{index % 3}",
            depositor_id=f"DEP-STREAM-{index % 4}",
        )
    for index, (day, amount) in enumerate([(15, 19000), (17, 19000), (18, 6000)]):
        plant("C002", day, amount, "wire_out", "TM-04", "STREAM-C002-01", purpose_field="Supplier payment")
    for index in range(2):
        plant(
            "C003",
            22 + index * 5,
            12500 + index * 1000,
            "wire_in",
            "TM-07",
            "STREAM-C003-01",
            purpose_field="Consulting services",
        )
        plant(
            "C003",
            23 + index * 5,
            12300 + index * 1000,
            "wire_out",
            "TM-07",
            "STREAM-C003-01",
            purpose_field="Payment",
        )
    for index in range(9):
        plant(
            "C005",
            4 + index * 2,
            8000 + index * 70,
            "wire_out",
            "TM-08",
            "STREAM-C005-01",
            purpose_field="Investment funding",
        )
    for index in range(11):
        plant(
            "C004",
            31 + index * 2,
            50000 + (index % 4) * 5000,
            "wire_out",
            "TM-09",
            "STREAM-C004-01",
            counterparty_country="CN",
            counterparty_id="CP-C004-001",
        )
    rows.sort(key=lambda r: (r["txn_ts"], r["transaction_id"]))
    with (data_dir / "stream_transactions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (data_dir / "stream_labels.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction_id", "customer_id", "label", "pattern_id", "scenario_id", "reason"])
        for row in rows:
            writer.writerow([row["transaction_id"], row["customer_id"], *annotations[row["transaction_id"]]])
    manifest = {
        "seed": seed,
        "rows": len(rows),
        "normal": 954,
        "planted": 46,
        "episodes": 5,
        "start": rows[0]["txn_ts"],
        "end": rows[-1]["txn_ts"],
        "note": "Synthetic resampled extension. Labels are held out from runtime. UTC demo event clock.",
    }
    (data_dir / "stream_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
