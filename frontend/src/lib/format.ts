export type Currency = "usd" | "eur"

const CURRENCY_SYMBOL: Record<Currency, string> = { usd: "$", eur: "€" }

export function formatPrice(value: string | number | null, currency: Currency = "usd"): string {
  if (value === null || value === undefined) return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  return `${CURRENCY_SYMBOL[currency]}${num.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}`
}

export function formatUnit(unit: string | null | undefined, currency: Currency = "usd"): string {
  // The canonical unit is USD-denominated (e.g. "USD/t"); show it in the displayed
  // currency so a EUR price reads "EUR/t", not "USD/t".
  if (!unit) return ""
  return currency === "eur" ? unit.replace("USD", "EUR") : unit
}

export function formatTonnes(value: string | number | null): string {
  if (value === null || value === undefined) return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  if (num >= 1_000_000) return `${(num / 1_000_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mt`
  if (num >= 1_000) return `${(num / 1_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} kt`
  return `${num.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} t`
}

export function formatQuantity(value: string | number | null, unit: string): string {
  if (unit === "t") return formatTonnes(value)
  if (value === null || value === undefined) return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  // Compact SI scaling (k/M/G/T…) for very large quantities, e.g. gas reserves in m³.
  if (Math.abs(num) >= 1_000_000) {
    const prefixes = ["", "k", "M", "G", "T", "P"]
    let n = num
    let i = 0
    while (Math.abs(n) >= 1000 && i < prefixes.length - 1) {
      n /= 1000
      i += 1
    }
    return `${n.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} ${prefixes[i]}${unit}`
  }
  return `${num.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} ${unit}`
}

export function formatDate(value: string | null): string {
  if (!value) return "—"
  return new Date(value).toLocaleDateString("fr-FR", { year: "numeric", month: "short", day: "numeric" })
}
