"""Customer KYC panels backed by operational records, independent of reports."""

import pandas as pd
import streamlit as st

from .ui_design import detail_rows, note, section_heading


def display(value):
    if value is None or value == "":
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{value:,}"
    if isinstance(value, dict):
        if "min" in value and "max" in value:
            return f"{value['min']:,} – {value['max']:,}"
        return "; ".join(f"{k.replace('_', ' ').title()}: {display(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(display(v) for v in value) or "Not recorded"
    return str(value).replace("_", " ")


def fields(record, mapping):
    detail_rows([(label, display(record.get(key))) for label, key in mapping])


def render_kyc(data):
    c = data["customer"]
    st.caption(
        "Customer KYC record · Synthetic demonstration data · Screening fields show recorded data, not a new screening check."
    )
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        section_heading("Identity & business profile")
        fields(
            c,
            [
                ("Customer reference", "customer_id"),
                ("Customer type", "customer_type"),
                ("Legal business name", "business_name")
                if c.get("customer_type") == "BUSINESS"
                else ("Full name", "fake_name"),
                ("Occupation / industry", "occupation_or_industry"),
                ("Customer since", "onboarding_date"),
                ("Annual income / revenue (USD)", "annual_income_or_revenue_usd"),
                ("Source of funds", "source_of_funds"),
                ("Stated purpose", "stated_business_purpose"),
            ],
        )
    with right:
        section_heading("Verification & screening")
        fields(
            c,
            [
                ("Customer risk rating", "risk_rating"),
                ("Risk rating reason", "risk_rating_reason"),
                ("Identity verified", "id_verified"),
                ("Sanctions status", "sanctions_status"),
                ("Politically exposed person", "pep_flag"),
                ("Last KYC review", "kyc_last_review_date"),
                ("Next KYC review", "kyc_next_review_date"),
            ],
        )
    section_heading("Expected account activity", "Declared customer profile")
    note("NORMAL BEHAVIOR", c.get("normal_behavior_summary", "Not recorded"))
    left, right = st.columns(2)
    with left:
        fields(
            c,
            [
                ("Monthly transactions", "expected_monthly_transaction_count"),
                ("Monthly volume (USD)", "expected_monthly_transaction_volume_usd"),
                ("Operating states", "expected_operating_states"),
                ("Countries", "expected_countries"),
            ],
        )
    with right:
        fields(c, [("Cash activity", "expected_cash_activity"), ("Wire activity", "expected_wire_activity")])
    for account in data["accounts"]:
        section_heading(f"Account · {account['account_id']}", account.get("status", ""))
        left, right = st.columns(2)
        with left:
            fields(
                account,
                [
                    ("Account type", "account_type"),
                    ("Purpose", "account_purpose"),
                    ("Account number", "synthetic_masked_account_number"),
                    ("Opened", "open_date"),
                ],
            )
        with right:
            fields(
                account,
                [
                    ("Ownership", "ownership_type"),
                    ("Branch", "home_branch_id"),
                    ("Expected balance (USD)", "expected_balance_range_usd"),
                    ("Authorized signers", "authorized_signers"),
                ],
            )
    if c.get("customer_type") == "BUSINESS":
        with st.expander("Beneficial ownership"):
            owners = c.get("beneficial_owners", [])
            if owners:
                st.dataframe(pd.DataFrame(owners), hide_index=True, width="stretch")
            else:
                st.caption(
                    "Beneficial ownership records are not supplied in this dataset. Account signers are shown separately."
                )
    with st.expander(f"Known counterparties ({len(data['counterparties'])})"):
        if data["counterparties"]:
            frame = pd.DataFrame(data["counterparties"])
            frame = frame.drop(columns=["associated_customer_ids"], errors="ignore")
            frame.columns = [key.replace("_", " ").title() for key in frame.columns]
            st.dataframe(frame, hide_index=True, width="stretch")
        else:
            st.caption("No counterparties recorded.")
