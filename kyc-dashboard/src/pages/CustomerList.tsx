import { AlertTriangle, ChevronRight, ShieldAlert, Users, CalendarClock } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchCustomers, type CustomerSummary, type ReviewStatus, type RiskRating } from '../api'
import { displayName, formatDate, formatUsd, humanize } from '../format'
import { ErrorState, ReviewBadge, RiskBadge, Spinner } from '../components/ui'

type RiskFilter = 'ALL' | RiskRating
type ReviewFilter = 'ALL' | ReviewStatus

function StatCard({ label, value, icon, accent = false }: {
  label: string
  value: number
  icon: ReactNode
  accent?: boolean
}) {
  return (
    <div className="rounded-xl border border-line bg-panel p-5">
      <div className="flex items-center justify-between text-neutral-400">
        <span className="text-xs uppercase tracking-wider">{label}</span>
        {icon}
      </div>
      <p className={`mt-3 text-3xl font-bold ${accent && value > 0 ? 'text-brand' : 'text-white'}`}>
        {value}
      </p>
    </div>
  )
}

function FilterGroup<T extends string>({ label, options, value, onChange }: {
  label: string
  options: [T, string][]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs uppercase tracking-wider text-neutral-500">{label}</span>
      <div className="flex rounded-lg border border-line bg-panel p-0.5">
        {options.map(([key, text]) => (
          <button
            key={key}
            onClick={() => onChange(key)}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              value === key ? 'bg-brand text-black' : 'text-neutral-400 hover:text-white'
            }`}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function CustomerList() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<CustomerSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [risk, setRisk] = useState<RiskFilter>('ALL')
  const [review, setReview] = useState<ReviewFilter>('ALL')

  useEffect(() => {
    fetchCustomers().then(setCustomers).catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <ErrorState message={error} />
  if (!customers) return <Spinner label="Loading customers..." />

  const rows = customers.filter(
    (c) => (risk === 'ALL' || c.risk_rating === risk) && (review === 'ALL' || c.kyc_review_status === review),
  )
  const needsReview = customers.filter((c) => c.kyc_review_status !== 'CURRENT').length
  const screeningHits = customers.filter((c) => c.pep_flag || c.sanctions_status !== 'CLEAR').length

  return (
    <div className="mx-auto max-w-6xl p-8">
      <h1 className="text-2xl font-bold">
        Customer <span className="text-brand">KYC</span> overview
      </h1>
      <p className="mt-1 text-sm text-neutral-400">
        Know-your-customer profiles, risk ratings, and review schedule for every customer.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Customers" value={customers.length} icon={<Users className="h-4 w-4" />} />
        <StatCard
          label="High risk"
          value={customers.filter((c) => c.risk_rating === 'HIGH').length}
          icon={<AlertTriangle className="h-4 w-4" />}
          accent
        />
        <StatCard
          label="Review due / overdue"
          value={needsReview}
          icon={<CalendarClock className="h-4 w-4" />}
          accent
        />
        <StatCard
          label="PEP / sanctions hits"
          value={screeningHits}
          icon={<ShieldAlert className="h-4 w-4" />}
          accent
        />
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-6">
        <FilterGroup<RiskFilter>
          label="Risk"
          value={risk}
          onChange={setRisk}
          options={[['ALL', 'All'], ['HIGH', 'High'], ['MEDIUM', 'Medium'], ['LOW', 'Low']]}
        />
        <FilterGroup<ReviewFilter>
          label="KYC review"
          value={review}
          onChange={setReview}
          options={[['ALL', 'All'], ['CURRENT', 'Current'], ['DUE_SOON', 'Due soon'], ['OVERDUE', 'Overdue']]}
        />
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-panel">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-wider text-neutral-500">
            <tr>
              <th className="px-5 py-3 font-medium">Customer</th>
              <th className="px-5 py-3 font-medium">Type</th>
              <th className="px-5 py-3 font-medium">Risk</th>
              <th className="px-5 py-3 font-medium">Screening</th>
              <th className="px-5 py-3 font-medium">Next review</th>
              <th className="px-5 py-3 font-medium text-right">Balance</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr
                key={c.customer_id}
                onClick={() => navigate(`/kyc/${c.customer_id}`)}
                className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-raised"
              >
                <td className="px-5 py-4">
                  <p className="font-medium text-white">{displayName(c)}</p>
                  <p className="text-xs text-neutral-500">
                    {c.customer_id} · {c.business_name ? c.fake_name : c.occupation_or_industry}
                  </p>
                </td>
                <td className="px-5 py-4 text-neutral-300">{humanize(c.customer_type)}</td>
                <td className="px-5 py-4"><RiskBadge rating={c.risk_rating} /></td>
                <td className="px-5 py-4 text-neutral-300">
                  {c.pep_flag ? 'PEP · ' : ''}
                  {humanize(c.sanctions_status)}
                </td>
                <td className="px-5 py-4">
                  <p className="text-neutral-200">{formatDate(c.kyc_next_review_date)}</p>
                  <div className="mt-1"><ReviewBadge status={c.kyc_review_status} /></div>
                </td>
                <td className="px-5 py-4 text-right text-neutral-200">{formatUsd(c.current_balance_usd)}</td>
                <td className="px-3 py-4 text-neutral-600"><ChevronRight className="h-4 w-4" /></td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-5 py-10 text-center text-neutral-500">
                  No customers match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
