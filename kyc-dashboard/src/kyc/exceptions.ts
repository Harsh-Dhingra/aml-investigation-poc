import type { CustomerKyc } from '../api'
import { formatDate, formatNumber, formatRange, formatUsd, humanize } from '../format'
import {
  REVIEW_YEARS, activityRows, compare, formatActivityRange, formatActivityValue, outsideCountries,
  toRange, unexpectedTxnTypes, yearsBetween,
} from './activity'

export type Severity = 'HIGH' | 'MEDIUM'
export type TabKey = 'profile' | 'activity' | 'transactions' | 'counterparties' | 'history'

export const TABS: { key: TabKey; label: string }[] = [
  { key: 'profile', label: 'Profile' },
  { key: 'activity', label: 'Activity' },
  { key: 'transactions', label: 'Transactions' },
  { key: 'counterparties', label: 'Counterparties' },
  { key: 'history', label: 'Review history' },
]

export interface ProfileException {
  severity: Severity
  area: string
  title: string
  detail: string
  tab: TabKey
}

export function profileExceptions(data: CustomerKyc): ProfileException[] {
  const c = data.customer
  const out: ProfileException[] = []

  if (c.sanctions_status && c.sanctions_status !== 'CLEAR') {
    out.push({ severity: 'HIGH', area: 'Screening', tab: 'profile',
      title: `Sanctions screening: ${humanize(c.sanctions_status)}`,
      detail: `Last screened ${formatDate(c.sanctions_last_screening_date)}.` })
  }
  if (c.pep_flag) {
    out.push({ severity: 'HIGH', area: 'Screening', tab: 'profile',
      title: 'Politically exposed person', detail: 'Enhanced due diligence applies.' })
  }
  if (c.id_verified === false) {
    out.push({ severity: 'HIGH', area: 'Identity', tab: 'profile',
      title: 'ID not verified', detail: `${humanize(c.id_document_type)} has not been verified.` })
  }
  const unverifiedOwners = data.beneficial_owners.filter((o) => o.id_verified === false)
  if (unverifiedOwners.length) {
    out.push({ severity: 'HIGH', area: 'Identity', tab: 'profile',
      title: 'Beneficial owner ID not verified',
      detail: unverifiedOwners.map((o) => o.name).join(', ') })
  }

  if (c.kyc_review_status === 'OVERDUE') {
    out.push({ severity: 'HIGH', area: 'KYC review', tab: 'history',
      title: 'KYC review overdue',
      detail: `Was due ${formatDate(c.kyc_next_review_date)} (${Math.abs(c.days_until_review ?? 0)} days ago).` })
  } else if (c.kyc_review_status === 'DUE_SOON') {
    out.push({ severity: 'MEDIUM', area: 'KYC review', tab: 'history',
      title: 'KYC review due soon',
      detail: `Due ${formatDate(c.kyc_next_review_date)} (in ${c.days_until_review} days).` })
  }
  const interval = yearsBetween(c.kyc_last_review_date, c.kyc_next_review_date)
  const required = REVIEW_YEARS[c.risk_rating]
  if (interval != null && interval > required + 0.1) {
    out.push({ severity: 'MEDIUM', area: 'KYC review', tab: 'history',
      title: 'Review cycle longer than policy',
      detail: `Next review is ${interval} years after the last one; ${c.risk_rating.toLowerCase()} risk requires every ${required} year${required > 1 ? 's' : ''}.` })
  }

  const fitText = { ABOVE: 'above profile', BELOW: 'below profile', PEAK_ABOVE: 'peak month above profile' }
  for (const row of activityRows(data)) {
    if (row.fit === 'WITHIN' || row.fit === 'NONE') continue
    const peakPart = row.peak != null ? `, peak month ${formatActivityValue(row.peak, row.money)}` : ''
    out.push({
      severity: row.fit === 'ABOVE' ? 'HIGH' : 'MEDIUM',
      area: 'Activity', tab: 'activity',
      title: `${row.label}: ${fitText[row.fit]}`,
      detail: `Average ${formatActivityValue(row.avg, row.money)}${peakPart} vs expected ${formatActivityRange(row)}.`,
    })
  }

  for (const a of data.accounts) {
    const range = toRange(a.expected_balance_min_usd, a.expected_balance_max_usd)
    const fit = compare(a.current_balance_usd, null, range)
    if (fit === 'ABOVE' || fit === 'BELOW') {
      out.push({ severity: fit === 'ABOVE' ? 'HIGH' : 'MEDIUM', area: 'Account', tab: 'activity',
        title: `Balance ${fit === 'ABOVE' ? 'above' : 'below'} expected range`,
        detail: `${a.account_id}: ${formatUsd(a.current_balance_usd)} vs expected ${formatRange(range, true)}.` })
    }
  }

  const countries = outsideCountries(data)
  if (countries.length) {
    const total = countries.reduce((s, x) => s + x.total_usd, 0)
    const count = countries.reduce((s, x) => s + x.txn_count, 0)
    out.push({ severity: 'HIGH', area: 'Geography', tab: 'activity',
      title: `Activity in ${countries.length} countr${countries.length > 1 ? 'ies' : 'y'} outside profile`,
      detail: `${countries.map((x) => x.country).join(', ')}: ${formatNumber(count)} transactions, ${formatUsd(total, true)}.` })
  }

  for (const t of unexpectedTxnTypes(data)) {
    out.push({ severity: 'MEDIUM', area: 'Activity', tab: 'transactions',
      title: `Unexpected transaction type: ${humanize(t.txn_type)}`,
      detail: `${formatNumber(t.txn_count)} transactions, ${formatUsd(t.total_usd, true)}. Not in the KYC profile.` })
  }

  if (data.unknown_parties.length) {
    const total = data.unknown_parties.reduce((s, x) => s + x.total_usd, 0)
    const count = data.unknown_parties.reduce((s, x) => s + x.txn_count, 0)
    out.push({ severity: 'HIGH', area: 'Counterparties', tab: 'counterparties',
      title: `Wires with ${data.unknown_parties.length} part${data.unknown_parties.length > 1 ? 'ies' : 'y'} not on file`,
      detail: `${formatNumber(count)} wires, ${formatUsd(total, true)} with parties that are not known counterparties.` })
  }

  const offRange = data.counterparties.filter((cp) => cp.outside_range_count > 0)
  if (offRange.length) {
    out.push({ severity: 'MEDIUM', area: 'Counterparties', tab: 'counterparties',
      title: 'Amounts outside counterparty expectations',
      detail: offRange.map((cp) => `${cp.name} (${cp.outside_range_count} of ${cp.txn_count})`).join('; ') + '.' })
  }

  return out.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'HIGH' ? -1 : 1))
}
