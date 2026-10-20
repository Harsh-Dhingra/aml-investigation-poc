import type { CustomerKyc, Range, RiskRating } from '../api'
import { formatNumber, formatRange, formatUsd } from '../format'

export type Fit = 'WITHIN' | 'ABOVE' | 'BELOW' | 'PEAK_ABOVE' | 'NONE'

export const REVIEW_YEARS: Record<RiskRating, number> = { HIGH: 1, MEDIUM: 2, LOW: 3 }

export function compare(avg: number | null, peak: number | null, range: Range | null | undefined): Fit {
  if (avg == null || !range) return 'NONE'
  if (avg > range.max) return 'ABOVE'
  if (avg < range.min) return 'BELOW'
  if (peak != null && peak > range.max) return 'PEAK_ABOVE'
  return 'WITHIN'
}

export function toRange(min: number | null | undefined, max: number | null | undefined): Range | null {
  return min == null || max == null ? null : { min, max }
}

export function yearsBetween(from: string | null, to: string | null) {
  if (!from || !to) return null
  const ms = new Date(to).getTime() - new Date(from).getTime()
  return Math.round((ms / (365.25 * 24 * 3600 * 1000)) * 10) / 10
}

export interface ActivityRow {
  label: string
  range: Range | null
  money: boolean
  avg: number | null
  peak: number | null
  fit: Fit
}

export function activityRows({ customer: c, actual_activity: a }: CustomerKyc): ActivityRow[] {
  const row = (label: string, range: Range | null | undefined, money: boolean, avg: number | null, peak: number | null): ActivityRow => ({
    label,
    range: range ?? null,
    money,
    avg,
    peak,
    fit: compare(avg, peak, range),
  })
  return [
    row('Transactions per month',
      toRange(c.expected_monthly_txn_count_min, c.expected_monthly_txn_count_max), false,
      a.avg_txn_count, a.max_txn_count),
    row('Monthly volume (larger of in / out)',
      toRange(c.expected_monthly_volume_usd_min, c.expected_monthly_volume_usd_max), true,
      a.avg_volume_usd, a.max_volume_usd),
    row('Cash deposits per month',
      c.expected_cash_activity?.monthly_cash_deposit_count, false,
      a.avg_cash_deposit_count, null),
    row('Cash deposit total per month',
      c.expected_cash_activity?.monthly_cash_deposit_total_usd, true,
      a.avg_cash_deposit_total_usd, a.max_cash_deposit_total_usd),
    row('Wires per month',
      c.expected_wire_activity?.monthly_wire_count, false,
      a.avg_wire_count, a.max_wire_count),
  ]
}

export function formatActivityValue(value: number | null, money: boolean) {
  return money ? formatUsd(value, true) : formatNumber(value, 1)
}

export function formatActivityRange(row: ActivityRow) {
  return formatRange(row.range, row.money)
}

export function outsideCountries(data: CustomerKyc) {
  const expected = new Set(data.customer.expected_countries ?? [])
  return data.counterparty_countries.filter((x) => x.country !== 'UNKNOWN' && !expected.has(x.country))
}

export function unexpectedTxnTypes(data: CustomerKyc) {
  const expected = new Set(data.customer.expected_transaction_types ?? [])
  return data.transaction_types.filter((t) => !expected.has(t.txn_type))
}
