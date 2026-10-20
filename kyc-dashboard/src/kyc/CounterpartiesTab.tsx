import { HelpCircle, Network } from 'lucide-react'
import type { CustomerKyc } from '../api'
import { formatDate, formatNumber, formatRange, formatUsd, humanize } from '../format'
import { Badge, Panel, Table } from '../components/ui'
import { toRange } from './activity'

export default function CounterpartiesTab({ data }: { data: CustomerKyc }) {
  const known = data.counterparties
  const unknown = data.unknown_parties
  const expectedCountries = new Set(data.customer.expected_countries ?? [])
  const knownTotal = known.reduce((s, cp) => s + cp.total_usd, 0)
  const unknownTotal = unknown.reduce((s, p) => s + p.total_usd, 0)

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ['Known counterparties', formatNumber(known.length), false],
          ['Paid via known parties', formatUsd(knownTotal, true), false],
          ['Wire parties not on file', formatNumber(unknown.length), unknown.length > 0],
          ['Wired via unknown parties', formatUsd(unknownTotal, true), unknown.length > 0],
        ].map(([label, value, alert]) => (
          <div key={label as string} className="rounded-xl border border-line bg-panel px-4 py-3">
            <p className="text-[11px] uppercase tracking-wider text-neutral-500">{label}</p>
            <p className={`mt-1 text-xl font-bold ${alert ? 'text-red-400' : 'text-white'}`}>{value}</p>
          </div>
        ))}
      </div>

      {unknown.length > 0 && (
        <Panel
          title="Wire parties not on file"
          icon={<HelpCircle className="h-4 w-4" />}
          action={<span className="text-xs text-neutral-500">Wires with parties that are not known counterparties</span>}
        >
          <Table head={['Party', 'Country', 'Direction', 'Wires', 'Total', 'First seen', 'Last seen']}>
            {unknown.map((p) => {
              const outside = p.country != null && !expectedCountries.has(p.country)
              return (
                <tr key={`${p.name}-${p.direction}`}>
                  <td className="font-medium text-white">{p.name ?? 'Unnamed party'}</td>
                  <td>
                    <span className="flex items-center gap-2">
                      <span className={outside ? 'font-semibold text-red-400' : 'text-neutral-300'}>{p.country ?? '—'}</span>
                      {outside && <Badge tone="red">Outside profile</Badge>}
                    </span>
                  </td>
                  <td className="text-neutral-300">{p.direction === 'INCOMING' ? 'Money in' : 'Money out'}</td>
                  <td className="text-neutral-300">{formatNumber(p.txn_count)}</td>
                  <td className="font-medium text-white">{formatUsd(p.total_usd)}</td>
                  <td className="whitespace-nowrap text-neutral-400">{formatDate(p.first_txn_ts.slice(0, 10))}</td>
                  <td className="whitespace-nowrap text-neutral-400">{formatDate(p.last_txn_ts.slice(0, 10))}</td>
                </tr>
              )
            })}
          </Table>
        </Panel>
      )}

      <Panel
        title="Known counterparties"
        icon={<Network className="h-4 w-4" />}
        action={<span className="text-xs text-neutral-500">From the customer's KYC file</span>}
      >
        <Table head={['Name', 'Relationship', 'Expected amount', 'Actual activity', 'Last activity']}>
          {known.map((cp) => {
            const range = toRange(cp.expected_amount_min_usd, cp.expected_amount_max_usd)
            return (
              <tr key={cp.counterparty_id}>
                <td className="min-w-48">
                  <p className="text-white">{cp.name}</p>
                  <p className="text-xs text-neutral-500">
                    {cp.counterparty_id} · {humanize(cp.industry)} · {[cp.state, cp.country].filter(Boolean).join(', ') || '—'}
                  </p>
                </td>
                <td className="text-neutral-300">
                  {humanize(cp.relationship)}
                  <p className="text-xs text-neutral-500">
                    {cp.expected_direction === 'INCOMING' ? 'Pays customer' : 'Customer pays'}
                    {cp.expected_payment_methods?.length ? ` · ${cp.expected_payment_methods.map(humanize).join(', ')}` : ''}
                  </p>
                </td>
                <td className="whitespace-nowrap text-neutral-400">{formatRange(range, true)}</td>
                <td className="whitespace-nowrap">
                  <p className="text-neutral-200">
                    {formatNumber(cp.txn_count)} txns · {formatUsd(cp.total_usd, true)}
                  </p>
                  <p className="text-xs text-neutral-500">
                    avg {formatUsd(cp.avg_amount_usd, true)} · max {formatUsd(cp.max_amount_usd, true)}
                  </p>
                  {cp.outside_range_count > 0 && (
                    <div className="mt-1"><Badge tone="amber">{cp.outside_range_count} outside range</Badge></div>
                  )}
                </td>
                <td className="whitespace-nowrap text-neutral-400">
                  {cp.last_txn_ts ? formatDate(cp.last_txn_ts.slice(0, 10)) : <Badge>No activity</Badge>}
                </td>
              </tr>
            )
          })}
        </Table>
      </Panel>
    </div>
  )
}
