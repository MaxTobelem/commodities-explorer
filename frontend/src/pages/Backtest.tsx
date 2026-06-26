import { useMutation, useQuery } from "@tanstack/react-query"
import { LineChart as LineChartIcon, Loader2, Plus, Trash2 } from "lucide-react"
import { useMemo, useState } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Combobox, type ComboOption } from "@/components/ui/combobox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, ApiError } from "@/lib/api"
import { type Currency, formatPrice } from "@/lib/format"
import type { BacktestResponse, BtResult, Instrument } from "@/lib/types"

// Each allocation/benchmark gets a stable colour across every chart & table.
const SERIES_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
]
const BENCH_COLOR = "var(--color-muted-foreground)"

const REBALANCE_LABELS: Record<string, string> = {
  none: "Aucun (buy & hold)",
  monthly: "Mensuel",
  quarterly: "Trimestriel",
  annual: "Annuel",
}

const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)} %`
const ratio = (x: number) => `${x.toFixed(1)} %`

interface Line0 {
  ref: string
  weight: string
}
interface AllocDraft {
  name: string
  lines: Line0[]
}

const emptyLine = (): Line0 => ({ ref: "", weight: "" })
const newAlloc = (name: string): AllocDraft => ({ name, lines: [{ ref: "", weight: "100" }] })

function linesToWeights(lines: Line0[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const l of lines) {
    const w = Number(l.weight)
    if (l.ref && w > 0) out[l.ref] = w
  }
  return out
}

const errMsg = (e: unknown) =>
  e instanceof ApiError && e.data && typeof e.data === "object" && "detail" in e.data
    ? String((e.data as { detail: unknown }).detail)
    : "Erreur lors du backtest."

export function Backtest() {
  const instrumentsQ = useQuery({
    queryKey: ["instruments"],
    queryFn: () => api.get<Instrument[]>("/market-assets/instruments/"),
  })

  const options: ComboOption[] = useMemo(
    () =>
      (instrumentsQ.data ?? []).map((i) => ({
        value: i.ref,
        label: `${i.label} · ${i.group_display}`,
      })),
    [instrumentsQ.data],
  )
  const labelOf = useMemo(() => {
    const m = new Map<string, string>()
    for (const i of instrumentsQ.data ?? []) m.set(i.ref, i.label)
    return (ref: string) => m.get(ref) ?? ref
  }, [instrumentsQ.data])

  const [allocs, setAllocs] = useState<AllocDraft[]>([newAlloc("Portefeuille 1")])
  const [benchEnabled, setBenchEnabled] = useState(true)
  const [bench, setBench] = useState<AllocDraft>(newAlloc("Benchmark"))

  const [amount, setAmount] = useState("10000")
  const [currency, setCurrency] = useState("EUR")
  const [rebalance, setRebalance] = useState("monthly")
  const [fee, setFee] = useState("0.20")
  const [start, setStart] = useState("2010-01-01")
  const [end, setEnd] = useState("")
  const [formError, setFormError] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: (body: unknown) => api.post<BacktestResponse>("/backtest/", body),
  })

  const updateAlloc = (idx: number, next: AllocDraft) =>
    setAllocs((prev) => prev.map((a, i) => (i === idx ? next : a)))

  const onRun = () => {
    setFormError(null)
    const payloadAllocs = allocs
      .map((a) => ({ name: a.name, weights: linesToWeights(a.lines) }))
      .filter((a) => Object.keys(a.weights).length > 0)
    if (payloadAllocs.length === 0) {
      setFormError("Ajoutez au moins un actif avec une pondération à une allocation.")
      return
    }
    const benchWeights = linesToWeights(bench.lines)
    const body = {
      amount: Number(amount) || 0,
      currency,
      rebalance,
      fee_percent: Number(fee) || 0,
      start: start || undefined,
      end: end || undefined,
      allocations: payloadAllocs,
      benchmark:
        benchEnabled && Object.keys(benchWeights).length > 0
          ? { name: bench.name, weights: benchWeights }
          : undefined,
    }
    run.mutate(body)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <LineChartIcon className="size-5" />
        <h1 className="text-xl font-semibold tracking-tight">Backtest historique</h1>
      </div>
      <p className="text-sm text-muted-foreground -mt-3">
        « Si j'avais investi à telle date sur cette allocation… » — performance brute et nette de
        frais, avec métriques de risque (CAGR, volatilité, Sharpe, VaR, drawdown) et comparaison à
        un benchmark. Univers : matières premières + indices financiers.
      </p>

      {/* --- Builder --- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Allocations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            {allocs.map((a, i) => (
              <AllocationEditor
                key={i}
                draft={a}
                color={SERIES_COLORS[i % SERIES_COLORS.length]}
                options={options}
                disabled={instrumentsQ.isLoading}
                onChange={(next) => updateAlloc(i, next)}
                onRemove={allocs.length > 1 ? () => setAllocs((p) => p.filter((_, j) => j !== i)) : undefined}
              />
            ))}
          </div>
          {allocs.length < 3 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAllocs((p) => [...p, newAlloc(`Portefeuille ${p.length + 1}`)])}
            >
              <Plus className="size-4" /> Ajouter une allocation à comparer
            </Button>
          )}

          {/* Benchmark */}
          <div className="rounded-lg border border-dashed p-3 space-y-3">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={benchEnabled}
                onChange={(e) => setBenchEnabled(e.target.checked)}
                className="size-4"
              />
              Comparer à un benchmark
            </label>
            {benchEnabled && (
              <AllocationEditor
                draft={bench}
                color={BENCH_COLOR}
                options={options}
                disabled={instrumentsQ.isLoading}
                onChange={setBench}
              />
            )}
          </div>
        </CardContent>
      </Card>

      {/* --- Parameters --- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Paramètres</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6 items-end">
            <Field label="Montant initial">
              <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" />
            </Field>
            <Field label="Devise">
              <Select value={currency} onValueChange={setCurrency}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="EUR">Euro (€)</SelectItem>
                  <SelectItem value="USD">Dollar ($)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Rééquilibrage">
              <Select value={rebalance} onValueChange={setRebalance}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(REBALANCE_LABELS).map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Frais / opération (%)">
              <Input value={fee} onChange={(e) => setFee(e.target.value)} inputMode="decimal" />
            </Field>
            <Field label="Début">
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="Fin">
              <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Button onClick={onRun} disabled={run.isPending || instrumentsQ.isLoading}>
              {run.isPending ? <Loader2 className="size-4 animate-spin" /> : <LineChartIcon className="size-4" />}
              Lancer le backtest
            </Button>
            {formError && <span className="text-sm text-destructive">{formError}</span>}
            {run.isError && <span className="text-sm text-destructive">{errMsg(run.error)}</span>}
            <span className="text-xs text-muted-foreground">
              Les pondérations sont normalisées à 100 %. Données indices jusqu'à fin 2021.
            </span>
          </div>
        </CardContent>
      </Card>

      {/* --- Results --- */}
      {run.data && <Results data={run.data} labelOf={labelOf} />}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function AllocationEditor({
  draft,
  color,
  options,
  disabled,
  onChange,
  onRemove,
}: {
  draft: AllocDraft
  color: string
  options: ComboOption[]
  disabled?: boolean
  onChange: (next: AllocDraft) => void
  onRemove?: () => void
}) {
  const total = draft.lines.reduce((s, l) => s + (Number(l.weight) || 0), 0)
  const chosen = new Set(draft.lines.map((l) => l.ref).filter(Boolean))

  const setLine = (i: number, patch: Partial<Line0>) =>
    onChange({ ...draft, lines: draft.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) })

  return (
    <div className="rounded-lg border p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <span className="size-2.5 shrink-0 rounded-sm" style={{ background: color }} />
        <Input
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
          className="h-8 font-medium"
        />
        {onRemove && (
          <button
            onClick={onRemove}
            aria-label="Supprimer l'allocation"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
          >
            <Trash2 className="size-4" />
          </button>
        )}
      </div>
      {draft.lines.map((l, i) => (
        <div key={i} className="flex items-center gap-2">
          <Combobox
            value={l.ref}
            onChange={(v) => setLine(i, { ref: v })}
            // Hide instruments already used elsewhere in this allocation.
            options={options.filter((o) => o.value === l.ref || !chosen.has(o.value))}
            disabled={disabled}
            placeholder="— actif —"
            className="flex-1"
          />
          <Input
            value={l.weight}
            onChange={(e) => setLine(i, { weight: e.target.value })}
            inputMode="decimal"
            className="h-9 w-20 text-right"
            aria-label="Pondération"
          />
          <span className="text-sm text-muted-foreground">%</span>
          {draft.lines.length > 1 && (
            <button
              onClick={() => onChange({ ...draft, lines: draft.lines.filter((_, j) => j !== i) })}
              aria-label="Retirer la ligne"
              className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ))}
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange({ ...draft, lines: [...draft.lines, emptyLine()] })}
        >
          <Plus className="size-3.5" /> Ligne
        </Button>
        <span className={`text-xs tabular-nums ${Math.abs(total - 100) < 0.01 ? "text-muted-foreground" : "text-amber-600"}`}>
          Total {total.toFixed(0)} %
        </span>
      </div>
    </div>
  )
}

// --- Results dashboard ------------------------------------------------------

interface Series {
  name: string
  color: string
  isBenchmark: boolean
  res: BtResult
}

function Results({
  data,
  labelOf,
}: {
  data: BacktestResponse
  labelOf: (ref: string) => string
}) {
  const cur = data.currency.toLowerCase() as Currency
  const series: Series[] = [
    ...data.results.map((res, i) => ({
      name: res.name,
      color: SERIES_COLORS[i % SERIES_COLORS.length],
      isBenchmark: false,
      res,
    })),
    ...(data.benchmark
      ? [{ name: data.benchmark.name, color: BENCH_COLOR, isBenchmark: true, res: data.benchmark }]
      : []),
  ]
  const [showGross, setShowGross] = useState(true)

  const equityData = data.dates.map((d, i) => {
    const row: Record<string, string | number> = { date: d }
    for (const s of series) {
      row[`${s.name}`] = s.res.equity_net[i]
      if (showGross && !s.isBenchmark) row[`${s.name} (brut)`] = s.res.equity_gross[i]
    }
    return row
  })

  const drawdownData = data.dates.map((d, i) => {
    const row: Record<string, string | number> = { date: d }
    for (const s of series) row[s.name] = +(s.res.drawdown[i] * 100).toFixed(2)
    return row
  })

  const years = Array.from(
    new Set(series.flatMap((s) => s.res.calendar_years.map((c) => c.year))),
  ).sort()
  const calendarData = years.map((year) => {
    const row: Record<string, string | number> = { year }
    for (const s of series) {
      const hit = s.res.calendar_years.find((c) => c.year === year)
      if (hit) row[s.name] = +(hit.return * 100).toFixed(2)
    }
    return row
  })

  const fmtAxis = (d: string) =>
    new Date(d).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" })
  const tooltipStyle = {
    background: "var(--color-popover)",
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    fontSize: 12,
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {series.map((s) => (
          <Card key={s.name}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
                <span className="truncate">{s.name}</span>
                {s.isBenchmark && <span className="text-xs font-normal text-muted-foreground">benchmark</span>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold tabular-nums">
                {formatPrice(s.res.metrics.final_net, cur)}
              </div>
              <div className="text-sm text-muted-foreground tabular-nums">
                CAGR <b className="text-foreground">{pct(s.res.metrics.cagr)}</b> · vol {pct(s.res.metrics.volatility)} ·
                Sharpe {s.res.metrics.sharpe.toFixed(2)}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Equity curve */}
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
          <CardTitle className="text-base">Évolution de la valeur</CardTitle>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={showGross} onChange={(e) => setShowGross(e.target.checked)} className="size-3.5" />
            afficher le brut
          </label>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={equityData} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
              <XAxis dataKey="date" tickFormatter={fmtAxis} fontSize={11} tickMargin={8} minTickGap={40} stroke="var(--color-muted-foreground)" />
              <YAxis width={72} fontSize={11} stroke="var(--color-muted-foreground)" tickFormatter={(v: number) => formatPrice(v, cur)} />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v) => formatPrice(Number(v), cur)}
                labelFormatter={(l) => new Date(String(l)).toLocaleDateString("fr-FR")}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {series.map((s) => (
                <Line key={s.name} type="monotone" dataKey={s.name} stroke={s.color} strokeWidth={2} dot={false} />
              ))}
              {showGross &&
                series
                  .filter((s) => !s.isBenchmark)
                  .map((s) => (
                    <Line
                      key={`${s.name}-g`}
                      type="monotone"
                      dataKey={`${s.name} (brut)`}
                      stroke={s.color}
                      strokeWidth={1.2}
                      strokeDasharray="4 3"
                      dot={false}
                      opacity={0.65}
                    />
                  ))}
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-muted-foreground">
            Trait plein = net de frais, pointillés = brut. Période : {data.start} → {data.end} ({data.months}{" "}
            mois, rééq. {REBALANCE_LABELS[data.rebalance]?.toLowerCase()}). Inflation {pct(data.inflation)}/an,
            taux sans risque {pct(data.rf_cagr)}/an.
          </p>
        </CardContent>
      </Card>

      <MetricsTable series={series} cur={cur} labelOf={labelOf} />

      {/* Drawdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Drawdown (repli depuis le plus haut)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={drawdownData} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
              <XAxis dataKey="date" tickFormatter={fmtAxis} fontSize={11} tickMargin={8} minTickGap={40} stroke="var(--color-muted-foreground)" />
              <YAxis width={48} fontSize={11} stroke="var(--color-muted-foreground)" tickFormatter={(v: number) => `${v}%`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${Number(v).toFixed(1)} %`} labelFormatter={(l) => new Date(String(l)).toLocaleDateString("fr-FR")} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {series.map((s) => (
                <Line key={s.name} type="monotone" dataKey={s.name} stroke={s.color} strokeWidth={1.6} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Calendar-year performance */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Performance par année civile</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={calendarData} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
              <XAxis dataKey="year" fontSize={11} tickMargin={8} stroke="var(--color-muted-foreground)" />
              <YAxis width={48} fontSize={11} stroke="var(--color-muted-foreground)" tickFormatter={(v: number) => `${v}%`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${Number(v).toFixed(1)} %`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {series.map((s) => (
                <Bar key={s.name} dataKey={s.name} fill={s.color} radius={[2, 2, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}

function MetricsTable({
  series,
  cur,
  labelOf,
}: {
  series: Series[]
  cur: Currency
  labelOf: (ref: string) => string
}) {
  const hasRelative = series.some((s) => s.res.relative)
  const rows: { label: string; render: (s: Series) => React.ReactNode }[] = [
    { label: "Valeur finale (net)", render: (s) => formatPrice(s.res.metrics.final_net, cur) },
    { label: "Valeur finale (brut)", render: (s) => formatPrice(s.res.metrics.final_gross, cur) },
    { label: "CAGR (annualisé)", render: (s) => pct(s.res.metrics.cagr) },
    { label: "Rendement annuel moyen", render: (s) => pct(s.res.metrics.annual_return) },
    { label: "Volatilité annualisée", render: (s) => pct(s.res.metrics.volatility) },
    { label: "Ratio de Sharpe", render: (s) => s.res.metrics.sharpe.toFixed(2) },
    { label: "Max drawdown", render: (s) => pct(s.res.metrics.max_drawdown) },
    { label: "VaR 95 % (mensuelle)", render: (s) => pct(s.res.metrics.var["95"].monthly) },
    { label: "VaR 95 % (annuelle)", render: (s) => pct(s.res.metrics.var["95"].annual) },
    { label: "VaR 99 % (mensuelle)", render: (s) => pct(s.res.metrics.var["99"].monthly) },
    { label: "Frais payés", render: (s) => formatPrice(s.res.metrics.fees_total, cur) },
  ]
  const relRows: { label: string; render: (s: Series) => React.ReactNode }[] = [
    { label: "Tracking error", render: (s) => (s.res.relative ? pct(s.res.relative.tracking_error) : "—") },
    { label: "Capture haussière", render: (s) => (s.res.relative ? ratio(s.res.relative.up_capture) : "—") },
    { label: "Capture baissière", render: (s) => (s.res.relative ? ratio(s.res.relative.down_capture) : "—") },
    {
      label: "Meilleur mois relatif",
      render: (s) => (s.res.relative?.best_relative_month ? pct(s.res.relative.best_relative_month.value) : "—"),
    },
    {
      label: "Pire mois relatif",
      render: (s) => (s.res.relative?.worst_relative_month ? pct(s.res.relative.worst_relative_month.value) : "—"),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Métriques détaillées</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-56">Métrique</TableHead>
                {series.map((s) => (
                  <TableHead key={s.name} className="text-right">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
                      {s.name}
                    </span>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.label}>
                  <TableCell className="text-muted-foreground">{r.label}</TableCell>
                  {series.map((s) => (
                    <TableCell key={s.name} className="text-right tabular-nums">
                      {r.render(s)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {hasRelative && (
                <>
                  <TableRow>
                    <TableCell colSpan={series.length + 1} className="bg-secondary/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Relatif au benchmark
                    </TableCell>
                  </TableRow>
                  {relRows.map((r) => (
                    <TableRow key={r.label}>
                      <TableCell className="text-muted-foreground">{r.label}</TableCell>
                      {series.map((s) => (
                        <TableCell key={s.name} className="text-right tabular-nums">
                          {r.render(s)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </>
              )}
            </TableBody>
          </Table>
        </div>
        <div className="mt-3 space-y-1 text-xs text-muted-foreground">
          {series.map((s) => (
            <div key={s.name}>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-sm" style={{ background: s.color }} />
                <b className="text-foreground">{s.name}</b>
              </span>{" "}
              :{" "}
              {Object.entries(s.res.weights)
                .map(([ref, w]) => `${labelOf(ref)} ${w}%`)
                .join(" · ")}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
