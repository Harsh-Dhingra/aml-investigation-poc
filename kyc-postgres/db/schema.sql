-- KYC / AML demo schema for the aml_demo database.
-- assigned_pattern_ids and golden_labels.csv are the answer key and are not loaded.

DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS customer_counterparties CASCADE;
DROP TABLE IF EXISTS counterparties CASCADE;
DROP TABLE IF EXISTS account_monthly_summary CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;
DROP TABLE IF EXISTS beneficial_owners CASCADE;
DROP TABLE IF EXISTS kyc_profiles CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS policy_patterns CASCADE;

CREATE TABLE customers (
    customer_id                  TEXT PRIMARY KEY,
    fake_name                    TEXT NOT NULL,
    business_name                TEXT,
    customer_type                TEXT NOT NULL CHECK (customer_type IN ('BUSINESS', 'INDIVIDUAL')),
    occupation_or_industry       TEXT,
    naics_code                   TEXT,
    stated_business_purpose      TEXT,
    annual_income_or_revenue_usd NUMERIC(14, 2),
    onboarding_date              DATE,
    risk_rating                  TEXT NOT NULL CHECK (risk_rating IN ('LOW', 'MEDIUM', 'HIGH')),
    risk_rating_reason           TEXT,
    normal_behavior_summary      TEXT,
    expected_monthly_txn_count_min   INTEGER,
    expected_monthly_txn_count_max   INTEGER,
    expected_monthly_volume_usd_min  NUMERIC(14, 2),
    expected_monthly_volume_usd_max  NUMERIC(14, 2),
    expected_cash_activity           JSONB,
    expected_wire_activity           JSONB,
    expected_transaction_types       JSONB,
    expected_operating_states        JSONB,
    expected_countries               JSONB,
    expected_counterparty_industries JSONB
);

CREATE TABLE kyc_profiles (
    customer_id                   TEXT PRIMARY KEY REFERENCES customers (customer_id) ON DELETE CASCADE,
    entity_type                   TEXT,
    date_of_incorporation         DATE,
    date_of_birth                 DATE,
    citizenship_country           TEXT,
    tax_id_masked                 TEXT,
    address                       TEXT,
    address_type                  TEXT CHECK (address_type IN ('REGISTERED', 'RESIDENTIAL')),
    id_document_type              TEXT,
    id_verified                   BOOLEAN,
    id_verified_date              DATE,
    source_of_funds               TEXT,
    cash_intensive_business       BOOLEAN,
    pep_flag                      BOOLEAN NOT NULL DEFAULT FALSE,
    sanctions_status              TEXT,
    sanctions_last_screening_date DATE,
    kyc_last_review_date          DATE,
    kyc_next_review_date          DATE
);

CREATE TABLE beneficial_owners (
    owner_id          SERIAL PRIMARY KEY,
    customer_id       TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    ownership_percent NUMERIC(5, 2),
    date_of_birth     DATE,
    id_document_type  TEXT,
    id_verified       BOOLEAN
);

CREATE TABLE accounts (
    account_id                      TEXT PRIMARY KEY,
    customer_id                     TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    account_type                    TEXT,
    account_purpose                 TEXT,
    currency                        TEXT,
    open_date                       DATE,
    domicile_country                TEXT,
    domicile_state                  TEXT,
    home_branch_id                  TEXT,
    status                          TEXT,
    ownership_type                  TEXT,
    authorized_signers              JSONB,
    expected_transaction_types      JSONB,
    capabilities                    JSONB,
    expected_balance_min_usd        NUMERIC(14, 2),
    expected_balance_max_usd        NUMERIC(14, 2),
    synthetic_routing_identifier    TEXT,
    synthetic_masked_account_number TEXT,
    opening_balance_usd             NUMERIC(14, 2),
    opening_balance_date            DATE,
    current_balance_usd             NUMERIC(14, 2),
    current_balance_date            DATE,
    last_activity_date              DATE
);

CREATE TABLE account_monthly_summary (
    account_id             TEXT NOT NULL REFERENCES accounts (account_id) ON DELETE CASCADE,
    month                  TEXT NOT NULL,
    is_partial_month       BOOLEAN,
    days_covered           INTEGER,
    avg_daily_balance_usd  NUMERIC(14, 2),
    month_end_balance_usd  NUMERIC(14, 2),
    transaction_count      INTEGER,
    total_in_usd           NUMERIC(14, 2),
    total_out_usd          NUMERIC(14, 2),
    cash_deposit_count     INTEGER,
    cash_deposit_total_usd NUMERIC(14, 2),
    wire_count             INTEGER,
    wire_total_usd         NUMERIC(14, 2),
    PRIMARY KEY (account_id, month)
);

CREATE TABLE counterparties (
    counterparty_id          TEXT PRIMARY KEY,
    name                     TEXT NOT NULL,
    entity_type              TEXT,
    relationship             TEXT,
    industry                 TEXT,
    country                  TEXT,
    state                    TEXT,
    is_known_counterparty    BOOLEAN,
    expected_direction       TEXT,
    expected_payment_methods JSONB,
    expected_amount_min_usd  NUMERIC(14, 2),
    expected_amount_max_usd  NUMERIC(14, 2)
);

CREATE TABLE customer_counterparties (
    customer_id     TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    counterparty_id TEXT NOT NULL REFERENCES counterparties (counterparty_id) ON DELETE CASCADE,
    PRIMARY KEY (customer_id, counterparty_id)
);

CREATE TABLE transactions (
    transaction_id        TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts (account_id) ON DELETE CASCADE,
    customer_id           TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE CASCADE,
    txn_ts                TIMESTAMP NOT NULL,
    txn_type              TEXT NOT NULL,
    direction             TEXT NOT NULL,
    amount                NUMERIC(14, 2) NOT NULL,
    currency              TEXT,
    cash_flag             BOOLEAN,
    channel               TEXT,
    branch_id             TEXT,
    branch_state          TEXT,
    counterparty_id       TEXT REFERENCES counterparties (counterparty_id),
    counterparty_country  TEXT,
    depositor_id          TEXT,
    depositor_is_customer BOOLEAN,
    atm_country           TEXT,
    originator_name       TEXT,
    originator_country    TEXT,
    beneficiary_name      TEXT,
    purpose_field         TEXT,
    invoice_id            TEXT,
    check_number          TEXT,
    is_round_amount       BOOLEAN,
    description           TEXT,
    balance_after         NUMERIC(14, 2)
);

CREATE INDEX idx_transactions_customer_ts ON transactions (customer_id, txn_ts);
CREATE INDEX idx_transactions_counterparty ON transactions (counterparty_id);

CREATE TABLE policy_patterns (
    pattern_id                    TEXT PRIMARY KEY,
    pattern_name                  TEXT NOT NULL,
    enabled_for_initial_synthesis BOOLEAN,
    alert_only                    BOOLEAN,
    detection_logic               TEXT,
    definition                    JSONB NOT NULL
);
