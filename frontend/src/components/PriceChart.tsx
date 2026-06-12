import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { type Currency, formatPrice } from "@/lib/format"
import type { PriceQuote } from "@/lib/types"

export function PriceChart({ data, currency }: { data: PriceQuote[]; currency: Currency }) {
  const points = data
    .map((d) => ({
      date: d.date,
      value: currency === "usd" ? Number(d.price_usd) : d.price_eur ? Number(d.price_eur) : null,
    }))
    .filter((p) => p.value !== null)

  if (points.length === 0) {
    return (
      <div className="grid h-[280px] place-items-center text-sm text-muted-foreground">
        Aucun cours disponible pour le moment.
      </div>
    )
  }

  // Colour the line by the net move over the visible window: green when the price
  // ended higher than it started, red when lower — so the hue carries real meaning.
  const values = points.map((p) => p.value as number)
  const color =
    values[values.length - 1] >= values[0] ? "var(--color-positive)" : "var(--color-destructive)"

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={points} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d: string) =>
            new Date(d).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" })
          }
          fontSize={11}
          tickMargin={8}
          minTickGap={32}
          stroke="var(--color-muted-foreground)"
        />
        <YAxis
          width={64}
          fontSize={11}
          stroke="var(--color-muted-foreground)"
          tickFormatter={(v: number) => formatPrice(v, currency)}
        />
        <Tooltip
          formatter={(value) => [formatPrice(Number(value), currency), "Cours"]}
          labelFormatter={(label) => new Date(String(label)).toLocaleDateString("fr-FR")}
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill="url(#priceFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
