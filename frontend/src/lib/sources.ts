export interface SourceInfo {
  /** Short label shown inline. */
  label: string
  /** Full name shown on hover (title attribute). */
  full: string
  /** Optional link to the source. */
  url?: string
}

const SOURCE_META: Record<string, SourceInfo> = {
  commodities_api: {
    label: "Commodities-API",
    full: "Commodities-API — cours quotidiens",
    url: "https://commodities-api.com",
  },
  worldbank: {
    label: "World Bank",
    full: "World Bank — Pink Sheet (cours mensuels)",
    url: "https://www.worldbank.org/en/research/commodity-markets",
  },
  usgs: {
    label: "USGS",
    full: "U.S. Geological Survey — Mineral Commodity Summaries",
    url: "https://www.usgs.gov/centers/national-minerals-information-center",
  },
  usgs_price: {
    label: "USGS",
    full: "U.S. Geological Survey",
    url: "https://www.usgs.gov/centers/national-minerals-information-center",
  },
  owid: {
    label: "Our World in Data",
    full: "Our World in Data (FAO, Energy Institute)",
    url: "https://ourworldindata.org",
  },
  gdelt: {
    label: "GDELT",
    full: "The GDELT Project",
    url: "https://www.gdeltproject.org",
  },
  rmis: {
    label: "EU RMIS",
    full: "EU Raw Materials Information System (JRC)",
    url: "https://rmis.jrc.ec.europa.eu",
  },
  curated: {
    label: "curé",
    full: "Données curées — USGS, AIE, FAO, instituts métiers",
  },
  seed: { label: "démo", full: "Données de démonstration" },
}

export function sourceInfo(key?: string | null): SourceInfo {
  if (!key) return { label: "—", full: "Source inconnue" }
  return SOURCE_META[key] ?? { label: key, full: key }
}
