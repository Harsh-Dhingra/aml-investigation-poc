"""Load the cleaned AML demo data into the aml_demo PostgreSQL database.

Usage (from the Gates folder):
    .venv/bin/python db/load_data.py

Drops and recreates all tables from db/schema.sql, so it is safe to re-run.
"""

import csv
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "aml_demo_data_cleaned"
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def connect():
    load_dotenv(ROOT / ".env")
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "require"),
        connect_timeout=15,
    )


def read_json(name):
    with open(DATA_DIR / name) as f:
        return json.load(f)


def blank_to_none(value):
    return None if value == "" else value


def to_bool(value):
    if value in ("", None):
        return None
    return value.strip().lower() == "true"


def load_customers(cur, customers):
    customer_rows, kyc_rows, owner_rows = [], [], []
    for c in customers:
        txn_count = c["expected_monthly_transaction_count"]
        volume = c["expected_monthly_transaction_volume_usd"]
        customer_rows.append((
            c["customer_id"], c["fake_name"], c.get("business_name"), c["customer_type"],
            c.get("occupation_or_industry"), c.get("naics_code"), c.get("stated_business_purpose"),
            c.get("annual_income_or_revenue_usd"), c.get("onboarding_date"),
            c["risk_rating"], c.get("risk_rating_reason"), c.get("normal_behavior_summary"),
            txn_count["min"], txn_count["max"], volume["min"], volume["max"],
            Json(c.get("expected_cash_activity")), Json(c.get("expected_wire_activity")),
            Json(c.get("expected_transaction_types")), Json(c.get("expected_operating_states")),
            Json(c.get("expected_countries")), Json(c.get("expected_counterparty_industries")),
        ))

        k = c["kyc_profile"]
        id_check = k.get("id_verification", {})
        sanctions = k.get("sanctions_screening", {})
        is_business = "registered_address" in k
        kyc_rows.append((
            c["customer_id"], k.get("entity_type"), k.get("date_of_incorporation"),
            k.get("date_of_birth"), k.get("citizenship_country"), k.get("tax_id_masked"),
            k.get("registered_address") if is_business else k.get("residential_address"),
            "REGISTERED" if is_business else "RESIDENTIAL",
            id_check.get("document_type"), id_check.get("verified"), id_check.get("verified_date"),
            k.get("source_of_funds"), k.get("cash_intensive_business"), k.get("pep_flag", False),
            sanctions.get("status"), sanctions.get("last_screening_date"),
            k.get("kyc_last_review_date"), k.get("kyc_next_review_date"),
        ))

        for owner in k.get("beneficial_owners") or []:
            owner_rows.append((
                c["customer_id"], owner["name"], owner.get("ownership_percent"),
                owner.get("date_of_birth"), owner.get("id_document_type"), owner.get("id_verified"),
            ))

    execute_values(cur, """
        INSERT INTO customers (
            customer_id, fake_name, business_name, customer_type, occupation_or_industry,
            naics_code, stated_business_purpose, annual_income_or_revenue_usd, onboarding_date,
            risk_rating, risk_rating_reason, normal_behavior_summary,
            expected_monthly_txn_count_min, expected_monthly_txn_count_max,
            expected_monthly_volume_usd_min, expected_monthly_volume_usd_max,
            expected_cash_activity, expected_wire_activity, expected_transaction_types,
            expected_operating_states, expected_countries, expected_counterparty_industries
        ) VALUES %s""", customer_rows)
    execute_values(cur, """
        INSERT INTO kyc_profiles (
            customer_id, entity_type, date_of_incorporation, date_of_birth, citizenship_country,
            tax_id_masked, address, address_type, id_document_type, id_verified, id_verified_date,
            source_of_funds, cash_intensive_business, pep_flag, sanctions_status,
            sanctions_last_screening_date, kyc_last_review_date, kyc_next_review_date
        ) VALUES %s""", kyc_rows)
    if owner_rows:
        execute_values(cur, """
            INSERT INTO beneficial_owners (
                customer_id, name, ownership_percent, date_of_birth, id_document_type, id_verified
            ) VALUES %s""", owner_rows)
    return len(owner_rows)


def load_accounts(cur, accounts):
    account_rows, summary_rows = [], []
    for a in accounts:
        balance_range = a.get("expected_balance_range_usd") or {}
        account_rows.append((
            a["account_id"], a["customer_id"], a.get("account_type"), a.get("account_purpose"),
            a.get("currency"), a.get("open_date"), a.get("domicile_country"), a.get("domicile_state"),
            a.get("home_branch_id"), a.get("status"), a.get("ownership_type"),
            Json(a.get("authorized_signers")), Json(a.get("expected_transaction_types")),
            Json(a.get("capabilities")), balance_range.get("min"), balance_range.get("max"),
            a.get("synthetic_routing_identifier"), a.get("synthetic_masked_account_number"),
            a.get("opening_balance_usd"), a.get("opening_balance_date"),
            a.get("current_balance_usd"), a.get("current_balance_date"), a.get("last_activity_date"),
        ))
        for m in a.get("monthly_summary") or []:
            summary_rows.append((
                a["account_id"], m["month"], m.get("is_partial_month"), m.get("days_covered"),
                m.get("avg_daily_balance_usd"), m.get("month_end_balance_usd"),
                m.get("transaction_count"), m.get("total_in_usd"), m.get("total_out_usd"),
                m.get("cash_deposit_count"), m.get("cash_deposit_total_usd"),
                m.get("wire_count"), m.get("wire_total_usd"),
            ))

    execute_values(cur, """
        INSERT INTO accounts (
            account_id, customer_id, account_type, account_purpose, currency, open_date,
            domicile_country, domicile_state, home_branch_id, status, ownership_type,
            authorized_signers, expected_transaction_types, capabilities,
            expected_balance_min_usd, expected_balance_max_usd, synthetic_routing_identifier,
            synthetic_masked_account_number, opening_balance_usd, opening_balance_date,
            current_balance_usd, current_balance_date, last_activity_date
        ) VALUES %s""", account_rows)
    execute_values(cur, """
        INSERT INTO account_monthly_summary (
            account_id, month, is_partial_month, days_covered, avg_daily_balance_usd,
            month_end_balance_usd, transaction_count, total_in_usd, total_out_usd,
            cash_deposit_count, cash_deposit_total_usd, wire_count, wire_total_usd
        ) VALUES %s""", summary_rows)
    return len(summary_rows)


