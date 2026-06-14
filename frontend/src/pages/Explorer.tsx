import { useQuery } from "@tanstack/react-query"
import { Search, X } from "lucide-react"
import { Link, useSearchParams } from "react-router-dom"

import { Sparkline } from "@/components/Sparkline"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { formatPrice, formatUnit } from "@/lib/format"
import type {
  Commodity,
  CommodityEvent,
  Country,
  Paginated,
  Product,
  Sector,
} from "@/lib/types"

const ENTITIES = [
  { key: "commodities", label: "Matières" },
  { key: "countries", label: "Pays" },
  { key: "sectors", label: "Secteurs" },
  { key: "products", label: "Produits" },
  { key: "events", label: "Événements" },
] as const

const CATEGORY_OPTIONS = [
  { value: "precious", label: "Métal précieux" },
  { value: "base", label: "Métal de base" },
  { value: "battery", label: "Batteries" },
  { value: "other", label: "Autre" },
]

const EVENT_TYPE_OPTIONS = [
  { value: "war", label: "Conflit / Guerre" },
  { value: "policy", label: "Politique" },
  { value: "disaster", label: "Catastrophe" },
  { value: "economic", label: "Marché" },
  { value: "other", label: "Autre" },
]

const ALL = "__all__"

function useList<T>(path: string) {
  return useQuery({
    queryKey: ["list", path],
    queryFn: () => api.get<Paginated<T>>(path),
    staleTime: Infinity,
  })
}

export function Explorer() {
  const [params, setParams] = useSearchParams()
  const entity = params.get("entity") ?? "commodities"

  const commodities = useList<Commodity>("/commodities/")
  const countries = useList<Country>("/countries/")
  const sectors = useList<Sector>("/sectors/")
  const products = useList<Product>("/products/")
  const events = useList<CommodityEvent>("/events/")

  const setEntity = (key: string) => {
    // Reset filters when switching dimension to avoid confusing carry-over.
    setParams(key === "commodities" ? {} : { entity: key })
  }

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (!value || value === ALL) next.delete(key)
    else next.set(key, value)
    setParams(next)
  }

  const resultsQuery = useQuery({
    queryKey: ["results", entity, params.toString()],
    queryFn: () => api.get<Paginated<unknown>>(buildPath(entity, params)),
  })

  const activeFilters = [...params.entries()].filter(([k]) => k !== "entity")

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Explorer</h1>
        <p className="text-muted-foreground text-sm">
          Filtrez sur n'importe quelle dimension — matières, pays, secteurs, produits, événements.
        </p>
      </div>

      <Tabs value={entity} onValueChange={setEntity}>
        <TabsList className="flex-wrap h-auto">
          {ENTITIES.map((e) => (
            <TabsTrigger key={e.key} value={e.key}>
              {e.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Filter bar (adapts to the active entity) */}
      <div className="flex flex-wrap items-center gap-2">
        {entity === "commodities" && (
          <>
            <FilterSelect
              placeholder="Catégorie"
              value={params.get("category")}
              options={CATEGORY_OPTIONS}
              onChange={(v) => setFilter("category", v)}
            />
            <FilterSelect
              placeholder="Pays"
              value={params.get("country")}
              options={(countries.data?.results ?? []).map((c) => ({ value: c.iso3, label: c.name }))}
              onChange={(v) => setFilter("country", v)}
            />
            <FilterSelect
              placeholder="Secteur"
              value={params.get("sector")}
              options={(sectors.data?.results ?? []).map((s) => ({ value: s.slug, label: s.name }))}
              onChange={(v) => setFilter("sector", v)}
            />
            <FilterSelect
              placeholder="Produit"
              value={params.get("product")}
              options={(products.data?.results ?? []).map((p) => ({ value: p.slug, label: p.name }))}
              onChange={(v) => setFilter("product", v)}
            />
            <FilterSelect
              placeholder="Événement"
              value={params.get("event")}
              options={(events.data?.results ?? []).map((e) => ({ value: e.slug, label: e.title }))}
              onChange={(v) => setFilter("event", v)}
            />
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Rechercher…"
                className="pl-8 w-44"
                defaultValue={params.get("search") ?? ""}
                onChange={(e) => setFilter("search", e.target.value || null)}
              />
            </div>
          </>
        )}
        {(entity === "countries" || entity === "sectors" || entity === "products" || entity === "events") && (
          <FilterSelect
            placeholder="Matière"
            value={params.get("commodity")}
            options={(commodities.data?.results ?? []).map((c) => ({ value: c.slug, label: c.name }))}
            onChange={(v) => setFilter("commodity", v)}
          />
        )}
        {(entity === "products") && (
          <FilterSelect
            placeholder="Secteur"
            value={params.get("sector")}
            options={(sectors.data?.results ?? []).map((s) => ({ value: s.slug, label: s.name }))}
            onChange={(v) => setFilter("sector", v)}
          />
        )}
        {entity === "events" && (
          <FilterSelect
            placeholder="Type"
            value={params.get("type")}
            options={EVENT_TYPE_OPTIONS}
            onChange={(v) => setFilter("type", v)}
          />
        )}

        {activeFilters.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setParams(entity === "commodities" ? {} : { entity })}>
            <X className="size-3.5" /> Réinitialiser
          </Button>
        )}
      </div>

      {/* Results */}
      {resultsQuery.isLoading ? (
        <ResultsSkeleton />
      ) : (
        <Results entity={entity} data={resultsQuery.data?.results ?? []} />
      )}
    </div>
  )
}

