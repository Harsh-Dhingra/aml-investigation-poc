import { AlertTriangle, ArrowLeft, Building2, CheckCircle2, User } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { CustomerKyc } from '../api'
import { displayName, formatDate, formatUsd, humanize } from '../format'
import { Badge, ReviewBadge, RiskBadge } from '../components/ui'
import { TABS, type ProfileException, type TabKey } from './exceptions'

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wider text-neutral-500">{label}</p>
      <p className="mt-0.5 truncate text-sm font-medium text-neutral-100">{children}</p>
    </div>
  )
}

export default function CustomerHeader({
  data, exceptions, tab, onTab,
}: {
  data: CustomerKyc
  exceptions: ProfileException[]
  tab: TabKey
  onTab: (t: TabKey) => void
}) {
  const c = data.customer
  const account = data.accounts[0]
  const high = exceptions.filter((e) => e.severity === 'HIGH').length
  const isBusiness = c.customer_type === 'BUSINESS'

  return (
    <div className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto max-w-6xl px-8 pt-4">
        <Link to="/kyc" className="inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-brand">
          <ArrowLeft className="h-3.5 w-3.5" /> All customers
        </Link>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand/15 text-brand">
              {isBusiness ? <Building2 className="h-5 w-5" /> : <User className="h-5 w-5" />}
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-bold">{displayName(c)}</h1>
              <p className="truncate text-xs text-neutral-400">
                {isBusiness ? `Owner: ${c.fake_name} · ` : ''}{c.occupation_or_industry}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <RiskBadge rating={c.risk_rating} />
            <ReviewBadge status={c.kyc_review_status} />
            <Badge tone={c.sanctions_status === 'CLEAR' ? 'green' : 'red'}>
              Sanctions: {humanize(c.sanctions_status)}
            </Badge>
            <Badge tone={c.pep_flag ? 'red' : 'green'}>{c.pep_flag == null ? 'PEP: unknown' : c.pep_flag ? 'PEP' : 'Not PEP'}</Badge>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-4 rounded-lg border border-line bg-panel px-4 py-3 md:grid-cols-6">
          <Fact label="Customer ID">{c.customer_id}</Fact>
          <Fact label="Type">{humanize(c.customer_type)}</Fact>
          <Fact label="Account">{account?.account_id ?? '—'}</Fact>
          <Fact label="Balance">{formatUsd(account?.current_balance_usd)}</Fact>
          <Fact label="Next KYC review">{formatDate(c.kyc_next_review_date)}</Fact>
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-wider text-neutral-500">Exceptions</p>
            <button
              onClick={() => onTab('profile')}
              className={`mt-0.5 inline-flex items-center gap-1.5 text-sm font-semibold ${
                exceptions.length === 0 ? 'text-emerald-400' : high > 0 ? 'text-red-400' : 'text-yellow-300'
              } hover:underline`}
            >
              {exceptions.length === 0 ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
              {exceptions.length === 0 ? 'None' : `${exceptions.length} (${high} high)`}
            </button>
          </div>
        </div>

        <nav className="mt-3 flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => onTab(t.key)}
              className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium outline-none transition-colors focus-visible:bg-brand/10 ${
                tab === t.key
                  ? 'border-brand text-brand'
                  : 'border-transparent text-neutral-400 hover:text-white'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  )
}
