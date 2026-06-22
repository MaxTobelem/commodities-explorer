import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Trash2 } from "lucide-react"
import { useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import {
  Area,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError, api } from "@/lib/api"
import { type Currency, formatDate, formatPrice } from "@/lib/format"
import type {
  Commodity,
  Paginated,
  Portfolio,
  PortfolioHistoryPoint,
  PortfolioTransaction,
  PortfolioValuation,
  Sector,
  TransactionPreview,
} from "@/lib/types"

const PIE_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
]
const TODAY = new Date().toISOString().slice(0, 10)

function pnlClass(n: number) {
  return n >= 0 ? "text-emerald-600" : "text-destructive"
}

export function PortfolioDetail() {
  const { id = "" } = useParams()
  const qc = useQueryClient()
  const [asOf, setAsOf] = useState(TODAY)

  const portfolio = useQuery({
    queryKey: ["portfolio", id],
    queryFn: () => api.get<Portfolio>(`/portfolios/${id}/`),
  })
  const valuation = useQuery({
    queryKey: ["portfolio", id, "valuation", asOf],
    queryFn: () => api.get<PortfolioValuation>(`/portfolios/${id}/valuation/?as_of=${asOf}`),
  })
  const history = useQuery({
    queryKey: ["portfolio", id, "history", asOf],
    queryFn: () =>
      api.get<PortfolioHistoryPoint[]>(`/portfolios/${id}/history/?to=${asOf}&resolution=daily`),
  })
  const transactions = useQuery({
    queryKey: ["portfolio", id, "transactions"],
    queryFn: () => api.get<PortfolioTransaction[]>(`/portfolios/${id}/transactions/`),
  })
  const commodities = useQuery({
    queryKey: ["commodities-all"],
    queryFn: () => api.get<Paginated<Commodity>>("/commodities/?page_size=1000&ordering=name"),
    staleTime: Infinity,
  })
  const sectors = useQuery({
    queryKey: ["sectors-all"],
    queryFn: () => api.get<Paginated<Sector>>("/sectors/?page_size=1000&ordering=name"),
    staleTime: Infinity,
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ["portfolio", id] })

  if (portfolio.isLoading) return <Skeleton className="h-64 w-full" />
  if (!portfolio.data) return <p>Portefeuille introuvable.</p>
  const p = portfolio.data
  const currency = p.base_currency.toLowerCase() as Currency
  const v = valuation.data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link to="/portfolios" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Portefeuilles
        </Link>
        <div className="flex items-center gap-2">
          <Label htmlFor="asof" className="text-xs text-muted-foreground">Se placer au</Label>
          <Input id="asof" type="date" value={asOf} max={TODAY} onChange={(e) => setAsOf(e.target.value)} className="h-8 w-auto" />
        </div>
      </div>

      <h1 className="text-xl font-semibold tracking-tight">
        {p.name} <span className="text-sm font-normal text-muted-foreground">· {p.base_currency}</span>
      </h1>

      {/* Summary */}
      {v && (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-5">
          <SummaryCard label="Valeur totale" value={formatPrice(v.total_value, currency)} />
          <SummaryCard label="Trésorerie" value={formatPrice(v.cash, currency)} />
          <SummaryCard label="Investi (coût)" value={formatPrice(v.invested, currency)} />
          <SummaryCard
            label="P&L total"
            value={`${Number(v.total_pnl) >= 0 ? "+" : ""}${formatPrice(v.total_pnl, currency)}`}
            sub={`${Number(v.total_pnl_pct) >= 0 ? "+" : ""}${Number(v.total_pnl_pct).toFixed(1)}% · réalisé ${formatPrice(v.realized_pnl, currency)}`}
            cls={pnlClass(Number(v.total_pnl))}
          />
          <SummaryCard label="Frais payés" value={formatPrice(v.fees_total, currency)} />
        </div>
      )}

      {/* Value over time */}
      <Card>
        <CardHeader><CardTitle className="text-base">Valeur dans le temps</CardTitle></CardHeader>
        <CardContent>
          {history.isLoading ? (
            <Skeleton className="h-[260px]" />
          ) : (history.data ?? []).length < 2 ? (
            <p className="text-sm text-muted-foreground">Pas encore assez d'historique.</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={(history.data ?? []).map((h) => ({ date: h.date, value: Number(h.value), invested: Number(h.invested) }))} margin={{ left: 4, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="pfFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                <XAxis dataKey="date" fontSize={11} tickMargin={8} minTickGap={32} stroke="var(--color-muted-foreground)"
                  tickFormatter={(d: string) => new Date(d).toLocaleDateString("fr-FR", { month: "short", day: "numeric" })} />
                <YAxis width={64} fontSize={11} stroke="var(--color-muted-foreground)" tickFormatter={(n: number) => formatPrice(n, currency)} />
                <Tooltip
                  formatter={(val, name) => [formatPrice(Number(val), currency), name === "value" ? "Valeur" : "Investi"]}
                  labelFormatter={(l) => new Date(String(l)).toLocaleDateString("fr-FR")}
                  contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }} />
                <Area type="monotone" dataKey="value" stroke="var(--color-chart-1)" strokeWidth={2} fill="url(#pfFill)" />
                <Line type="monotone" dataKey="invested" stroke="var(--color-muted-foreground)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Composition + positions */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-base">Composition</CardTitle></CardHeader>
          <CardContent>
            {v && v.positions.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={v.positions.map((pos) => ({ name: pos.commodity.name, value: Number(pos.market_value) }))}
                    dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                    {v.positions.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(val) => formatPrice(Number(val), currency)}
                    contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground">Aucune position.</p>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle className="text-base">Positions</CardTitle></CardHeader>
          <CardContent>
            {v && v.positions.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Matière</TableHead>
                    <TableHead className="text-right">Qté</TableHead>
                    <TableHead className="text-right">Prix moy.</TableHead>
                    <TableHead className="text-right">Prix actuel</TableHead>
                    <TableHead className="text-right">Valeur</TableHead>
                    <TableHead className="text-right">Poids</TableHead>
                    <TableHead className="text-right">P&L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {v.positions.map((pos) => {
                    const pnl = Number(pos.unrealized_pnl)
                    return (
                      <TableRow key={pos.commodity.slug}>
                        <TableCell>
                          <Link to={`/commodity/${pos.commodity.slug}`} className="hover:underline">{pos.commodity.name}</Link>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{Number(pos.quantity).toLocaleString("fr-FR", { maximumFractionDigits: 4 })}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatPrice(pos.avg_cost, currency)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatPrice(pos.price, currency)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatPrice(pos.market_value, currency)}</TableCell>
                        <TableCell className="text-right tabular-nums">{Number(pos.weight).toFixed(1)}%</TableCell>
                        <TableCell className={`text-right tabular-nums ${pnlClass(pnl)}`}>{pnl >= 0 ? "+" : ""}{formatPrice(pos.unrealized_pnl, currency)}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">Aucune position à cette date.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Add transaction + sector */}
      <div className="grid gap-4 lg:grid-cols-2">
        <AddTransaction portfolioId={id} currency={currency} commodities={commodities.data?.results ?? []} onDone={refresh} />
        <SectorBuy portfolioId={id} sectors={sectors.data?.results ?? []} onDone={refresh} />
      </div>

      {/* Journal */}
      <Card>
        <CardHeader><CardTitle className="text-base">Journal des transactions</CardTitle></CardHeader>
        <CardContent>
          {(transactions.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune transaction.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Matière</TableHead>
                  <TableHead className="text-right">Montant</TableHead>
                  <TableHead className="text-right">Frais</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(transactions.data ?? []).map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{formatDate(t.date)}</TableCell>
                    <TableCell>{t.kind_display}</TableCell>
                    <TableCell>{t.commodity?.name ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatPrice(t.amount, currency)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatPrice(t.fee, currency)}</TableCell>
                    <TableCell className="text-right">
                      <button
                        className="text-muted-foreground hover:text-destructive"
                        onClick={async () => {
                          await api.del(`/portfolios/${id}/transactions/${t.id}/`)
                          refresh()
                        }}
                        aria-label="Supprimer"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function SummaryCard({ label, value, sub, cls }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={`text-xl font-semibold tabular-nums ${cls ?? ""}`}>{value}</div>
        {sub && <div className={`text-xs tabular-nums ${cls ?? "text-muted-foreground"}`}>{sub}</div>}
      </CardContent>
    </Card>
  )
}

function AddTransaction({ portfolioId, currency, commodities, onDone }: {
  portfolioId: string
  currency: Currency
  commodities: Commodity[]
  onDone: () => void
}) {
  const [kind, setKind] = useState("deposit")
  const [date, setDate] = useState(TODAY)
  const [commodity, setCommodity] = useState("")
  const [amount, setAmount] = useState("")
  const [preview, setPreview] = useState<TransactionPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const needsCommodity = kind === "buy" || kind === "sell"

  const body = () => ({
    kind, date, amount,
    ...(needsCommodity ? { commodity } : {}),
  })

  const run = async (action: "preview" | "submit") => {
    setError(null)
    try {
      if (action === "preview") {
        setPreview(await api.post<TransactionPreview>(`/portfolios/${portfolioId}/preview/`, body()))
      } else {
        await api.post(`/portfolios/${portfolioId}/transactions/`, body())
        setPreview(null)
        setAmount("")
        onDone()
      }
    } catch (e) {
      setError(e instanceof ApiError ? String((e.data as { detail?: string })?.detail ?? "Erreur") : "Erreur")
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Nouvelle transaction</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Type</Label>
            <select value={kind} onChange={(e) => { setKind(e.target.value); setPreview(null) }}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm">
              <option value="deposit">Dépôt</option>
              <option value="withdraw">Retrait</option>
              <option value="buy">Achat</option>
              <option value="sell">Vente</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Date</Label>
            <Input type="date" value={date} max={TODAY} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        {needsCommodity && (
          <div className="space-y-1.5">
            <Label>Matière</Label>
            <select value={commodity} onChange={(e) => setCommodity(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm">
              <option value="">— choisir —</option>
              {commodities.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </select>
          </div>
        )}
        <div className="space-y-1.5">
          <Label>Montant ({currency.toUpperCase()})</Label>
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" />
        </div>

        {preview && (
          <div className="rounded-md bg-secondary/50 p-3 text-sm space-y-0.5">
            {preview.unit_price && (
              <div>Quantité : <span className="tabular-nums">{Number(preview.quantity).toLocaleString("fr-FR", { maximumFractionDigits: 4 })}</span> @ {formatPrice(preview.unit_price, currency)}</div>
            )}
            <div>Frais : <span className="tabular-nums">{formatPrice(preview.fee, currency)}</span></div>
            <div>Trésorerie après : <span className="tabular-nums">{formatPrice(preview.cash_after, currency)}</span></div>
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button variant="outline" type="button" disabled={!amount || (needsCommodity && !commodity)} onClick={() => run("preview")}>Aperçu</Button>
          <Button type="button" disabled={!amount || (needsCommodity && !commodity)} onClick={() => run("submit")}>Valider</Button>
        </div>
      </CardContent>
    </Card>
  )
}

function SectorBuy({ portfolioId, sectors, onDone }: {
  portfolioId: string
  sectors: Sector[]
  onDone: () => void
}) {
  const [sector, setSector] = useState("")
  const [amount, setAmount] = useState("")
  const [date, setDate] = useState(TODAY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Commodities in the chosen sector (via the existing catalogue filter).
  const inSector = useQuery({
    queryKey: ["commodities-sector", sector],
    queryFn: () => api.get<Paginated<Commodity>>(`/commodities/?sector=${sector}&page_size=1000`),
    enabled: !!sector,
  })
  const members = inSector.data?.results ?? []
  const perAsset = useMemo(() => {
    const n = members.length
    const a = Number(amount)
    return n && a ? (a / n) : 0
  }, [members.length, amount])

  const submit = async () => {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/portfolios/${portfolioId}/transactions/batch/`, {
        items: members.map((c) => ({ kind: "buy", date, commodity: c.slug, amount: String(perAsset) })),
      })
      setAmount("")
      onDone()
    } catch (e) {
      setError(e instanceof ApiError ? String((e.data as { detail?: string })?.detail ?? "Erreur") : "Erreur")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Acheter un secteur (équipondéré)</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Secteur</Label>
            <select value={sector} onChange={(e) => setSector(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm">
              <option value="">— choisir —</option>
              {sectors.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Date</Label>
            <Input type="date" value={date} max={TODAY} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Montant total</Label>
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" />
        </div>
        {sector && (
          <p className="text-xs text-muted-foreground">
            {members.length} matière(s) → {perAsset ? formatPrice(perAsset, "eur") : "—"} chacune (réparti à parts égales).
          </p>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="button" disabled={!sector || !amount || !members.length || busy} onClick={submit}>Acheter le secteur</Button>
      </CardContent>
    </Card>
  )
}
