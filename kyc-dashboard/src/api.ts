export type RiskRating = 'LOW' | 'MEDIUM' | 'HIGH'
export type ReviewStatus = 'CURRENT' | 'DUE_SOON' | 'OVERDUE' | 'UNKNOWN'

export interface Range {
  min: number
  max: number
}

export interface CustomerSummary {
  customer_id: string
  fake_name: string
  business_name: string | null
  customer_type: 'BUSINESS' | 'INDIVIDUAL'
  occupation_or_industry: string | null
  risk_rating: RiskRating
  onboarding_date: string | null
  pep_flag: boolean
  sanctions_status: string | null
  id_verified: boolean | null
  kyc_last_review_date: string | null
  kyc_next_review_date: string | null
  account_id: string | null
  account_status: string | null
  current_balance_usd: number | null
  kyc_review_status: ReviewStatus
  days_until_review: number | null
}

export interface CustomerDetail extends CustomerSummary {
  naics_code: string | null
  stated_business_purpose: string | null
  annual_income_or_revenue_usd: number | null
  risk_rating_reason: string | null
  normal_behavior_summary: string | null
  expected_monthly_txn_count_min: number | null
  expected_monthly_txn_count_max: number | null
  expected_monthly_volume_usd_min: number | null
  expected_monthly_volume_usd_max: number | null
  expected_cash_activity: {
    level: string
    monthly_cash_deposit_count?: Range
    monthly_cash_deposit_total_usd?: Range
    [key: string]: unknown
  } | null
  expected_wire_activity: {
    level: string
    monthly_wire_count?: Range
    [key: string]: unknown
  } | null
  expected_transaction_types: string[] | null
  expected_operating_states: string[] | null
  expected_countries: string[] | null
  expected_counterparty_industries: string[] | null
  entity_type: string | null
  date_of_incorporation: string | null
  date_of_birth: string | null
  citizenship_country: string | null
  tax_id_masked: string | null
  address: string | null
  address_type: 'REGISTERED' | 'RESIDENTIAL' | null
  id_document_type: string | null
  id_verified_date: string | null
  source_of_funds: string | null
  cash_intensive_business: boolean | null
  sanctions_last_screening_date: string | null
}

export interface BeneficialOwner {
  name: string
  ownership_percent: number | null
  date_of_birth: string | null
  id_document_type: string | null
  id_verified: boolean | null
}

export interface Account {
  account_id: string
  account_type: string | null
  account_purpose: string | null
  open_date: string | null
  status: string | null
  ownership_type: string | null
  home_branch_id: string | null
  domicile_state: string | null
  synthetic_masked_account_number: string | null
  authorized_signers: { name: string; role: string }[] | null
  capabilities: Record<string, boolean> | null
  expected_balance_min_usd: number | null
  expected_balance_max_usd: number | null
  current_balance_usd: number | null
  current_balance_date: string | null
  last_activity_date: string | null
}

export interface MonthlySummary {
  account_id: string
  month: string
  is_partial_month: boolean
  transaction_count: number
  total_in_usd: number
  total_out_usd: number
  cash_deposit_count: number
  cash_deposit_total_usd: number
  wire_count: number
  wire_total_usd: number
  month_end_balance_usd: number
}

export interface ActualActivity {
  avg_txn_count: number | null
  avg_volume_usd: number | null
  avg_cash_deposit_count: number | null
  avg_cash_deposit_total_usd: number | null
  avg_wire_count: number | null
  max_txn_count: number | null
  max_volume_usd: number | null
  max_cash_deposit_total_usd: number | null
  max_wire_count: number | null
  full_months: number
}

export interface Breakdown {
  txn_count: number
  total_usd: number
}

export interface Counterparty extends Breakdown {
  counterparty_id: string
  name: string
  entity_type: string | null
  relationship: string | null
  industry: string | null
  country: string | null
  state: string | null
  is_known_counterparty: boolean | null
  expected_direction: string | null
  expected_payment_methods: string[] | null
  expected_amount_min_usd: number | null
  expected_amount_max_usd: number | null
  avg_amount_usd: number | null
  max_amount_usd: number | null
  outside_range_count: number
  last_txn_ts: string | null
}

export interface UnknownParty extends Breakdown {
  name: string | null
  country: string | null
  direction: 'INCOMING' | 'OUTGOING'
  txn_type: string
  first_txn_ts: string
  last_txn_ts: string
}

export interface CustomerKyc {
  customer: CustomerDetail
  beneficial_owners: BeneficialOwner[]
  accounts: Account[]
  monthly_summary: MonthlySummary[]
  actual_activity: ActualActivity
  transaction_types: (Breakdown & { txn_type: string })[]
  counterparty_countries: (Breakdown & { country: string })[]
  counterparties: Counterparty[]
  unknown_parties: UnknownParty[]
  data_period: { first_txn_ts: string | null; last_txn_ts: string | null; txn_count: number }
}

export interface Transaction {
  transaction_id: string
  txn_ts: string
  txn_type: string
  direction: 'INCOMING' | 'OUTGOING'
  amount: number
  cash_flag: boolean | null
  channel: string | null
  counterparty_id: string | null
  counterparty_country: string | null
  description: string | null
  balance_after: number | null
  branch_id: string | null
  party_name: string | null
  party_on_file: boolean
}

export interface TransactionPage {
  total: number
  total_usd: number
  rows: Transaction[]
}

export interface TransactionFilters {
  txn_type?: string
  direction?: 'INCOMING' | 'OUTGOING'
  date_from?: string
  date_to?: string
  limit: number
  offset: number
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `Request failed (${res.status})`)
  }
  return res.json()
}

export const fetchCustomers = () => getJson<CustomerSummary[]>('/api/customers')
export const fetchCustomerKyc = (id: string) =>
  getJson<CustomerKyc>(`/api/customers/${encodeURIComponent(id)}`)

export function fetchTransactions(id: string, filters: TransactionFilters) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  return getJson<TransactionPage>(`/api/customers/${encodeURIComponent(id)}/transactions?${params}`)
}
