import { AlertTriangle, CheckCircle2, ChevronRight, Fingerprint, Landmark, ShieldCheck, Users } from 'lucide-react'
import type { CustomerKyc } from '../api'
import { formatDate, formatNumber, formatRange, formatUsd, humanize } from '../format'
import { Badge, Field, Masked, Panel, Table, YesNo } from '../components/ui'
import type { ProfileException, TabKey } from './exceptions'

function ExceptionsBox({ exceptions, onTab }: { exceptions: ProfileException[]; onTab: (t: TabKey) => void }) {
  if (exceptions.length === 0) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-300">
        <CheckCircle2 className="h-5 w-5" />
        No profile exceptions. Activity, screening, and review status all match the KYC profile.
      </div>
    )
  }
  return (
    <Panel
      title="Profile exceptions"
      icon={<AlertTriangle className="h-4 w-4" />}
      action={<span className="text-xs text-neutral-500">Where actual data differs from the KYC profile</span>}
    >
      <ul className="divide-y divide-line">
        {exceptions.map((e, i) => (
          <li key={i}>
            <button
              onClick={() => onTab(e.tab)}
              className="group flex w-full items-start gap-3 py-2.5 text-left first:pt-0 last:pb-0"
            >
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${e.severity === 'HIGH' ? 'bg-red-400' : 'bg-yellow-300'}`} />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-white">{e.title}</span>
                  <span className="text-[11px] uppercase tracking-wider text-neutral-500">{e.area}</span>
                </span>
                <span className="mt-0.5 block text-sm text-neutral-400">{e.detail}</span>
              </span>
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-neutral-600 group-hover:text-brand" />
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

export default function ProfileTab({ data, exceptions, onTab }: {
  data: CustomerKyc
  exceptions: ProfileException[]
  onTab: (t: TabKey) => void
}) {
  const c = data.customer
  const isBusiness = c.customer_type === 'BUSINESS'

  return (
    <div className="space-y-5">
      <ExceptionsBox exceptions={exceptions} onTab={onTab} />

      <div className="grid gap-5 lg:grid-cols-3">
        <Panel title="Identity" icon={<Fingerprint className="h-4 w-4" />} className="lg:col-span-2">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3.5 sm:grid-cols-2">
            {isBusiness ? (
              <>
                <Field label="Legal name">{c.business_name}</Field>
                <Field label="Entity type">{humanize(c.entity_type)}</Field>
                <Field label="Date of incorporation">{formatDate(c.date_of_incorporation)}</Field>
                <Field label="NAICS code">{c.naics_code ?? '—'}</Field>
              </>
            ) : (
              <>
                <Field label="Full name">{c.fake_name}</Field>
                <Field label="Date of birth"><Masked value={formatDate(c.date_of_birth)} /></Field>
                <Field label="Citizenship">{c.citizenship_country ?? '—'}</Field>
                <Field label="Occupation">{c.occupation_or_industry ?? '—'}</Field>
              </>
            )}
            <Field label="Tax ID (masked)">{c.tax_id_masked ?? '—'}</Field>
            <Field label={c.address_type === 'REGISTERED' ? 'Registered address' : 'Residential address'}>
              {c.address ?? '—'}
            </Field>
            <Field label="Customer since">{formatDate(c.onboarding_date)}</Field>
            <Field label={isBusiness ? 'Annual revenue' : 'Annual income'}>
              {formatUsd(c.annual_income_or_revenue_usd)}
            </Field>
            <Field label="Source of funds">{c.source_of_funds ?? '—'}</Field>
            {isBusiness && (
              <Field label="Cash-intensive business">
                <YesNo value={c.cash_intensive_business} good={false} />
              </Field>
            )}
            {c.stated_business_purpose && (
              <div className="sm:col-span-2">
                <Field label="Stated purpose">{c.stated_business_purpose}</Field>
              </div>
            )}
            {c.risk_rating_reason && (
              <div className="sm:col-span-2">
                <Field label="Risk rating reason">{c.risk_rating_reason}</Field>
              </div>
            )}
          </dl>
        </Panel>

        <Panel title="Verification & screening" icon={<ShieldCheck className="h-4 w-4" />}>
          <dl className="space-y-3.5">
            <Field label="ID document">{humanize(c.id_document_type)}</Field>
            <Field label="ID verified">
              <span className="flex items-center gap-2">
                <YesNo value={c.id_verified} />
                <span className="text-xs text-neutral-500">{formatDate(c.id_verified_date)}</span>
              </span>
            </Field>
            <Field label="Sanctions (OFAC) screening">
              <span className="flex items-center gap-2">
                <Badge tone={c.sanctions_status === 'CLEAR' ? 'green' : 'red'}>{humanize(c.sanctions_status)}</Badge>
                <span className="text-xs text-neutral-500">{formatDate(c.sanctions_last_screening_date)}</span>
              </span>
            </Field>
            <Field label="Politically exposed person"><YesNo value={c.pep_flag} good={false} /></Field>
            <Field label="Last KYC review">{formatDate(c.kyc_last_review_date)}</Field>
          </dl>
        </Panel>
      </div>

      {isBusiness && (
        <Panel title="Beneficial owners (25% or more)" icon={<Users className="h-4 w-4" />}>
          {data.beneficial_owners.length === 0 ? (
            <p className="text-sm text-neutral-500">No beneficial owners recorded.</p>
          ) : (
            <Table head={['Name', 'Ownership', 'Date of birth', 'ID document', 'Verified']}>
              {data.beneficial_owners.map((o) => (
                <tr key={o.name}>
                  <td className="text-white">{o.name}</td>
                  <td className="text-brand-light">{formatNumber(o.ownership_percent)}%</td>
                  <td className="text-neutral-300"><Masked value={formatDate(o.date_of_birth)} /></td>
                  <td className="text-neutral-300">{humanize(o.id_document_type)}</td>
                  <td><YesNo value={o.id_verified} /></td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      )}

      {data.accounts.map((a) => (
        <Panel
          key={a.account_id}
          title={`Account ${a.account_id}`}
          icon={<Landmark className="h-4 w-4" />}
          action={<Badge tone={a.status === 'ACTIVE' ? 'green' : 'neutral'}>{humanize(a.status)}</Badge>}
        >
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3.5 md:grid-cols-4">
            <Field label="Type">{humanize(a.account_type)}</Field>
            <Field label="Purpose">{humanize(a.account_purpose)}</Field>
            <Field label="Account number">{a.synthetic_masked_account_number ?? '—'}</Field>
            <Field label="Opened">{formatDate(a.open_date)}</Field>
            <Field label="Ownership">{humanize(a.ownership_type)}</Field>
            <Field label="Branch">{a.home_branch_id ?? '—'}</Field>
            <Field label="Expected balance">
              {formatRange(
                a.expected_balance_min_usd != null
                  ? { min: a.expected_balance_min_usd, max: a.expected_balance_max_usd ?? 0 }
                  : null,
                true,
              )}
            </Field>
            <Field label="Authorized signers">
              {(a.authorized_signers ?? []).map((s) => `${s.name} (${s.role})`).join(', ') || '—'}
            </Field>
          </dl>
          {a.capabilities && (
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(a.capabilities).map(([key, allowed]) => (
                <Badge key={key} tone={allowed ? 'brand' : 'neutral'}>
                  {allowed ? '✓' : '✕'} {humanize(key.replace(/^allows_/, ''))}
                </Badge>
              ))}
            </div>
          )}
        </Panel>
      ))}
    </div>
  )
}
