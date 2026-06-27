import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Minus,
  Plus,
  Trash2,
  Wallet,
} from "lucide-react"
import { type ReactNode, useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
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
import { Combobox } from "@/components/ui/combobox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Modal } from "@/components/ui/modal"
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
  InvestQuote,
  Paginated,
  Portfolio,
  PortfolioHistoryPoint,
  PortfolioPosition,
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

/** A single P&L cell. Clicking toggles the whole column (state lives in the
 * parent) between the amount and a percentage of cost. */
function PnlCell({
  pnl,
  costBasis,
  currency,
  showPct,
  onToggle,
}: {
  pnl: number
  costBasis: number
  currency: Currency
  showPct: boolean
  onToggle: () => void
}) {
  const pct = costBasis > 0 ? (pnl / costBasis) * 100 : 0
  const sign = pnl >= 0 ? "+" : ""
  return (
    <TableCell className={`text-right tabular-nums ${pnlClass(pnl)}`}>
      <button
        type="button"
        onClick={onToggle}
        title={showPct ? "Afficher le montant" : "Afficher le pourcentage"}
        className="cursor-pointer tabular-nums underline-offset-2 hover:underline"
      >
        {showPct ? `${sign}${pct.toFixed(1)}%` : `${sign}${formatPrice(pnl, currency)}`}
      </button>
    </TableCell>
  )
}

function errMsg(e: unknown): string {
  return e instanceof ApiError
    ? String((e.data as { detail?: string })?.detail ?? "Erreur")
    : "Erreur"
}

function qtyFmt(n: number | string) {
  return Number(n).toLocaleString("fr-FR", { maximumFractionDigits: 4 })
}

export function PortfolioDetail() {
  const { id = "" } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [asOf, setAsOf] = useState(TODAY)
  const [cashKind, setCashKind] = useState<"deposit" | "withdraw" | null>(null)
  // P&L column display, toggled for the whole table at once (amount ↔ percent).
  const [pnlAsPct, setPnlAsPct] = useState(false)

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
  const txns = transactions.data ?? []
  const isEmpty = !transactions.isLoading && txns.length === 0

  const removePortfolio = async () => {
    if (!confirm(`Supprimer le portefeuille « ${p.name} » et toutes ses transactions ?`)) return
    await api.del(`/portfolios/${id}/`)
    qc.invalidateQueries({ queryKey: ["portfolios"] })
    navigate("/portfolios")
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link to="/portfolios" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Portefeuilles
        </Link>
        <div className="flex items-center gap-3">
          {!isEmpty && (
            <div className="flex items-center gap-2">
              <Label htmlFor="asof" className="text-xs text-muted-foreground">Se placer au</Label>
              <Input id="asof" type="date" value={asOf} max={TODAY} onChange={(e) => setAsOf(e.target.value)} className="h-8 w-auto" />
            </div>
          )}
          <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" onClick={removePortfolio}>
            <Trash2 className="size-4" /> Supprimer
          </Button>
        </div>
      </div>

      <h1 className="text-xl font-semibold tracking-tight">
        {p.name} <span className="text-sm font-normal text-muted-foreground">· {p.base_currency}</span>
      </h1>

      {isEmpty ? (
        <OnboardingCard portfolioId={id} currency={currency} onDone={refresh} />
      ) : (
        <>
          {/* Summary — P&L total now folds in the fees paid */}
          {v && (
            <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
              <SummaryCard label="Valeur totale" value={formatPrice(v.total_value, currency)} />
              <SummaryCard label="Trésorerie" value={formatPrice(v.cash, currency)} />
              <SummaryCard label="Investi (coût)" value={formatPrice(v.invested, currency)} />
              <SummaryCard
                label="P&L total"
                value={`${Number(v.total_pnl) >= 0 ? "+" : ""}${formatPrice(v.total_pnl, currency)}`}
                cls={pnlClass(Number(v.total_pnl))}
                sub={
                  <>
                    {Number(v.total_pnl_pct) >= 0 ? "+" : ""}{Number(v.total_pnl_pct).toFixed(1)}% · réalisé {formatPrice(v.realized_pnl, currency)}
                    <span className="block text-muted-foreground">dont {formatPrice(v.fees_total, currency)} de frais</span>
                  </>
                }
              />
            </div>
          )}

          {/* Cash actions */}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setCashKind("deposit")}>
              <Plus className="size-4" /> Déposer
            </Button>
            <Button variant="outline" size="sm" onClick={() => setCashKind("withdraw")}>
              <Minus className="size-4" /> Retirer
            </Button>
          </div>

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
            <CompositionChart positions={v?.positions ?? []} currency={currency} />

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
                            <TableCell className="text-right tabular-nums">{qtyFmt(pos.quantity)}</TableCell>
                            <TableCell className="text-right tabular-nums">{formatPrice(pos.avg_cost, currency)}</TableCell>
                            <TableCell className="text-right tabular-nums">{formatPrice(pos.price, currency)}</TableCell>
                            <TableCell className="text-right tabular-nums">{formatPrice(pos.market_value, currency)}</TableCell>
                            <TableCell className="text-right tabular-nums">{Number(pos.weight).toFixed(1)}%</TableCell>
                            <PnlCell
                              pnl={pnl}
                              costBasis={Number(pos.cost_basis)}
                              currency={currency}
                              showPct={pnlAsPct}
                              onToggle={() => setPnlAsPct((s) => !s)}
                            />
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

          {/* Trade + sector */}
          <div className="grid gap-4 lg:grid-cols-2">
            <TradeCard portfolioId={id} currency={currency} commodities={commodities.data?.results ?? []} positions={v?.positions ?? []} onDone={refresh} />
            <SectorBuy portfolioId={id} currency={currency} sectors={sectors.data?.results ?? []} onDone={refresh} />
          </div>

          {/* Journal */}
          <Journal currency={currency} txns={txns} />
        </>
      )}

      {cashKind !== null && (
        <CashModal
          key={cashKind}
          portfolioId={id}
          currency={currency}
          kind={cashKind}
          onClose={() => setCashKind(null)}
          onDone={refresh}
        />
      )}
    </div>
  )
}

