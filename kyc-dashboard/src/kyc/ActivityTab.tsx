import { BarChart3, CalendarRange, Globe2, ListTree } from 'lucide-react'
import { useState } from 'react'
import type { CustomerKyc, MonthlySummary } from '../api'
import { formatNumber, formatRange, formatUsd, humanize } from '../format'
import { Badge, FitBadge, Panel, Table } from '../components/ui'
import { activityRows, compare, formatActivityRange, formatActivityValue, toRange } from './activity'

function MonthlyChart({ months }: { months: MonthlySummary[] }) {
  const max = Math.max(1, ...months.map((m) => Math.max(m.total_in_usd, m.total_out_usd)))
  return (
    <div>
      <div className="flex h-44 items-end gap-2">
        {months.map((m) => (
          <div key={m.month} className="group relative flex h-full flex-1 flex-col items-center justify-end">
            <div className="flex h-full w-full items-end justify-center gap-0.5">
              <div className="w-1/2 rounded-t bg-brand" style={{ height: `${(m.total_in_usd / max) * 100}%` }} />
              <div className="w-1/2 rounded-t bg-neutral-600" style={{ height: `${(m.total_out_usd / max) * 100}%` }} />
            </div>
            <span className={`mt-1.5 text-[10px] ${m.is_partial_month ? 'text-neutral-600' : 'text-neutral-500'}`}>
              {m.month.slice(2)}
            </span>
            <div className="pointer-events-none absolute bottom-full z-10 mb-2 hidden w-44 rounded-lg border border-line bg-black p-2 text-xs group-hover:block">
              <p className="font-semibold text-brand-light">{m.month}{m.is_partial_month ? ' (partial)' : ''}</p>
              <p className="text-neutral-300">In: {formatUsd(m.total_in_usd)}</p>
              <p className="text-neutral-300">Out: {formatUsd(m.total_out_usd)}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-4 text-xs text-neutral-400">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-brand" /> Money in</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-neutral-600" /> Money out</span>
        <span className="text-neutral-600">Faded labels = partial months</span>
      </div>
    </div>
  )
}

export default function ActivityTab({ data }: { data: CustomerKyc }) {
  const c = data.customer
  const [showMonths, setShowMonths] = useState(false)
  const rows = activityRows(data)
  const expectedCountries = new Set(c.expected_countries ?? [])
  const expectedTypes = new Set(c.expected_transaction_types ?? [])
  const cash = c.expected_cash_activity
  const wire = c.expected_wire_activity
  const cashRange = cash?.monthly_cash_deposit_total_usd
  const wireRange = wire?.monthly_wire_count

  return (
    <div className="space-y-5">
      <Panel
        title="Expected vs actual activity"
        icon={<BarChart3 className="h-4 w-4" />}
        action={
          <span className="text-xs text-neutral-500">
            Actual = average of {data.actual_activity.full_months} full months
          </span>
        }
      >
        <Table head={['Measure', 'Expected (KYC)', 'Actual avg', 'Peak month', 'Status']}>
          {rows.map((r) => (
            <tr key={r.label}>
              <td className="text-neutral-200">{r.label}</td>
              <td className="text-neutral-400">{formatActivityRange(r)}</td>
              <td className="font-medium text-white">{formatActivityValue(r.avg, r.money)}</td>
              <td className="text-neutral-300">{r.peak == null ? '—' : formatActivityValue(r.peak, r.money)}</td>
              <td><FitBadge fit={r.fit} /></td>
            </tr>
          ))}
          {data.accounts.map((a) => {
            const range = toRange(a.expected_balance_min_usd, a.expected_balance_max_usd)
            return (
              <tr key={a.account_id}>
                <td className="text-neutral-200">Current balance</td>
                <td className="text-neutral-400">{formatRange(range, true)}</td>
                <td className="font-medium text-white">{formatUsd(a.current_balance_usd, true)}</td>
                <td className="text-neutral-300">—</td>
                <td><FitBadge fit={compare(a.current_balance_usd, null, range)} /></td>
              </tr>
            )
          })}
        </Table>
        <div className="mt-4 grid gap-3 border-t border-line pt-4 text-sm sm:grid-cols-2">
          <p className="text-neutral-400">
            Expected cash: <span className="text-white">{humanize(cash?.level)}</span>
            {cashRange && <span className="text-neutral-500"> · {formatRange(cashRange, true)} / month</span>}
          </p>
          <p className="text-neutral-400">
            Expected wires: <span className="text-white">{humanize(wire?.level)}</span>
            {wireRange && <span className="text-neutral-500"> · {formatRange(wireRange)} / month</span>}
          </p>
          {c.normal_behavior_summary && (
            <p className="text-neutral-400 sm:col-span-2">
              Expected behaviour: <span className="text-neutral-300">{c.normal_behavior_summary}</span>
            </p>
          )}
        </div>
      </Panel>

      <Panel
        title="Monthly activity"
        icon={<CalendarRange className="h-4 w-4" />}
        action={
          <button onClick={() => setShowMonths((s) => !s)} className="text-xs font-medium text-brand hover:text-brand-light">
            {showMonths ? 'Hide month table' : 'Show month table'}
          </button>
        }
      >
        <MonthlyChart months={data.monthly_summary} />
        {showMonths && (
          <div className="mt-5 border-t border-line pt-4">
            <Table head={['Month', 'Txns', 'Money in', 'Money out', 'Cash deposits', 'Wires', 'Month-end balance']}>
              {data.monthly_summary.map((m) => {
                const cashFit = compare(m.cash_deposit_total_usd, null, cashRange)
                const wireFit = compare(m.wire_count, null, wireRange)
                return (
                  <tr key={m.month}>
                    <td className="text-neutral-200">
                      {m.month}
                      {m.is_partial_month && <span className="ml-1.5 text-xs text-neutral-500">partial</span>}
                    </td>
                    <td className="text-neutral-300">{formatNumber(m.transaction_count)}</td>
                    <td className="text-neutral-300">{formatUsd(m.total_in_usd)}</td>
                    <td className="text-neutral-300">{formatUsd(m.total_out_usd)}</td>
                    <td className={!m.is_partial_month && cashFit === 'ABOVE' ? 'font-medium text-red-400' : 'text-neutral-300'}>
                      {formatUsd(m.cash_deposit_total_usd)}
                      <span className="text-xs text-neutral-500"> ({m.cash_deposit_count})</span>
                    </td>
                    <td className={!m.is_partial_month && wireFit === 'ABOVE' ? 'font-medium text-red-400' : 'text-neutral-300'}>
                      {m.wire_count}
                    </td>
                    <td className="text-neutral-200">{formatUsd(m.month_end_balance_usd)}</td>
                  </tr>
                )
              })}
            </Table>
            <p className="mt-2 text-xs text-neutral-500">Red = month above the KYC-expected range.</p>
          </div>
        )}
      </Panel>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Countries" icon={<Globe2 className="h-4 w-4" />}>
          <p className="text-xs uppercase tracking-wider text-neutral-500">Expected</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(c.expected_countries ?? []).map((x) => <Badge key={x}>{x}</Badge>)}
          </div>
          <p className="mt-4 text-xs uppercase tracking-wider text-neutral-500">Actual counterparty countries</p>
          <ul className="mt-1 divide-y divide-line text-sm">
            {data.counterparty_countries.map((x) => {
              const outside = x.country !== 'UNKNOWN' && !expectedCountries.has(x.country)
              return (
                <li key={x.country} className="flex items-center justify-between py-2">
                  <span className="flex items-center gap-2">
                    <span className={outside ? 'font-semibold text-red-400' : 'text-neutral-200'}>
                      {x.country === 'UNKNOWN' ? 'No country (card / cash)' : x.country}
                    </span>
                    {outside && <Badge tone="red">Outside profile</Badge>}
                  </span>
                  <span className="text-neutral-400">
                    {formatNumber(x.txn_count)} · {formatUsd(x.total_usd, true)}
                  </span>
                </li>
              )
            })}
          </ul>
        </Panel>

        <Panel title="Transaction types" icon={<ListTree className="h-4 w-4" />}>
          <p className="text-xs uppercase tracking-wider text-neutral-500">Count · total</p>
          <ul className="mt-1 divide-y divide-line text-sm">
            {data.transaction_types.map((t) => {
              const outside = !expectedTypes.has(t.txn_type)
              return (
                <li key={t.txn_type} className="flex items-center justify-between py-2">
                  <span className="flex items-center gap-2">
                    <span className={outside ? 'font-semibold text-red-400' : 'text-neutral-200'}>
                      {humanize(t.txn_type)}
                    </span>
                    {outside && <Badge tone="red">Not expected</Badge>}
                  </span>
                  <span className="text-neutral-400">
                    {formatNumber(t.txn_count)} · {formatUsd(t.total_usd, true)}
                  </span>
                </li>
              )
            })}
          </ul>
          {(c.expected_transaction_types ?? []).filter((t) => !data.transaction_types.some((x) => x.txn_type === t)).length > 0 && (
            <p className="mt-3 text-xs text-neutral-500">
              Expected but not seen:{' '}
              {(c.expected_transaction_types ?? [])
                .filter((t) => !data.transaction_types.some((x) => x.txn_type === t))
                .map(humanize)
                .join(', ')}
            </p>
          )}
        </Panel>
      </div>
    </div>
  )
}
