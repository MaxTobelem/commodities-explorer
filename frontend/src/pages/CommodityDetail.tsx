import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, TrendingDown, TrendingUp } from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { Choropleth, type MapDatum } from "@/components/Choropleth"
import { PriceChart } from "@/components/PriceChart"
import { RankBar, type RankItem } from "@/components/RankBar"
import { SourceTag } from "@/components/SourceTag"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { type Currency, formatDate, formatPrice, formatQuantity } from "@/lib/format"
import { api } from "@/lib/api"
import type {
  Commodity,
  Composition,
  Impact,
  PriceQuote,
  Production,
  Reserve,
  Usage,
} from "@/lib/types"

const RANGES = [
  { key: "1m", label: "1M", days: 30 },
  { key: "6m", label: "6M", days: 182 },
  { key: "1y", label: "1A", days: 365 },
  { key: "all", label: "Max", days: 0 },
] as const

export function CommodityDetail() {
  const { slug = "" } = useParams()
  const [currency, setCurrency] = useState<Currency>("usd")
  const [range, setRange] = useState<string>("1y")
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

  const cutoff = RANGES.find((r) => r.key === range)?.days ?? 0
  const filteredPrices = (prices.data ?? []).filter((p) => {
    if (!cutoff) return true
    const limit = new Date()
    limit.setDate(limit.getDate() - cutoff)
    return new Date(p.date) >= limit
  })
  const priceSource = prices.data?.[0]?.source  // latest quote (API ordered by -date)

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
          <div className="text-xs text-muted-foreground">
            {c.price_unit} · {formatDate(c.latest_price_date)}
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
            <ToggleGroup value={range} onChange={setRange} options={RANGES.map((r) => ({ value: r.key, label: r.label }))} />
          </div>
        </CardHeader>
        <CardContent>
          {prices.isLoading ? <Skeleton className="h-[280px]" /> : <PriceChart data={filteredPrices} currency={currency} />}
        </CardContent>
      </Card>

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
