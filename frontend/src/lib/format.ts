export type Currency = "usd" | "eur"

const CURRENCY_SYMBOL: Record<Currency, string> = { usd: "$", eur: "€" }

export function formatPrice(value: string | number | null, currency: Currency = "usd"): string {
  if (value === null || value === undefined) return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  return `${CURRENCY_SYMBOL[currency]}${num.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}`
}

export function formatTonnes(value: string | number | null): string {
  if (value === null || value === undefined) return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  if (num >= 1_000_000) return `${(num / 1_000_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mt`
  if (num >= 1_000) return `${(num / 1_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} kt`
  return `${num.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} t`
}

export function formatDate(value: string | null): string {
  if (!value) return "—"
  return new Date(value).toLocaleDateString("fr-FR", { year: "numeric", month: "short", day: "numeric" })
}
