import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ChevronRight, Receipt } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchTransactions, type CustomerKyc, type Transaction, type TransactionFilters, type TransactionPage } from '../api'
import { formatDate, formatNumber, formatTime, formatUsd, humanize } from '../format'
import { Badge, Panel } from '../components/ui'

const PAGE_SIZE = 50

const inputClass =
  'rounded-lg border border-line bg-panel-raised px-3 py-1.5 text-sm text-white focus:border-brand focus:outline-none [color-scheme:dark]'

function rowFlags(t: Transaction, expectedCountries: Set<string>, expectedTypes: Set<string>) {
  const flags: string[] = []
  if (t.counterparty_country && !expectedCountries.has(t.counterparty_country)) flags.push('Country')
  if (!expectedTypes.has(t.txn_type)) flags.push('Type')
  if (t.txn_type.startsWith('wire') && !t.party_on_file) flags.push('Party not on file')
  return flags
}

export default function TransactionsTab({ data }: { data: CustomerKyc }) {
  const c = data.customer
  const [filters, setFilters] = useState<TransactionFilters>({ limit: PAGE_SIZE, offset: 0 })
  const [page, setPage] = useState<TransactionPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchTransactions(c.customer_id, filters)
      .then((p) => { if (!cancelled) { setPage(p); setError(null) } })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [c.customer_id, filters])

  const update = (patch: Partial<TransactionFilters>) => setFilters((f) => ({ ...f, ...patch, offset: 0 }))
  const expectedCountries = new Set(c.expected_countries ?? [])
  const expectedTypes = new Set(c.expected_transaction_types ?? [])
  const minDate = data.data_period.first_txn_ts?.slice(0, 10)
  const maxDate = data.data_period.last_txn_ts?.slice(0, 10)
  const total = page?.total ?? 0
  const from = total === 0 ? 0 : filters.offset + 1
  const to = Math.min(filters.offset + PAGE_SIZE, total)
  const hasFilters = Boolean(filters.txn_type || filters.direction || filters.date_from || filters.date_to)

  return (
    <Panel
      title="Transactions"
      icon={<Receipt className="h-4 w-4" />}
      action={
        <span className="text-xs text-neutral-500">
          {page ? `${formatNumber(total)} transactions · ${formatUsd(page.total_usd)}` : ''}
        </span>
      }
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-neutral-500">
          Type
          <select
            className={inputClass}
            value={filters.txn_type ?? ''}
            onChange={(e) => update({ txn_type: e.target.value || undefined })}
          >
            <option value="">All types</option>
            {data.transaction_types.map((t) => (
              <option key={t.txn_type} value={t.txn_type}>
                {humanize(t.txn_type)} ({t.txn_count})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-500">
          Direction
          <select
            className={inputClass}
            value={filters.direction ?? ''}
            onChange={(e) => update({ direction: (e.target.value || undefined) as TransactionFilters['direction'] })}
          >
            <option value="">In and out</option>
            <option value="INCOMING">Money in</option>
            <option value="OUTGOING">Money out</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-500">
          From
          <input
            type="date" className={inputClass} min={minDate} max={maxDate}
            value={filters.date_from ?? ''}
            onChange={(e) => update({ date_from: e.target.value || undefined })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-500">
          To
          <input
            type="date" className={inputClass} min={minDate} max={maxDate}
            value={filters.date_to ?? ''}
            onChange={(e) => update({ date_to: e.target.value || undefined })}
          />
        </label>
        {hasFilters && (
          <button
            onClick={() => setFilters({ limit: PAGE_SIZE, offset: 0 })}
            className="pb-1.5 text-xs font-medium text-brand hover:text-brand-light"
          >
            Clear filters
          </button>
        )}
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className={`mt-4 overflow-x-auto transition-opacity ${loading ? 'opacity-50' : ''}`}>
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="whitespace-nowrap pb-2 pr-4 font-medium">Date</th>
              <th className="pb-2 pr-4 font-medium">Type</th>
              <th className="pb-2 pr-4 font-medium">Party / description</th>
              <th className="pb-2 pr-4 font-medium">Country</th>
              <th className="whitespace-nowrap pb-2 pr-4 text-right font-medium">Amount / balance</th>
              <th className="pb-2 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody>
            {page?.rows.map((t) => {
              const flags = rowFlags(t, expectedCountries, expectedTypes)
              const incoming = t.direction === 'INCOMING'
              return (
                <tr
                  key={t.transaction_id}
                  className={`border-t border-line ${flags.length ? 'bg-red-500/[0.04]' : ''}`}
                >
                  <td className="whitespace-nowrap py-2.5 pr-4">
                    <p className="text-neutral-200">{formatDate(t.txn_ts.slice(0, 10))}</p>
                    <p className="text-xs text-neutral-500">{formatTime(t.txn_ts)}</p>
                    <p className="text-xs text-neutral-600">{t.transaction_id}</p>
                  </td>
                  <td className="min-w-28 py-2.5 pr-4">
                    <span className="flex items-start gap-1.5 text-neutral-200">
                      {incoming
                        ? <ArrowDownLeft className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                        : <ArrowUpRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-500" />}
                      {humanize(t.txn_type)}
                    </span>
                    {t.cash_flag && <span className="text-xs text-yellow-300">Cash</span>}
                  </td>
                  <td className="min-w-44 py-2.5 pr-4">
                    <p className="text-neutral-200">{t.party_name ?? t.description ?? '—'}</p>
                    {t.party_name && t.description && <p className="text-xs text-neutral-500">{t.description}</p>}
                  </td>
                  <td className="py-2.5 pr-4 text-neutral-300">{t.counterparty_country ?? '—'}</td>
                  <td className="whitespace-nowrap py-2.5 pr-4 text-right">
                    <p className={`font-medium ${incoming ? 'text-emerald-400' : 'text-white'}`}>
                      {incoming ? '+' : '−'}{formatUsd(t.amount)}
                    </p>
                    <p className="text-xs text-neutral-500">Bal {formatUsd(t.balance_after)}</p>
                  </td>
                  <td className="py-2.5">
                    <div className="flex flex-col items-start gap-1">
                      {flags.map((f) => <Badge key={f} tone="red">{f}</Badge>)}
                    </div>
                  </td>
                </tr>
              )
            })}
            {page && page.rows.length === 0 && (
              <tr>
                <td colSpan={6} className="py-10 text-center text-neutral-500">No transactions match these filters.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-sm text-neutral-400">
        <span>{total > 0 ? `Showing ${formatNumber(from)}–${formatNumber(to)} of ${formatNumber(total)}` : ''}</span>
        <div className="flex gap-2">
          <button
            disabled={filters.offset === 0 || loading}
            onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, f.offset - PAGE_SIZE) }))}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 hover:border-brand hover:text-brand disabled:pointer-events-none disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" /> Newer
          </button>
          <button
            disabled={to >= total || loading}
            onClick={() => setFilters((f) => ({ ...f, offset: f.offset + PAGE_SIZE }))}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 hover:border-brand hover:text-brand disabled:pointer-events-none disabled:opacity-40"
          >
            Older <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </Panel>
  )
}
