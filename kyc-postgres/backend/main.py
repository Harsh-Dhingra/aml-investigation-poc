"""Read-only KYC API over the aml_demo PostgreSQL database.

Run from the Gates folder:
    .venv/bin/uvicorn backend.main:app --reload --port 8000
"""

import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DUE_SOON_DAYS = 60

app = FastAPI(title="KYC Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@contextmanager
def cursor():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "require"),
        connect_timeout=10,
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def review_status(next_review):
    if next_review is None:
        return "UNKNOWN"
    days_left = (next_review - date.today()).days
    if days_left < 0:
        return "OVERDUE"
    if days_left <= DUE_SOON_DAYS:
        return "DUE_SOON"
    return "CURRENT"


def with_review_status(row):
    row["kyc_review_status"] = review_status(row["kyc_next_review_date"])
    row["days_until_review"] = (
        (row["kyc_next_review_date"] - date.today()).days if row["kyc_next_review_date"] else None
    )
    return row


@app.get("/api/health")
def health():
    with cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        return cur.fetchone()


@app.get("/api/customers")
def list_customers():
    with cursor() as cur:
        cur.execute("""
            SELECT c.customer_id, c.fake_name, c.business_name, c.customer_type,
                   c.occupation_or_industry, c.risk_rating, c.onboarding_date,
                   k.pep_flag, k.sanctions_status, k.id_verified,
                   k.kyc_last_review_date, k.kyc_next_review_date,
                   a.account_id, a.status AS account_status, a.current_balance_usd
            FROM customers c
            JOIN kyc_profiles k USING (customer_id)
            LEFT JOIN accounts a USING (customer_id)
            ORDER BY c.customer_id
        """)
        return [with_review_status(r) for r in cur.fetchall()]


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: str):
    with cursor() as cur:
        cur.execute("""
            SELECT c.*, k.entity_type, k.date_of_incorporation, k.date_of_birth,
                   k.citizenship_country, k.tax_id_masked, k.address, k.address_type,
                   k.id_document_type, k.id_verified, k.id_verified_date, k.source_of_funds,
                   k.cash_intensive_business, k.pep_flag, k.sanctions_status,
                   k.sanctions_last_screening_date, k.kyc_last_review_date, k.kyc_next_review_date
            FROM customers c
            JOIN kyc_profiles k USING (customer_id)
            WHERE c.customer_id = %s
        """, (customer_id,))
        customer = cur.fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        with_review_status(customer)

        cur.execute("""
            SELECT name, ownership_percent, date_of_birth, id_document_type, id_verified
            FROM beneficial_owners WHERE customer_id = %s ORDER BY ownership_percent DESC
        """, (customer_id,))
        owners = cur.fetchall()

        cur.execute("SELECT * FROM accounts WHERE customer_id = %s ORDER BY account_id", (customer_id,))
        accounts = cur.fetchall()

        cur.execute("""
            SELECT m.* FROM account_monthly_summary m
            JOIN accounts a USING (account_id)
            WHERE a.customer_id = %s ORDER BY m.month
        """, (customer_id,))
        monthly = cur.fetchall()

        cur.execute("""
            SELECT ROUND(AVG(transaction_count), 1)                 AS avg_txn_count,
                   ROUND(AVG(GREATEST(total_in_usd, total_out_usd)), 2) AS avg_volume_usd,
                   ROUND(AVG(cash_deposit_count), 1)                AS avg_cash_deposit_count,
                   ROUND(AVG(cash_deposit_total_usd), 2)            AS avg_cash_deposit_total_usd,
                   ROUND(AVG(wire_count), 1)                        AS avg_wire_count,
                   MAX(transaction_count)                           AS max_txn_count,
                   MAX(GREATEST(total_in_usd, total_out_usd))       AS max_volume_usd,
                   MAX(cash_deposit_total_usd)                      AS max_cash_deposit_total_usd,
                   MAX(wire_count)                                  AS max_wire_count,
                   COUNT(*)                                         AS full_months
            FROM account_monthly_summary m
            JOIN accounts a USING (account_id)
            WHERE a.customer_id = %s AND NOT m.is_partial_month
        """, (customer_id,))
        actual_activity = cur.fetchone()

        cur.execute("""
            SELECT txn_type, COUNT(*) AS txn_count, SUM(amount) AS total_usd
            FROM transactions WHERE customer_id = %s
            GROUP BY txn_type ORDER BY txn_count DESC
        """, (customer_id,))
        txn_types = cur.fetchall()

        cur.execute("""
            SELECT COALESCE(NULLIF(counterparty_country, ''), 'UNKNOWN') AS country,
                   COUNT(*) AS txn_count, SUM(amount) AS total_usd
            FROM transactions WHERE customer_id = %s
            GROUP BY 1 ORDER BY txn_count DESC
        """, (customer_id,))
        countries = cur.fetchall()

        cur.execute("""
            SELECT cp.*,
                   COUNT(t.transaction_id)      AS txn_count,
                   COALESCE(SUM(t.amount), 0)   AS total_usd,
                   ROUND(AVG(t.amount), 2)      AS avg_amount_usd,
                   MAX(t.amount)                AS max_amount_usd,
                   COUNT(t.transaction_id) FILTER (
                       WHERE t.amount > cp.expected_amount_max_usd
                          OR t.amount < cp.expected_amount_min_usd
                   )                            AS outside_range_count,
                   MAX(t.txn_ts)                AS last_txn_ts
            FROM customer_counterparties cc
            JOIN counterparties cp USING (counterparty_id)
            LEFT JOIN transactions t
                   ON t.counterparty_id = cp.counterparty_id AND t.customer_id = cc.customer_id
            WHERE cc.customer_id = %s
            GROUP BY cp.counterparty_id
            ORDER BY txn_count DESC, cp.name
        """, (customer_id,))
        counterparties = cur.fetchall()

        # Card, cash and ATM activity never has a counterparty; only wires are expected to.
        cur.execute("""
            SELECT CASE WHEN direction = 'INCOMING' THEN originator_name ELSE beneficiary_name END AS name,
                   COALESCE(NULLIF(counterparty_country, ''),
                            CASE WHEN direction = 'INCOMING' THEN originator_country END) AS country,
                   direction, txn_type,
                   COUNT(*) AS txn_count, SUM(amount) AS total_usd,
                   MIN(txn_ts) AS first_txn_ts, MAX(txn_ts) AS last_txn_ts
            FROM transactions
            WHERE customer_id = %s AND counterparty_id IS NULL AND txn_type IN ('wire_in', 'wire_out')
            GROUP BY 1, 2, 3, 4
            ORDER BY total_usd DESC
        """, (customer_id,))
        unknown_parties = cur.fetchall()

        cur.execute("""
            SELECT MIN(txn_ts) AS first_txn_ts, MAX(txn_ts) AS last_txn_ts, COUNT(*) AS txn_count
            FROM transactions WHERE customer_id = %s
        """, (customer_id,))
        data_period = cur.fetchone()

    return {
        "customer": customer,
        "beneficial_owners": owners,
        "accounts": accounts,
        "monthly_summary": monthly,
        "actual_activity": actual_activity,
        "transaction_types": txn_types,
        "counterparty_countries": countries,
        "counterparties": counterparties,
        "unknown_parties": unknown_parties,
        "data_period": data_period,
    }


