import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, TrendingDown, TrendingUp } from "lucide-react"
import type { ReactNode } from "react"
import { Link, useParams } from "react-router-dom"

import { RankBar, type RankItem } from "@/components/RankBar"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { formatDate, formatTonnes } from "@/lib/format"
import type {
  CommodityEvent,
  Composition,
  Country,
  Impact,
  Product,
  Production,
  Reserve,
  Sector,
  Usage,
} from "@/lib/types"

function BackLink() {
  return (
    <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Explorer
    </Link>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function commodityRows(
  rows: { commodity: { name: string; slug: string } }[],
  value: (r: never) => number,
): RankItem[] {
  return rows
    .map((r) => ({ label: r.commodity.name, value: value(r as never), href: `/commodity/${r.commodity.slug}` }))
    .sort((a, b) => b.value - a.value)
}

export function CountryDetail() {
  const { iso3 = "" } = useParams()
  const country = useQuery({ queryKey: ["country", iso3], queryFn: () => api.get<Country>(`/countries/${iso3}/`) })
  const production = useQuery({
    queryKey: ["country", iso3, "production"],
    queryFn: () => api.get<Production[]>(`/countries/${iso3}/production/`),
  })
  const reserves = useQuery({
    queryKey: ["country", iso3, "reserves"],
    queryFn: () => api.get<Reserve[]>(`/countries/${iso3}/reserves/`),
  })

  if (country.isLoading) return <Skeleton className="h-48" />
  if (!country.data) return <p>Pays introuvable.</p>

  return (
    <div className="space-y-5">
      <BackLink />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{country.data.name}</h1>
        <p className="text-sm text-muted-foreground">
          {country.data.region} · {country.data.iso3}
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Matières produites">
          <RankBar items={commodityRows(production.data ?? [], (r: Production) => Number(r.production_t))} format={formatTonnes} />
        </Section>
        <Section title="Réserves détenues">
          <RankBar items={commodityRows(reserves.data ?? [], (r: Reserve) => Number(r.reserves_t))} format={formatTonnes} />
        </Section>
      </div>
    </div>
  )
}

export function SectorDetail() {
  const { slug = "" } = useParams()
  const sector = useQuery({ queryKey: ["sector", slug], queryFn: () => api.get<Sector>(`/sectors/${slug}/`) })
  const usages = useQuery({
    queryKey: ["sector", slug, "commodities"],
    queryFn: () => api.get<Usage[]>(`/sectors/${slug}/commodities/`),
  })

  if (sector.isLoading) return <Skeleton className="h-48" />
  if (!sector.data) return <p>Secteur introuvable.</p>

  const rows: RankItem[] = (usages.data ?? [])
    .map((u) => ({ label: u.commodity.name, value: Number(u.share_percent ?? 0), href: `/commodity/${u.commodity.slug}` }))
    .sort((a, b) => b.value - a.value)

  return (
    <div className="space-y-5">
      <BackLink />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{sector.data.name}</h1>
        {sector.data.nace_code && <p className="text-sm text-muted-foreground">NACE {sector.data.nace_code}</p>}
      </div>
      <Section title="Matières utilisées dans ce secteur">
        <RankBar items={rows} format={(n) => `${n.toLocaleString("fr-FR")} %`} />
      </Section>
    </div>
  )
}

export function ProductDetail() {
  const { slug = "" } = useParams()
  const product = useQuery({ queryKey: ["product", slug], queryFn: () => api.get<Product>(`/products/${slug}/`) })
  const compositions = useQuery({
    queryKey: ["product", slug, "commodities"],
    queryFn: () => api.get<Composition[]>(`/products/${slug}/commodities/`),
  })

  if (product.isLoading) return <Skeleton className="h-48" />
  if (!product.data) return <p>Produit introuvable.</p>

  return (
    <div className="space-y-5">
      <BackLink />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{product.data.name}</h1>
        {product.data.description && <p className="text-sm text-muted-foreground">{product.data.description}</p>}
      </div>
      <Section title="Matières premières qui le composent">
        {(compositions.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucune matière référencée.</p>
        ) : (
          <ul className="space-y-2">
            {(compositions.data ?? []).map((comp) => (
              <li key={comp.commodity.slug} className="flex items-center justify-between gap-3 text-sm">
                <Link to={`/commodity/${comp.commodity.slug}`} className="font-medium hover:underline">
                  {comp.commodity.name}
                </Link>
                <span className="text-muted-foreground truncate">{comp.role}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}

export function EventDetail() {
  const { slug = "" } = useParams()
  const event = useQuery({ queryKey: ["event", slug], queryFn: () => api.get<CommodityEvent>(`/events/${slug}/`) })
  const impacts = useQuery({
    queryKey: ["event", slug, "commodities"],
    queryFn: () => api.get<Impact[]>(`/events/${slug}/commodities/`),
  })

  if (event.isLoading) return <Skeleton className="h-48" />
  if (!event.data) return <p>Événement introuvable.</p>

  return (
    <div className="space-y-5">
      <BackLink />
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{event.data.title}</h1>
        {event.data.type_display && <Badge variant="secondary">{event.data.type_display}</Badge>}
      </div>
      <p className="text-sm text-muted-foreground">{formatDate(event.data.start_date)}</p>
      {event.data.description && <p className="max-w-2xl text-sm">{event.data.description}</p>}
      <Section title="Matières impactées">
        {(impacts.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucune matière impactée référencée.</p>
        ) : (
          <ul className="space-y-3">
            {(impacts.data ?? []).map((im) => (
              <li key={im.commodity.slug} className="flex items-center justify-between gap-3">
                <Link to={`/commodity/${im.commodity.slug}`} className="text-sm font-medium hover:underline">
                  {im.commodity.name}
                </Link>
                <Badge
                  variant={im.direction === "up" ? "destructive" : im.direction === "down" ? "default" : "secondary"}
                  className="gap-1"
                >
                  {im.direction === "up" && <TrendingUp className="size-3" />}
                  {im.direction === "down" && <TrendingDown className="size-3" />}
                  {im.direction_display}
                  {im.magnitude && ` ${im.magnitude}%`}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
