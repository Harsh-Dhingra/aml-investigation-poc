import { Building2, LayoutGrid, Search, ShieldCheck, User } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { fetchCustomers, type CustomerSummary } from '../api'
import { displayName } from '../format'

const riskDot = { LOW: 'bg-emerald-400', MEDIUM: 'bg-yellow-300', HIGH: 'bg-red-400' }

export default function Layout() {
  const [customers, setCustomers] = useState<CustomerSummary[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    fetchCustomers().then(setCustomers).catch(() => setCustomers([]))
  }, [])

  const q = query.trim().toLowerCase()
  const filtered = customers.filter(
    (c) =>
      !q ||
      c.customer_id.toLowerCase().includes(q) ||
      c.fake_name.toLowerCase().includes(q) ||
      (c.business_name ?? '').toLowerCase().includes(q),
  )

  return (
    <div className="flex h-full">
      <aside className="flex w-72 shrink-0 flex-col border-r border-line bg-black">
        <div className="flex items-center gap-2 px-5 py-5">
          <ShieldCheck className="h-6 w-6 text-brand" />
          <span className="text-lg font-bold">KYC Dashboard</span>
        </div>

        <div className="px-4">
          <NavLink
            to="/kyc"
            end
            className={({ isActive }) =>
              `flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${
                isActive ? 'bg-brand text-black' : 'bg-brand/90 text-black hover:bg-brand-light'
              }`
            }
          >
            <LayoutGrid className="h-4 w-4" />
            All customers
          </NavLink>
        </div>

        <p className="mt-7 px-5 text-xs font-semibold uppercase tracking-widest text-neutral-400">
          Customers
        </p>
        <div className="px-4 pt-3">
          <label className="flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-2 focus-within:border-brand">
            <Search className="h-4 w-4 text-neutral-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search customers..."
              className="w-full bg-transparent text-sm text-white placeholder:text-neutral-500 focus:outline-none"
            />
          </label>
        </div>

        <nav className="mt-3 flex-1 space-y-1 overflow-y-auto px-4 pb-4">
          {filtered.map((c) => {
            const Icon = c.customer_type === 'BUSINESS' ? Building2 : User
            return (
              <NavLink
                key={c.customer_id}
                to={`/kyc/${c.customer_id}`}
                className={({ isActive }) =>
                  `flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                    isActive ? 'bg-brand/15 text-brand-light' : 'text-neutral-300 hover:bg-panel'
                  }`
                }
              >
                <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{displayName(c)}</span>
                  <span className="flex items-center gap-1.5 text-xs text-neutral-500">
                    <span className={`h-1.5 w-1.5 rounded-full ${riskDot[c.risk_rating]}`} />
                    {c.customer_id} · {c.risk_rating.toLowerCase()} risk
                  </span>
                </span>
              </NavLink>
            )
          })}
          {customers.length > 0 && filtered.length === 0 && (
            <p className="px-3 py-2 text-sm text-neutral-500">No matches</p>
          )}
        </nav>

        <p className="border-t border-line px-5 py-3 text-xs text-neutral-500">
          
        </p>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto bg-surface">
        <Outlet />
      </main>
    </div>
  )
}