@app.get("/api/customers/{customer_id}/transactions")
def list_transactions(
    customer_id: str,
    txn_type: Optional[str] = None,
    direction: Optional[str] = Query(None, pattern="^(INCOMING|OUTGOING)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    filters = ["t.customer_id = %s"]
    params: list = [customer_id]
    if txn_type:
        filters.append("t.txn_type = %s")
        params.append(txn_type)
    if direction:
        filters.append("t.direction = %s")
        params.append(direction)
    if date_from:
        filters.append("t.txn_ts >= %s")
        params.append(date_from)
    if date_to:
        filters.append("t.txn_ts < %s::date + 1")
        params.append(date_to)
    where = " AND ".join(filters)

    with cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total, COALESCE(SUM(amount), 0) AS total_usd FROM transactions t WHERE {where}", params)
        totals = cur.fetchone()
        cur.execute(f"""
            SELECT t.transaction_id, t.txn_ts, t.txn_type, t.direction, t.amount, t.cash_flag,
                   t.channel, t.counterparty_id, t.counterparty_country, t.description,
                   t.balance_after, t.branch_id,
                   COALESCE(cp.name,
                            CASE WHEN t.direction = 'INCOMING'
                                 THEN NULLIF(t.originator_name, COALESCE(c.business_name, c.fake_name))
                                 ELSE NULLIF(t.beneficiary_name, COALESCE(c.business_name, c.fake_name)) END) AS party_name,
                   (cc.counterparty_id IS NOT NULL) AS party_on_file
            FROM transactions t
            JOIN customers c ON c.customer_id = t.customer_id
            LEFT JOIN counterparties cp ON cp.counterparty_id = t.counterparty_id
            LEFT JOIN customer_counterparties cc
                   ON cc.customer_id = t.customer_id AND cc.counterparty_id = t.counterparty_id
            WHERE {where}
            ORDER BY t.txn_ts DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = cur.fetchall()

    return {"total": totals["total"], "total_usd": totals["total_usd"], "rows": rows}
