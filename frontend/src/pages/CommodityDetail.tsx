import { useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, TrendingDown, TrendingUp, Wallet } from "lucide-react"
import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"

import { Choropleth, type MapDatum } from "@/components/Choropleth"
import { PriceChart } from "@/components/PriceChart"
import { RankBar, type RankItem } from "@/components/RankBar"
import { SourceTag } from "@/components/SourceTag"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { type Currency, formatDate, formatPrice, formatQuantity, formatUnit } from "@/lib/format"
import { ApiError, api } from "@/lib/api"
import type {
  Commodity,
  Composition,
  Impact,
  InvestQuote,
  Paginated,
  Portfolio,
  PriceQuote,
  Production,
  Reserve,
  Usage,
} from "@/lib/types"

const RANGES = [
  { key: "1w", label: "1S", days: 7 },
  { key: "1m", label: "1M", days: 30 },
  { key: "6m", label: "6M", days: 182 },
  { key: "1y", label: "1A", days: 365 },
  { key: "all", label: "Max", days: 0 },
] as const

const TODAY = new Date().toISOString().slice(0, 10)

function errMsg(e: unknown): string {
  return e instanceof ApiError
    ? String((e.data as { detail?: string })?.detail ?? "Erreur")
    : "Erreur"
}

export function CommodityDetail() {
  const { slug = "" } = useParams()
  const [currency, setCurrency] = useState<Currency>("usd")
  const [range, setRange] = useState<string | null>(null)  // null = auto (cadence-based)
  const [geo, setGeo] = useState<"production" | "reserves">("production")

  const commodity = useQuery({
    queryKey: ["commodity", slug],
    queryFn: () => api.get<Commodity>(`/commodities/${slug}/`),
  })
  const prices = useQuery({
    queryKey: ["commodity", slug, "prices"],
    queryFn: () => api.get<PriceQuote[]>(`/commodities/${slug}/prices/`),
  })
  const production = useQuery({
    queryKey: ["commodity", slug, "production"],
    queryFn: () => api.get<Production[]>(`/commodities/${slug}/production/`),
  })
  const reserves = useQuery({
    queryKey: ["commodity", slug, "reserves"],
    queryFn: () => api.get<Reserve[]>(`/commodities/${slug}/reserves/`),
  })
  const usages = useQuery({
    queryKey: ["commodity", slug, "usages"],
    queryFn: () => api.get<Usage[]>(`/commodities/${slug}/usages/`),
  })
  const products = useQuery({
    queryKey: ["commodity", slug, "products"],
    queryFn: () => api.get<Composition[]>(`/commodities/${slug}/products/`),
  })
  const events = useQuery({
    queryKey: ["commodity", slug, "events"],
    queryFn: () => api.get<Impact[]>(`/commodities/${slug}/events/`),
  })

  if (commodity.isLoading) return <Skeleton className="h-64 w-full" />
  if (!commodity.data) return <p>Matière introuvable.</p>
  const c = commodity.data

  const allPrices = prices.data ?? []
  // Anchor the window on the latest available point, not "today", so a series that
  // ends in the past (e.g. monthly World Bank data, last point months ago) still
  // renders its recent history instead of an empty chart.
  const anchorMs = allPrices.reduce((m, p) => Math.max(m, new Date(p.date).getTime()), 0)
  const anchor = anchorMs ? new Date(anchorMs) : new Date()
  // Default scale adapts to the data's cadence: 1 week for daily-priced commodities
  // (enough recent points for a useful week view), else 1 month — a monthly series
  // would be near-empty at 1 week. An explicit user choice (range) always wins.
  const weekAgo = new Date(anchor)
  weekAgo.setDate(weekAgo.getDate() - 7)
  const isDaily = allPrices.filter((p) => new Date(p.date) >= weekAgo).length >= 2
  const effectiveRange = range ?? (isDaily ? "1w" : "1m")
  const cutoff = RANGES.find((r) => r.key === effectiveRange)?.days ?? 0
  const filteredPrices = allPrices.filter((p) => {
    if (!cutoff) return true
    const limit = new Date(anchor)
    limit.setDate(limit.getDate() - cutoff)
    return new Date(p.date) >= limit
  })
  // Source of the *current* price = the annotated newest quote (not the oldest point).
  const priceSource = c.latest_price_source
  // Sources actually present in the visible series (history + daily may differ).
  const chartSources = Array.from(new Set(filteredPrices.map((p) => p.source)))
  // % change over the visible window, in the selected currency (same idea as the cards).
  const rangeValues = filteredPrices
    .map((p) => (currency === "usd" ? Number(p.price_usd) : p.price_eur ? Number(p.price_eur) : null))
    .filter((v): v is number => v !== null && !Number.isNaN(v))
  const changePct =
    rangeValues.length > 1 && rangeValues[0]
      ? ((rangeValues[rangeValues.length - 1] - rangeValues[0]) / rangeValues[0]) * 100
      : null

  const geoMap: MapDatum[] =
    geo === "production"
      ? latestYearData(production.data ?? [], (r) => Number(r.production_t), (r) => r.country)
      : latestYearData(reserves.data ?? [], (r) => Number(r.reserves_t), (r) => r.country)
  const geoRows: RankItem[] = geoMap
    .slice(0, 8)
    .map((d) => ({ label: d.name, value: d.value, href: `/country/${d.iso3}` }))
  const geoUnit =
    geo === "production"
      ? (production.data?.[0]?.unit ?? "t")
      : (reserves.data?.[0]?.unit ?? "t")
  const geoData = geo === "production" ? (production.data ?? []) : (reserves.data ?? [])
  const geoYear = Math.max(0, ...geoData.map((r) => r.year))
  const geoBasis =
    geo === "production" ? (production.data?.[0]?.note ?? "Production") : "Réserves prouvées"
  const geoSource = geoData[0]?.source

  const sectorRows: RankItem[] = (usages.data ?? [])
    .filter((u) => u.share_percent !== null)
    .map((u) => ({
      label: u.sector.name,
      value: Number(u.share_percent),
      href: `/sector/${u.sector.slug}`,
    }))

  return (
    <div className="space-y-5">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Explorer
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{c.name}</h1>
            <Badge variant="secondary">{c.category_display}</Badge>
            {c.symbol && <Badge variant="outline">{c.symbol}</Badge>}
          </div>
          {c.description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{c.description}</p>}
        </div>
        <div className="text-right">
          <div className="text-3xl font-semibold tabular-nums">
            {formatPrice(currency === "usd" ? c.latest_price_usd : c.latest_price_eur, currency)}
          </div>
          {changePct != null && (
            <div
              className={`text-sm font-medium tabular-nums ${changePct >= 0 ? "text-emerald-600" : "text-destructive"}`}
            >
              {changePct >= 0 ? "+" : ""}
              {changePct.toFixed(1)}%{" "}
              <span className="font-normal text-muted-foreground">
                · {RANGES.find((r) => r.key === effectiveRange)?.label}
              </span>
            </div>
          )}
          <div className="text-xs text-muted-foreground">
            {formatUnit(c.price_unit, currency)} · {formatDate(c.latest_price_date)}
          </div>
          <div className="mt-1 flex justify-end">
            <SourceTag source={priceSource} />
          </div>
        </div>
      </div>

      {/* Price chart */}
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Cours</CardTitle>
          <div className="flex items-center gap-2">
            <ToggleGroup
              value={currency}
              onChange={(v) => setCurrency(v as Currency)}
              options={[
                { value: "usd", label: "USD" },
                { value: "eur", label: "EUR" },
              ]}
            />
            <ToggleGroup value={effectiveRange} onChange={setRange} options={RANGES.map((r) => ({ value: r.key, label: r.label }))} />
          </div>
        </CardHeader>
        <CardContent>
          {prices.isLoading ? <Skeleton className="h-[280px]" /> : <PriceChart data={filteredPrices} currency={currency} />}
          {chartSources.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              {chartSources.map((src) => (
                <SourceTag key={src} source={src} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Invest directly into one of the user's portfolios */}
      <InvestCard slug={c.slug} name={c.name} />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Geography */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">
              {geo === "production" ? "Principaux producteurs" : "Principales réserves"}
            </CardTitle>
            <ToggleGroup
              value={geo}
              onChange={(v) => setGeo(v as "production" | "reserves")}
              options={[
                { value: "production", label: "Production" },
                { value: "reserves", label: "Réserves" },
              ]}
            />
          </CardHeader>
          <CardContent>
            {geoMap.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <span>
                  {geoBasis}
                  {geoYear > 0 ? ` · ${geoYear}` : ""}
                </span>
                <SourceTag source={geoSource} />
              </div>
            )}
            <Choropleth data={geoMap} format={(n) => formatQuantity(n, geoUnit)} />
            <div className="mt-4">
              <RankBar items={geoRows} format={(n) => formatQuantity(n, geoUnit)} />
            </div>
          </CardContent>
        </Card>

        {/* Sectors */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Secteurs d'usage</CardTitle>
            <SourceTag source={usages.data?.[0]?.source} />
          </CardHeader>
          <CardContent>
            <RankBar items={sectorRows} format={(n) => `${n.toLocaleString("fr-FR")} %`} />
          </CardContent>
        </Card>

        {/* Products */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Produits du quotidien</CardTitle>
            <SourceTag source={products.data?.[0]?.source} />
          </CardHeader>
          <CardContent>
            {(products.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucun produit référencé.</p>
            ) : (
              <ul className="space-y-2">
                {(products.data ?? []).map((p) => (
                  <li key={p.product.slug} className="flex items-center justify-between gap-3 text-sm">
                    <Link to={`/product/${p.product.slug}`} className="font-medium hover:underline">
                      {p.product.name}
                    </Link>
                    <span className="text-muted-foreground truncate">{p.role}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Events */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Événements & impacts</CardTitle>
            <SourceTag source={events.data?.[0]?.source} />
          </CardHeader>
          <CardContent>
            {(events.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucun événement référencé.</p>
            ) : (
              <ul className="space-y-3">
                {(events.data ?? []).map((im) => (
                  <li key={im.event.slug} className="flex items-start justify-between gap-3">
                    <div>
                      <Link to={`/event/${im.event.slug}`} className="text-sm font-medium hover:underline">
                        {im.event.title}
                      </Link>
                      <div className="text-xs text-muted-foreground">{formatDate(im.event.start_date)}</div>
                    </div>
                    <ImpactBadge direction={im.direction} label={im.direction_display} magnitude={im.magnitude} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function latestYearData<T>(
  rows: T[],
  value: (r: T) => number,
  country: (r: T) => { name: string; iso3: string },
): MapDatum[] {
  const latestYear = Math.max(0, ...rows.map((r) => (r as { year: number }).year))
  return rows
    .filter((r) => (r as { year: number }).year === latestYear)
    .map((r) => ({ iso3: country(r).iso3, name: country(r).name, value: value(r) }))
    .sort((a, b) => b.value - a.value)
}

function ToggleGroup({
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

/** Buy this commodity into one of the user's portfolios, topping up the missing
 * cash (with confirmation) when the portfolio is short. */
function InvestCard({ slug, name }: { slug: string; name: string }) {
  const qc = useQueryClient()
  const portfolios = useQuery({
    queryKey: ["portfolios"],
    queryFn: () => api.get<Paginated<Portfolio>>("/portfolios/"),
  })
  const list = portfolios.data?.results ?? []
  const [pfId, setPfId] = useState("")
  const [amount, setAmount] = useState("")
  const [date, setDate] = useState(TODAY)
  const [quote, setQuote] = useState<InvestQuote | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [doneId, setDoneId] = useState<string | null>(null)

  // Default to the first portfolio once the list loads.
  useEffect(() => {
    if (!pfId && list.length) setPfId(String(list[0].id))
  }, [list, pfId])

  const pf = list.find((p) => String(p.id) === pfId)
  const currency = (pf?.base_currency.toLowerCase() ?? "eur") as Currency
  const ready = !!pfId && !!amount && Number(amount) > 0

  // Debounced quote: unit price, quantity, fees and cash shortfall as the user types.
  useEffect(() => {
    setDoneId(null)
    if (!ready) {
      setQuote(null)
      setError(null)
      return
    }
    let cancelled = false
    const handle = setTimeout(async () => {
      try {
        const q = await api.post<InvestQuote>(`/portfolios/${pfId}/invest-quote/`, {
          commodity: slug, date, amount,
        })
        if (!cancelled) {
          setQuote(q)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setQuote(null)
          setError(errMsg(e))
        }
      }
    }, 350)
    return () => {
      cancelled = true
      clearTimeout(handle)
    }
  }, [pfId, slug, date, amount, ready])

  const invest = async (autoDeposit: boolean) => {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/portfolios/${pfId}/invest/`, {
        commodity: slug, date, amount, auto_deposit: autoDeposit,
      })
      qc.invalidateQueries({ queryKey: ["portfolio", pfId] })
      qc.invalidateQueries({ queryKey: ["portfolios"] })
      setAmount("")
      setQuote(null)
      setDoneId(pfId)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const shortfall = quote ? Number(quote.shortfall) : 0
  const cur = currency.toUpperCase()
  const disabled = !ready || busy || !!error || !quote

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base flex items-center gap-2">
          <Wallet className="size-4" /> Investir dans un portefeuille
        </CardTitle>
      </CardHeader>
      <CardContent>
        {portfolios.isLoading ? (
          <Skeleton className="h-20" />
        ) : list.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Vous n'avez pas encore de portefeuille.{" "}
            <Link to="/portfolios" className="underline">Créez-en un</Link> pour investir directement.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label>Portefeuille</Label>
                <select value={pfId} onChange={(e) => setPfId(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm">
                  {list.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.base_currency})</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>Montant, frais inclus ({cur})</Label>
                <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Ex. 1000" inputMode="decimal" />
              </div>
              <div className="space-y-1.5">
                <Label>Date</Label>
                <Input type="date" value={date} max={TODAY} onChange={(e) => setDate(e.target.value)} />
              </div>
            </div>

            {quote && (
              <div className="rounded-md bg-secondary/50 p-3 text-sm space-y-0.5">
                <div className="flex justify-between"><span className="text-muted-foreground">Quantité</span>
                  <span className="tabular-nums">{Number(quote.quantity).toLocaleString("fr-FR", { maximumFractionDigits: 4 })} @ {formatPrice(quote.unit_price, currency)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Frais</span>
                  <span className="tabular-nums">{formatPrice(quote.fee, currency)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Trésorerie disponible</span>
                  <span className="tabular-nums">{formatPrice(quote.cash, currency)}</span></div>
                {shortfall > 0 && (
                  <div className="flex justify-between font-medium text-amber-600"><span>Fonds manquants</span>
                    <span className="tabular-nums">{formatPrice(quote.shortfall, currency)}</span></div>
                )}
              </div>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
            {doneId && (
              <p className="text-sm text-emerald-600">
                Investissement enregistré.{" "}
                <Link to={`/portfolios/${doneId}`} className="underline">Voir le portefeuille</Link>
              </p>
            )}

            {shortfall > 0 ? (
              <Button type="button" disabled={disabled} onClick={() => invest(true)}>
                Déposer {formatPrice(quote?.shortfall ?? "0", currency)} et acheter
              </Button>
            ) : (
              <Button type="button" disabled={disabled} onClick={() => invest(false)}>
                Acheter {name}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ImpactBadge({
  direction,
  label,
  magnitude,
}: {
  direction: string
  label: string
  magnitude: string | null
}) {
  const up = direction === "up"
  const down = direction === "down"
  return (
    <Badge variant={up ? "destructive" : down ? "default" : "secondary"} className="shrink-0 gap-1">
      {up && <TrendingUp className="size-3" />}
      {down && <TrendingDown className="size-3" />}
      {label}
      {magnitude && ` ${magnitude}%`}
    </Badge>
  )
}
