import { useQueries, useQuery } from "@tanstack/react-query"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { useSearchParams } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import { type Currency, formatPrice } from "@/lib/format"
import type { Commodity, Paginated, PriceQuote } from "@/lib/types"

const PALETTE = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
]
const MAX = 4

export function Compare() {
  const [params, setParams] = useSearchParams()
  const selected = (params.get("m") ?? "").split(",").filter(Boolean).slice(0, MAX)
  const currency = (params.get("cur") as Currency) ?? "usd"
  const mode = params.get("mode") ?? "indexed"

  const list = useQuery({
    queryKey: ["list", "/commodities/"],
    queryFn: () => api.get<Paginated<Commodity>>("/commodities/"),
    staleTime: Infinity,
  })
  const commodities = list.data?.results ?? []

  const priceQueries = useQueries({
    queries: selected.map((slug) => ({
      queryKey: ["commodity", slug, "prices"],
      queryFn: () => api.get<PriceQuote[]>(`/commodities/${slug}/prices/`),
    })),
  })

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next)
  }

  const toggle = (slug: string) => {
    if (selected.includes(slug)) setParam("m", selected.filter((s) => s !== slug).join(","))
    else if (selected.length < MAX) setParam("m", [...selected, slug].join(","))
  }

  // Merge per-commodity series into one dataset keyed by date.
  const dates = new Set<string>()
  priceQueries.forEach((q) => (q.data ?? []).forEach((p) => dates.add(p.date)))
  const sortedDates = [...dates].sort()

  const series = selected.map((slug, i) => {
    const data = priceQueries[i].data ?? []
    const map = new Map<string, number | null>(
      data.map((p) => [p.date, currency === "usd" ? Number(p.price_usd) : p.price_eur ? Number(p.price_eur) : null]),
    )
    const first = data.map((p) => map.get(p.date)).find((v) => v != null) ?? null
    return { slug, map, first }
  })

  const chartData = sortedDates.map((date) => {
    const row: Record<string, number | string> = { date }
    series.forEach((s) => {
      const v = s.map.get(date)
      if (v != null) {
        row[s.slug] = mode === "indexed" && s.first ? (v / s.first) * 100 : v
      }
    })
    return row
  })

  const bySlug = new Map(commodities.map((c) => [c.slug, c]))

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Comparer</h1>
        <p className="text-sm text-muted-foreground">
          Sélectionne jusqu'à {MAX} matières. L'indice base 100 permet de comparer des
          cours d'échelles différentes.
        </p>
      </div>

      {/* Picker */}
      <div className="flex flex-wrap gap-2">
        {commodities.map((c) => {
          const on = selected.includes(c.slug)
          return (
            <button
              key={c.slug}
              onClick={() => toggle(c.slug)}
              className={`rounded-full border px-3 py-1 text-sm transition-colors cursor-pointer ${
                on
                  ? "bg-primary text-primary-foreground border-primary"
                  : "hover:bg-accent text-muted-foreground"
              }`}
            >
              {c.name}
            </button>
          )
        })}
      </div>

      {selected.length === 0 ? (
        <div className="grid place-items-center rounded-xl border border-dashed py-16 text-sm text-muted-foreground">
          Choisis au moins une matière à comparer.
        </div>
      ) : (
        <>
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Cours comparés</CardTitle>
              <div className="flex items-center gap-2">
                <Toggle
                  value={mode}
                  onChange={(v) => setParam("mode", v)}
                  options={[
                    { value: "indexed", label: "Base 100" },
                    { value: "absolute", label: "Absolu" },
                  ]}
                />
                <Toggle
                  value={currency}
                  onChange={(v) => setParam("cur", v)}
                  options={[
                    { value: "usd", label: "USD" },
                    { value: "eur", label: "EUR" },
                  ]}
                />
              </div>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={chartData} margin={{ left: 4, right: 8, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    fontSize={11}
                    minTickGap={32}
                    stroke="var(--color-muted-foreground)"
                    tickFormatter={(d: string) =>
                      new Date(d).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" })
                    }
                  />
                  <YAxis width={56} fontSize={11} stroke="var(--color-muted-foreground)" />
                  <Tooltip
                    contentStyle={{
                      background: "var(--color-popover)",
                      border: "1px solid var(--color-border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    labelFormatter={(d) => new Date(String(d)).toLocaleDateString("fr-FR")}
                  />
                  <Legend />
                  {selected.map((slug, i) => (
                    <Line
                      key={slug}
                      type="monotone"
                      dataKey={slug}
                      name={bySlug.get(slug)?.name ?? slug}
                      stroke={PALETTE[i % PALETTE.length]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Synthèse</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Matière</TableHead>
                    <TableHead>Catégorie</TableHead>
                    <TableHead className="text-right">Dernier cours</TableHead>
                    <TableHead className="text-right">Unité</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {selected.map((slug) => {
                    const c = bySlug.get(slug)
                    if (!c) return null
                    return (
                      <TableRow key={slug}>
                        <TableCell className="font-medium">{c.name}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">{c.category_display}</Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatPrice(currency === "usd" ? c.latest_price_usd : c.latest_price_eur, currency)}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">{c.price_unit}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function Toggle({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="inline-flex rounded-md border p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${
            value === o.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
