import { Eye, EyeOff } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { ReviewStatus, RiskRating } from '../api'
import type { Fit } from '../kyc/activity'

export function Panel({
  title,
  icon,
  action,
  children,
  className = '',
}: {
  title: string
  icon?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-xl border border-line bg-panel ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-brand">
          {icon}
          {title}
        </h2>
        {action}
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs uppercase tracking-wider text-neutral-500">{label}</dt>
      <dd className="mt-1 break-words text-sm text-neutral-100">{children}</dd>
    </div>
  )
}

type Tone = 'brand' | 'green' | 'red' | 'amber' | 'neutral'

const toneClasses: Record<Tone, string> = {
  brand: 'border-brand/50 bg-brand/10 text-brand-light',
  green: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400',
  red: 'border-red-500/50 bg-red-500/10 text-red-400',
  amber: 'border-yellow-400/50 bg-yellow-400/10 text-yellow-300',
  neutral: 'border-line-strong bg-panel-raised text-neutral-300',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium ${toneClasses[tone]}`}
    >
      {children}
    </span>
  )
}

const riskTone: Record<RiskRating, Tone> = { LOW: 'green', MEDIUM: 'amber', HIGH: 'red' }

export function RiskBadge({ rating }: { rating: RiskRating }) {
  return <Badge tone={riskTone[rating]}>{rating} risk</Badge>
}

const reviewLabel: Record<ReviewStatus, [string, Tone]> = {
  CURRENT: ['KYC current', 'green'],
  DUE_SOON: ['Review due soon', 'amber'],
  OVERDUE: ['Review overdue', 'red'],
  UNKNOWN: ['No review date', 'neutral'],
}

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const [label, tone] = reviewLabel[status]
  return <Badge tone={tone}>{label}</Badge>
}

export function YesNo({ value, good = true }: { value: boolean | null | undefined; good?: boolean }) {
  if (value == null) return <span className="text-neutral-500">—</span>
  const positive = value === good
  return <Badge tone={positive ? 'green' : 'red'}>{value ? 'Yes' : 'No'}</Badge>
}

export function FitBadge({ fit }: { fit: Fit }) {
  switch (fit) {
    case 'WITHIN': return <Badge tone="green">Within profile</Badge>
    case 'ABOVE': return <Badge tone="red">Above profile</Badge>
    case 'BELOW': return <Badge tone="amber">Below profile</Badge>
    case 'PEAK_ABOVE': return <Badge tone="amber">Peak month above</Badge>
    default: return <span className="text-neutral-500">—</span>
  }
}

export function Masked({ value, mask = '•••• •• ••' }: { value: ReactNode; mask?: string }) {
  const [shown, setShown] = useState(false)
  return (
    <span className="inline-flex items-center gap-2">
      <span className={shown ? '' : 'tracking-widest text-neutral-500'}>{shown ? value : mask}</span>
      <button
        type="button"
        onClick={() => setShown((s) => !s)}
        className="inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-brand"
      >
        {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        {shown ? 'Hide' : 'Show'}
      </button>
    </span>
  )
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-wider text-neutral-500">
          <tr>
            {head.map((h, i) => (
              <th key={i} className="whitespace-nowrap pb-2 pr-4 font-medium last:pr-0">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-t [&>tr]:border-line [&_td]:py-2.5 [&_td]:pr-4 [&_td:last-child]:pr-0">
          {children}
        </tbody>
      </table>
    </div>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center gap-3 text-neutral-400">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brand border-t-transparent" />
      {label}
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-md rounded-xl border border-red-500/40 bg-red-500/5 p-6 text-center">
        <p className="font-semibold text-red-400">Couldn't load data</p>
        <p className="mt-2 text-sm text-neutral-400">{message}</p>
        <p className="mt-3 text-xs text-neutral-500">
          Check that the API is running on port 8000 and the AWS database is started.
        </p>
      </div>
    </div>
  )
}
