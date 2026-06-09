import { geoNaturalEarth1, geoPath } from "d3-geo"
import { useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { feature } from "topojson-client"
import worldData from "world-atlas/countries-110m.json"

import { ISO3_TO_NUM } from "@/lib/countryCodes"

export interface MapDatum {
  iso3: string
  name: string
  value: number
}

const W = 800
const H = 388

// Precompute features and projected paths once (module-level, shared).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const topo = worldData as any
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const features = (feature(topo, topo.objects.countries) as any).features as any[]
const projection = geoNaturalEarth1().fitSize([W, H], { type: "Sphere" })
const pathGen = geoPath(projection)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const PATHS = features.map((f: any) => ({ id: String(f.id), d: pathGen(f) ?? "" }))

function fillFor(value: number, max: number): string {
  const t = 0.2 + 0.8 * Math.sqrt(Math.max(value, 0) / max)
  return `color-mix(in oklab, var(--color-primary) ${Math.round(t * 100)}%, var(--color-secondary))`
}

export function Choropleth({
  data,
  format,
}: {
  data: MapDatum[]
  format: (n: number) => string
}) {
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<{ left: number; top: number; text: string } | null>(null)

  const byNum = useMemo(() => {
    const m = new Map<string, MapDatum>()
    for (const d of data) {
      const num = ISO3_TO_NUM[d.iso3]
      if (num) m.set(num, d)
    }
    return m
  }, [data])

  const max = useMemo(() => Math.max(...data.map((d) => d.value), 1), [data])

  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">Aucune donnée géographique.</p>
  }

  return (
    <div ref={containerRef} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Carte">
        {PATHS.map((p) => {
          const datum = byNum.get(p.id)
          return (
            <path
              key={p.id}
              d={p.d}
              fill={datum ? fillFor(datum.value, max) : "var(--color-muted)"}
              stroke="var(--color-background)"
              strokeWidth={0.4}
              className={datum ? "cursor-pointer hover:opacity-80" : ""}
              onMouseMove={(e) => {
                if (!datum) return
                const rect = containerRef.current?.getBoundingClientRect()
                if (!rect) return
                setTip({
                  left: e.clientX - rect.left,
                  top: e.clientY - rect.top,
                  text: `${datum.name} · ${format(datum.value)}`,
                })
              }}
              onMouseLeave={() => setTip(null)}
              onClick={() => datum && navigate(`/country/${datum.iso3}`)}
            />
          )
        })}
      </svg>
      {tip && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border bg-popover px-2 py-1 text-xs shadow-md"
          style={{ left: tip.left, top: tip.top - 6 }}
        >
          {tip.text}
        </div>
      )}
    </div>
  )
}
