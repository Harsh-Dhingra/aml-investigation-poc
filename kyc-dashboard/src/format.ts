const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const usdCompact = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
})

export function formatUsd(value: number | null | undefined, compact = false) {
  if (value == null) return '—'
  return compact ? usdCompact.format(value) : usd.format(value)
}

export function formatNumber(value: number | null | undefined, digits = 0) {
  if (value == null) return '—'
  return value.toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

export function humanize(value: string | null | undefined) {
  if (!value) return '—'
  return value
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export function formatRange(range: { min: number; max: number } | null | undefined, money = false) {
  if (!range) return '—'
  const f = money ? (v: number) => formatUsd(v, true) : (v: number) => formatNumber(v)
  return `${f(range.min)} – ${f(range.max)}`
}

export function displayName(c: { business_name: string | null; fake_name: string }) {
  return c.business_name ?? c.fake_name
}
