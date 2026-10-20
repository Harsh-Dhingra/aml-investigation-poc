import { CalendarClock, History } from 'lucide-react'
import type { CustomerKyc } from '../api'
import { formatDate, humanize } from '../format'
import { Badge, Field, Panel, ReviewBadge } from '../components/ui'
import { REVIEW_YEARS, yearsBetween } from './activity'

interface Event {
  date: string
  title: string
  detail?: string
  kind: 'past' | 'today' | 'future'
}

function todayIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function HistoryTab({ data }: { data: CustomerKyc }) {
  const c = data.customer
  const today = todayIso()
  const isBusiness = c.customer_type === 'BUSINESS'
  const interval = yearsBetween(c.kyc_last_review_date, c.kyc_next_review_date)
  const required = REVIEW_YEARS[c.risk_rating]

  const raw: (Omit<Event, 'kind'> | null)[] = [
    isBusiness && c.date_of_incorporation
      ? { date: c.date_of_incorporation, title: 'Business incorporated', detail: humanize(c.entity_type) }
      : null,
    c.onboarding_date ? { date: c.onboarding_date, title: 'Customer onboarded' } : null,
    c.id_verified_date
      ? { date: c.id_verified_date, title: 'Identity verified', detail: humanize(c.id_document_type) }
      : null,
    ...data.accounts.map((a) =>
      a.open_date ? { date: a.open_date, title: `Account ${a.account_id} opened`, detail: humanize(a.account_type) } : null,
    ),
    data.data_period.first_txn_ts
      ? { date: data.data_period.first_txn_ts.slice(0, 10), title: 'Monitoring data starts', detail: `${data.data_period.txn_count.toLocaleString()} transactions on file` }
      : null,
    c.kyc_last_review_date
      ? { date: c.kyc_last_review_date, title: 'Periodic KYC review completed' }
      : null,
    c.sanctions_last_screening_date
      ? { date: c.sanctions_last_screening_date, title: 'Sanctions & PEP screening', detail: `Result: ${humanize(c.sanctions_status)}${c.pep_flag ? ' · PEP' : ''}` }
      : null,
    data.data_period.last_txn_ts
      ? { date: data.data_period.last_txn_ts.slice(0, 10), title: 'Latest transaction' }
      : null,
    { date: today, title: 'Today' },
    c.kyc_next_review_date
      ? { date: c.kyc_next_review_date, title: 'Next KYC review due', detail: `${required}-year cycle for ${c.risk_rating.toLowerCase()} risk` }
      : null,
  ]

  const events: Event[] = raw
    .filter((e): e is Omit<Event, 'kind'> => e !== null)
    .map((e): Event => ({ ...e, kind: e.title === 'Today' ? 'today' : e.date > today ? 'future' : 'past' }))
    .sort((a, b) => a.date.localeCompare(b.date) || (a.kind === 'today' ? 1 : -1))

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Panel title="KYC timeline" icon={<History className="h-4 w-4" />} className="lg:col-span-2">
        <ol className="relative ml-2 border-l border-line">
          {events.map((e, i) => (
            <li key={i} className="relative pb-5 pl-6 last:pb-0">
              <span
                className={`absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full ${
                  e.kind === 'today'
                    ? 'bg-white ring-4 ring-white/10'
                    : e.kind === 'future'
                      ? 'border-2 border-brand bg-black'
                      : 'bg-brand'
                }`}
              />
              {e.kind === 'today' ? (
                <p className="text-xs font-semibold uppercase tracking-wider text-white">
                  Today · {formatDate(e.date)}
                </p>
              ) : (
                <>
                  <p className="text-xs text-neutral-500">{formatDate(e.date)}</p>
                  <p className={`text-sm font-medium ${e.kind === 'future' ? 'text-brand-light' : 'text-white'}`}>
                    {e.title}
                  </p>
                  {e.detail && <p className="text-sm text-neutral-400">{e.detail}</p>}
                </>
              )}
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Review policy" icon={<CalendarClock className="h-4 w-4" />}>
        <dl className="space-y-3.5">
          <Field label="Status"><ReviewBadge status={c.kyc_review_status} /></Field>
          <Field label="Risk rating">{c.risk_rating}</Field>
          <Field label="Required review cycle">Every {required} year{required > 1 ? 's' : ''}</Field>
          <Field label="Scheduled cycle">
            <span className="flex flex-wrap items-center gap-2">
              {interval != null ? `${interval} year${interval === 1 ? '' : 's'}` : '—'}
              {interval != null && interval > required + 0.1 && <Badge tone="red">Longer than policy</Badge>}
              {interval != null && interval <= required + 0.1 && <Badge tone="green">Matches policy</Badge>}
            </span>
          </Field>
          <Field label="Days until next review">
            {c.days_until_review == null
              ? '—'
              : c.days_until_review >= 0
                ? `${c.days_until_review} days`
                : `${Math.abs(c.days_until_review)} days overdue`}
          </Field>
        </dl>
        <div className="mt-4 border-t border-line pt-3 text-xs text-neutral-500">
          <p className="mb-1.5 font-medium text-neutral-400">Policy (demo setting)</p>
          <p>High risk: every 1 year</p>
          <p>Medium risk: every 2 years</p>
          <p>Low risk: every 3 years</p>
        </div>
      </Panel>
    </div>
  )
}