function SummaryCard({ label, value, sub, cls }: { label: string; value: string; sub?: ReactNode; cls?: string }) {
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

/** Guided first step for an empty portfolio: deposit cash before anything else. */
function OnboardingCard({ portfolioId, currency, onDone }: {
  portfolioId: string
  currency: Currency
  onDone: () => void
}) {
  const [amount, setAmount] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const cur = currency.toUpperCase()

  const deposit = async (value: string) => {
    if (!value || Number(value) <= 0) return
    setBusy(true)
    setError(null)
    try {
      await api.post(`/portfolios/${portfolioId}/transactions/`, { kind: "deposit", date: TODAY, amount: value })
      setAmount("")
      onDone()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Wallet className="size-4" /> Déposez des fonds pour commencer
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Ce portefeuille est vide. Indiquez le montant que vous souhaitez y placer&nbsp;: vous
          pourrez ensuite acheter des matières premières (les frais de courtage sont toujours
          inclus dans les montants saisis).
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="dep">Montant ({cur})</Label>
            <Input id="dep" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" className="w-40" inputMode="decimal" />
          </div>
          <Button disabled={!amount || Number(amount) <= 0 || busy} onClick={() => deposit(amount)}>Déposer</Button>
          <div className="flex gap-2">
            {["1000", "5000", "10000"].map((vv) => (
              <Button key={vv} type="button" variant="outline" size="sm" disabled={busy} onClick={() => deposit(vv)}>
                + {Number(vv).toLocaleString("fr-FR")}
              </Button>
            ))}
          </div>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <p className="text-xs text-muted-foreground">
          Astuce&nbsp;: vous pouvez aussi investir directement depuis la page d'une matière, via le
          bouton «&nbsp;Investir&nbsp;» — le dépôt manquant vous sera alors proposé automatiquement.
        </p>
      </CardContent>
    </Card>
  )
}

/** Deposit / withdraw cash in a modal (kept out of the trade flow). Mounted on
 * demand (keyed) so its state is always fresh — no reset effect needed. */
function CashModal({ portfolioId, currency, kind, onClose, onDone }: {
  portfolioId: string
  currency: Currency
  kind: "deposit" | "withdraw"
  onClose: () => void
  onDone: () => void
}) {
  const [amount, setAmount] = useState("")
  const [date, setDate] = useState(TODAY)
  const [preview, setPreview] = useState<TransactionPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const isDeposit = kind === "deposit"
  const ready = !!amount && Number(amount) > 0

  useEffect(() => {
    let cancelled = false
    const h = setTimeout(async () => {
      if (!ready) {
        setPreview(null)
        return
      }
      try {
        const pv = await api.post<TransactionPreview>(`/portfolios/${portfolioId}/preview/`, { kind, date, amount })
        if (!cancelled) {
          setPreview(pv)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setPreview(null)
          setError(errMsg(e))
        }
      }
    }, ready ? 300 : 0)
    return () => {
      cancelled = true
      clearTimeout(h)
    }
  }, [portfolioId, kind, date, amount, ready])

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/portfolios/${portfolioId}/transactions/`, { kind, date, amount })
      onDone()
      onClose()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={isDeposit ? "Déposer des fonds" : "Retirer des fonds"}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Montant ({currency.toUpperCase()})</Label>
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" inputMode="decimal" autoFocus />
          </div>
          <div className="space-y-1.5">
            <Label>Date</Label>
            <Input type="date" value={date} max={TODAY} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        {preview && (
          <div className="rounded-md bg-secondary/50 p-3 text-sm flex justify-between">
            <span className="text-muted-foreground">Trésorerie après</span>
            <span className="tabular-nums">{formatPrice(preview.cash_after, currency)}</span>
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>Annuler</Button>
          <Button disabled={!ready || busy || !!error} onClick={submit}>
            {isDeposit ? "Déposer" : "Retirer"}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/** Buy or sell a commodity. Buying tops up the missing cash on demand (deposit + buy). */
function TradeCard({ portfolioId, currency, commodities, positions, onDone }: {
  portfolioId: string
  currency: Currency
  commodities: Commodity[]
  positions: PortfolioPosition[]
  onDone: () => void
}) {
  const [mode, setMode] = useState<"buy" | "sell">("buy")
  const [commodity, setCommodity] = useState("")
  const [amount, setAmount] = useState("")
  const [date, setDate] = useState(TODAY)
  const [quote, setQuote] = useState<InvestQuote | null>(null)
  const [preview, setPreview] = useState<TransactionPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const options = useMemo(
    () =>
      mode === "buy"
        ? commodities.map((c) => ({ value: c.slug, label: c.name }))
        : positions.map((p) => ({ value: p.commodity.slug, label: p.commodity.name })),
    [mode, commodities, positions],
  )
  const ready = !!commodity && !!amount && Number(amount) > 0

  const switchMode = (m: "buy" | "sell") => {
    setMode(m)
    setCommodity("")
    setAmount("")
    setQuote(null)
    setPreview(null)
    setError(null)
  }

  // Live preview: buys use invest-quote (with cash shortfall), sells use preview.
  // All state updates happen inside the timeout (never synchronously in the effect).
  useEffect(() => {
    let cancelled = false
    const h = setTimeout(async () => {
      if (!ready) {
        setQuote(null)
        setPreview(null)
        setError(null)
        return
      }
      try {
        if (mode === "buy") {
          const q = await api.post<InvestQuote>(`/portfolios/${portfolioId}/invest-quote/`, { commodity, date, amount })
          if (!cancelled) {
            setQuote(q)
            setError(null)
          }
        } else {
          const pv = await api.post<TransactionPreview>(`/portfolios/${portfolioId}/preview/`, { kind: "sell", commodity, date, amount })
          if (!cancelled) {
            setPreview(pv)
            setError(null)
          }
        }
      } catch (e) {
        if (!cancelled) {
          setQuote(null)
          setPreview(null)
          setError(errMsg(e))
        }
      }
    }, ready ? 350 : 0)
    return () => {
      cancelled = true
      clearTimeout(h)
    }
  }, [portfolioId, mode, commodity, date, amount, ready])

  const shortfall = quote ? Number(quote.shortfall) : 0

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      if (mode === "buy") {
        await api.post(`/portfolios/${portfolioId}/invest/`, { commodity, date, amount, auto_deposit: shortfall > 0 })
      } else {
        await api.post(`/portfolios/${portfolioId}/transactions/`, { kind: "sell", commodity, date, amount })
      }
      setAmount("")
      setQuote(null)
      setPreview(null)
      onDone()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const disabled = !ready || busy || !!error || (mode === "buy" ? !quote : !preview)

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Acheter / Vendre</CardTitle>
        <div className="inline-flex rounded-md border p-0.5 text-xs font-medium">
          {(["buy", "sell"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => switchMode(m)}
              className={`rounded-[5px] px-2.5 py-1 transition-colors cursor-pointer ${
                mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {m === "buy" ? "Achat" : "Vente"}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label>Matière</Label>
          <Combobox
            value={commodity}
            onChange={setCommodity}
            options={options}
            placeholder={mode === "sell" && options.length === 0 ? "Aucune position à vendre" : "— choisir une matière —"}
            disabled={mode === "sell" && options.length === 0}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>{mode === "buy" ? `Montant, frais inclus (${currency.toUpperCase()})` : `Montant à vendre (${currency.toUpperCase()})`}</Label>
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" inputMode="decimal" />
          </div>
          <div className="space-y-1.5">
            <Label>Date</Label>
            <Input type="date" value={date} max={TODAY} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>

        {mode === "buy" && quote && (
          <div className="rounded-md bg-secondary/50 p-3 text-sm space-y-0.5">
            <Row label="Quantité" value={`${qtyFmt(quote.quantity)} @ ${formatPrice(quote.unit_price, currency)}`} />
            <Row label="Frais" value={formatPrice(quote.fee, currency)} />
            <Row label="Trésorerie disponible" value={formatPrice(quote.cash, currency)} />
            {shortfall > 0 && <Row label="Fonds manquants" value={formatPrice(quote.shortfall, currency)} cls="font-medium text-amber-600" />}
          </div>
        )}
        {mode === "sell" && preview && (
          <div className="rounded-md bg-secondary/50 p-3 text-sm space-y-0.5">
            {preview.unit_price && preview.quantity && (
              <Row label="Quantité" value={`${qtyFmt(preview.quantity)} @ ${formatPrice(preview.unit_price, currency)}`} />
            )}
            <Row label="Produit brut" value={formatPrice(preview.amount, currency)} />
            <Row label="Frais" value={formatPrice(preview.fee, currency)} />
            <Row label="Trésorerie après" value={formatPrice(preview.cash_after, currency)} />
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="button" disabled={disabled} onClick={submit}>
          {mode === "sell"
            ? "Vendre"
            : shortfall > 0
              ? `Déposer ${formatPrice(quote?.shortfall ?? "0", currency)} et acheter`
              : "Acheter"}
        </Button>
      </CardContent>
    </Card>
  )
}

function Row({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className={`flex justify-between ${cls ?? ""}`}>
      <span className={cls ? "" : "text-muted-foreground"}>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  )
}

/** Donut + an always-visible legend (color · name · weight) so weights are
 * readable without hovering. */
function CompositionChart({ positions, currency }: { positions: PortfolioPosition[]; currency: Currency }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Composition</CardTitle></CardHeader>
      <CardContent>
        {positions.length > 0 ? (
          <div className="space-y-4">
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={positions.map((pos) => ({ name: pos.commodity.name, value: Number(pos.market_value) }))}
                  dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>
                  {positions.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(val) => formatPrice(Number(val), currency)}
                  contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="space-y-1.5 text-sm">
              {positions.map((pos, i) => (
                <li key={pos.commodity.slug} className="flex items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                  <span className="flex-1 truncate">{pos.commodity.name}</span>
                  <span className="tabular-nums font-medium">{Number(pos.weight).toFixed(1)}%</span>
                  <span className="tabular-nums text-muted-foreground">{formatPrice(pos.market_value, currency)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Aucune position — achetez une matière ci-dessous.</p>
        )}
      </CardContent>
    </Card>
  )
}

const SECTOR_COLORS = PIE_COLORS

function SectorBuy({ portfolioId, currency, sectors, onDone }: {
  portfolioId: string
  currency: Currency
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
  const weight = members.length ? 100 / members.length : 0
  const perAsset = useMemo(() => {
    const n = members.length
    const a = Number(amount)
    return n && a ? a / n : 0
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
      setError(errMsg(e))
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
            <Combobox
              value={sector}
              onChange={setSector}
              options={sectors.map((s) => ({ value: s.slug, label: s.name }))}
              placeholder="— choisir un secteur —"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Date</Label>
            <Input type="date" value={date} max={TODAY} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Montant total, frais inclus ({currency.toUpperCase()})</Label>
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" inputMode="decimal" />
        </div>

        {sector && (
          inSector.isLoading ? (
            <Skeleton className="h-24" />
          ) : members.length === 0 ? (
            <p className="text-xs text-muted-foreground">Aucune matière dans ce secteur.</p>
          ) : (
            <div className="rounded-md border">
              <div className="flex items-center justify-between border-b px-3 py-2 text-xs text-muted-foreground">
                <span>{members.length} matière(s) · réparties à parts égales</span>
                <span>{weight.toFixed(1)}% chacune</span>
              </div>
              <ul className="max-h-44 overflow-y-auto divide-y">
                {members.map((c, i) => (
                  <li key={c.slug} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                    <span className="size-2.5 shrink-0 rounded-sm" style={{ background: SECTOR_COLORS[i % SECTOR_COLORS.length] }} />
                    <span className="flex-1 truncate">{c.name}</span>
                    <span className="tabular-nums text-muted-foreground">{weight.toFixed(1)}%</span>
                    <span className="tabular-nums">{perAsset ? formatPrice(perAsset, currency) : "—"}</span>
                  </li>
                ))}
              </ul>
            </div>
          )
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="button" disabled={!sector || !amount || !members.length || busy} onClick={submit}>Acheter le secteur</Button>
      </CardContent>
    </Card>
  )
}

const KIND_FILTERS = [
  { key: "deposit", label: "Dépôt" },
  { key: "withdraw", label: "Retrait" },
  { key: "buy", label: "Achat" },
  { key: "sell", label: "Vente" },
] as const

const PAGE_SIZE = 10

/** Transactions journal with text search, type filters, sortable amount/fee and pagination. */
function Journal({ currency, txns }: {
  currency: Currency
  txns: PortfolioTransaction[]
}) {
  const [query, setQuery] = useState("")
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [sortKey, setSortKey] = useState<"amount" | "fee" | null>(null)
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")
  const [page, setPage] = useState(0)

  const toggleType = (k: string) => {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
    setPage(0)
  }

  const toggleSort = (key: "amount" | "fee") => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    else {
      setSortKey(key)
      setSortDir("desc")
    }
    setPage(0)
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let rows = txns.filter((t) => !hidden.has(t.kind))
    if (q) {
      rows = rows.filter((t) =>
        [t.kind_display, t.commodity?.name ?? "", t.note ?? "", formatDate(t.date), String(t.amount)]
          .join(" ")
          .toLowerCase()
          .includes(q),
      )
    }
    if (sortKey) {
      rows = [...rows].sort((a, b) => {
        const d = Number(a[sortKey]) - Number(b[sortKey])
        return sortDir === "asc" ? d : -d
      })
    }
    return rows
  }, [txns, query, hidden, sortKey, sortDir])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageRows = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE)

  const sortIcon = (key: "amount" | "fee") =>
    sortKey === key ? (sortDir === "asc" ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />) : null

  return (
    <Card>
      <CardHeader className="space-y-3">
        <CardTitle className="text-base">Journal des transactions</CardTitle>
        <div className="flex flex-wrap items-center gap-3">
          <Input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(0) }}
            placeholder="Rechercher (matière, type, note…)"
            className="h-8 w-full sm:w-64"
          />
          <div className="flex flex-wrap gap-1.5">
            {KIND_FILTERS.map((k) => {
              const active = !hidden.has(k.key)
              return (
                <button
                  key={k.key}
                  type="button"
                  onClick={() => toggleType(k.key)}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${
                    active ? "bg-secondary text-foreground" : "text-muted-foreground line-through opacity-60"
                  }`}
                >
                  {k.label}
                </button>
              )
            })}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucune transaction.</p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Matière</TableHead>
                  <TableHead className="text-right">
                    <button onClick={() => toggleSort("amount")} className="inline-flex items-center gap-1 hover:text-foreground cursor-pointer">
                      Montant {sortIcon("amount")}
                    </button>
                  </TableHead>
                  <TableHead className="text-right">
                    <button onClick={() => toggleSort("fee")} className="inline-flex items-center gap-1 hover:text-foreground cursor-pointer">
                      Frais {sortIcon("fee")}
                    </button>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageRows.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{formatDate(t.date)}</TableCell>
                    <TableCell>{t.kind_display}</TableCell>
                    <TableCell>{t.commodity?.name ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatPrice(t.amount, currency)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatPrice(t.fee, currency)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
              <span>{filtered.length} transaction(s)</span>
              {pageCount > 1 && (
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
                    <ChevronLeft className="size-4" />
                  </Button>
                  <span className="tabular-nums">{safePage + 1} / {pageCount}</span>
                  <Button variant="outline" size="sm" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