function buildPath(entity: string, params: URLSearchParams): string {
  const q = new URLSearchParams()
  const get = (k: string) => params.get(k)
  if (entity === "commodities") {
    for (const k of ["category", "country", "sector", "product", "event", "type", "search"]) {
      const v = get(k)
      if (v) q.set(k, v)
    }
    return `/commodities/?${q}`
  }
  if (entity === "countries") {
    if (get("commodity")) q.set("commodity", get("commodity")!)
    return `/countries/?${q}`
  }
  if (entity === "sectors") {
    if (get("commodity")) q.set("commodity", get("commodity")!)
    return `/sectors/?${q}`
  }
  if (entity === "products") {
    if (get("commodity")) q.set("commodity", get("commodity")!)
    if (get("sector")) q.set("sector", get("sector")!)
    return `/products/?${q}`
  }
  // events
  if (get("commodity")) q.set("commodity", get("commodity")!)
  if (get("type")) q.set("type", get("type")!)
  return `/events/?${q}`
}

function FilterSelect({
  placeholder,
  value,
  options,
  onChange,
}: {
  placeholder: string
  value: string | null
  options: { value: string; label: string }[]
  onChange: (value: string | null) => void
}) {
  return (
    <Select value={value ?? ALL} onValueChange={onChange}>
      <SelectTrigger className="w-40">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{placeholder} : tous</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function Results({ entity, data }: { entity: string; data: unknown[] }) {
  if (data.length === 0) {
    return (
      <div className="grid place-items-center rounded-xl border border-dashed py-16 text-sm text-muted-foreground">
        Aucun résultat pour ces filtres.
      </div>
    )
  }
  if (entity === "commodities") {
    return (
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">Prix actuel · variation et tendance sur 6 mois</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(data as Commodity[]).map((c) => {
          const spark = c.sparkline ?? []
          const change =
            spark.length > 1 && spark[0]
              ? ((spark[spark.length - 1] - spark[0]) / spark[0]) * 100
              : null
          return (
            <Link key={c.slug} to={`/commodity/${c.slug}`}>
              <Card className="h-full transition-colors hover:border-primary/40 hover:bg-accent/40">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-base">{c.name}</CardTitle>
                    <Badge variant="secondary">{c.category_display}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-end justify-between gap-2">
                    <div>
                      <div className="text-2xl font-semibold tabular-nums">
                        {formatPrice(c.latest_price_usd, "usd")}
                        <span className="ml-1.5 text-sm font-normal text-muted-foreground">
                          · {formatUnit(c.price_unit, "usd")}
                        </span>
                      </div>
                      <div className="text-sm text-muted-foreground tabular-nums">
                        {formatPrice(c.latest_price_eur, "eur")} · {formatUnit(c.price_unit, "eur")}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-muted-foreground">{c.symbol}</div>
                      {change != null && (
                        <div
                          className={`text-xs font-medium tabular-nums ${change >= 0 ? "text-emerald-600" : "text-destructive"}`}
                        >
                          {change >= 0 ? "+" : ""}
                          {change.toFixed(1)}%
                        </div>
                      )}
                    </div>
                  </div>
                  {spark.length > 1 && <Sparkline data={spark} className="h-8 w-full" />}
                </CardContent>
              </Card>
            </Link>
          )
        })}
        </div>
      </div>
    )
  }

  const cards: { key: string; to: string; title: string; subtitle?: string; badge?: string }[] =
    entity === "countries"
      ? (data as Country[]).map((c) => ({ key: c.iso3, to: `/country/${c.iso3}`, title: c.name, subtitle: c.region }))
      : entity === "sectors"
        ? (data as Sector[]).map((s) => ({ key: s.slug, to: `/sector/${s.slug}`, title: s.name, subtitle: s.nace_code }))
        : entity === "products"
          ? (data as Product[]).map((p) => ({ key: p.slug, to: `/product/${p.slug}`, title: p.name }))
          : (data as CommodityEvent[]).map((e) => ({
              key: e.slug,
              to: `/event/${e.slug}`,
              title: e.title,
              subtitle: e.start_date ?? undefined,
              badge: e.type_display,
            }))

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((c) => (
        <Link key={c.key} to={c.to}>
          <Card className="h-full transition-colors hover:border-primary/40 hover:bg-accent/40">
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="text-base">{c.title}</CardTitle>
                {c.badge && <Badge variant="secondary">{c.badge}</Badge>}
              </div>
              {c.subtitle && <p className="text-sm text-muted-foreground">{c.subtitle}</p>}
            </CardHeader>
          </Card>
        </Link>
      ))}
    </div>
  )
}

function ResultsSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-28" />
      ))}
    </div>
  )
}