def load_counterparties(cur, counterparties):
    cp_rows, link_rows = [], []
    for cp in counterparties:
        amount_range = cp.get("expected_amount_range_usd") or {}
        cp_rows.append((
            cp["counterparty_id"], cp["name"], cp.get("entity_type"), cp.get("relationship"),
            cp.get("industry"), cp.get("country"), cp.get("state"), cp.get("is_known_counterparty"),
            cp.get("expected_direction"), Json(cp.get("expected_payment_methods")),
            amount_range.get("min"), amount_range.get("max"),
        ))
        for customer_id in cp.get("associated_customer_ids") or []:
            link_rows.append((customer_id, cp["counterparty_id"]))

    execute_values(cur, """
        INSERT INTO counterparties (
            counterparty_id, name, entity_type, relationship, industry, country, state,
            is_known_counterparty, expected_direction, expected_payment_methods,
            expected_amount_min_usd, expected_amount_max_usd
        ) VALUES %s""", cp_rows)
    execute_values(cur, """
        INSERT INTO customer_counterparties (customer_id, counterparty_id) VALUES %s""", link_rows)
    return len(link_rows)


def load_transactions(cur):
    with open(DATA_DIR / "transactions.csv", newline="") as f:
        rows = [(
            r["transaction_id"], r["account_id"], r["customer_id"], r["txn_ts"], r["txn_type"],
            r["direction"], r["amount"], blank_to_none(r["currency"]), to_bool(r["cash_flag"]),
            blank_to_none(r["channel"]), blank_to_none(r["branch_id"]),
            blank_to_none(r["branch_state"]), blank_to_none(r["counterparty_id"]),
            blank_to_none(r["counterparty_country"]), blank_to_none(r["depositor_id"]),
            to_bool(r["depositor_is_customer"]), blank_to_none(r["atm_country"]),
            blank_to_none(r["originator_name"]), blank_to_none(r["originator_country"]),
            blank_to_none(r["beneficiary_name"]), blank_to_none(r["purpose_field"]),
            blank_to_none(r["invoice_id"]), blank_to_none(r["check_number"]),
            to_bool(r["is_round_amount"]), blank_to_none(r["description"]),
            blank_to_none(r["balance_after"]),
        ) for r in csv.DictReader(f)]

    execute_values(cur, """
        INSERT INTO transactions (
            transaction_id, account_id, customer_id, txn_ts, txn_type, direction, amount, currency,
            cash_flag, channel, branch_id, branch_state, counterparty_id, counterparty_country,
            depositor_id, depositor_is_customer, atm_country, originator_name, originator_country,
            beneficiary_name, purpose_field, invoice_id, check_number, is_round_amount,
            description, balance_after
        ) VALUES %s""", rows, page_size=1000)
    return len(rows)


def load_policy_patterns(cur, patterns):
    rows = [(
        p["pattern_id"], p["pattern_name"], p.get("enabled_for_initial_synthesis"),
        p.get("alert_only"), p.get("detection_logic"), Json(p),
    ) for p in patterns]
    execute_values(cur, """
        INSERT INTO policy_patterns (
            pattern_id, pattern_name, enabled_for_initial_synthesis, alert_only,
            detection_logic, definition
        ) VALUES %s""", rows)
    return len(rows)


def main():
    customers = read_json("customers.json")["customers"]
    accounts = read_json("accounts.json")["accounts"]
    counterparties = read_json("counterparties.json")["counterparties"]
    patterns = read_json("policy_patterns.json")["patterns"]

    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(SCHEMA_FILE.read_text())
            owners = load_customers(cur, customers)
            summaries = load_accounts(cur, accounts)
            load_counterparties(cur, counterparties)
            txns = load_transactions(cur)
            pattern_count = load_policy_patterns(cur, patterns)
    finally:
        conn.close()

    print(f"customers:               {len(customers)}")
    print(f"kyc_profiles:            {len(customers)}")
    print(f"beneficial_owners:       {owners}")
    print(f"accounts:                {len(accounts)}")
    print(f"account_monthly_summary: {summaries}")
    print(f"counterparties:          {len(counterparties)}")
    print(f"transactions:            {txns}")
    print(f"policy_patterns:         {pattern_count}")


if __name__ == "__main__":
    main()
