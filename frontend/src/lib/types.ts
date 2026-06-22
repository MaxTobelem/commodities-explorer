export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface CommodityMini {
  id: number
  name: string
  slug: string
  symbol: string
  category: string
  price_unit?: string
}

export interface Commodity extends CommodityMini {
  category_display: string
  price_unit: string
  image_url: string
  latest_price_usd: string | null
  latest_price_eur: string | null
  latest_price_date: string | null
  latest_price_source: string | null
  sparkline?: number[]
  description?: string
}

export interface Country {
  id: number
  name: string
  iso2: string
  iso3: string
  region: string
}

export interface Sector {
  id: number
  name: string
  slug: string
  nace_code: string
  description?: string
}

export interface Product {
  id: number
  name: string
  slug: string
  image_url: string
  description?: string
}

export interface CommodityEvent {
  id: number
  title: string
  slug: string
  type: string
  type_display?: string
  start_date: string | null
  end_date: string | null
  description?: string
  source_url?: string
}

export interface PriceQuote {
  date: string
  price_usd: string
  price_eur: string | null
  source: string
}

export interface Production {
  commodity: CommodityMini
  country: Country
  year: number
  production_t: string
  unit: string
  note: string
  source: string
}

export interface Reserve {
  commodity: CommodityMini
  country: Country
  year: number
  reserves_t: string
  unit: string
  source: string
}

export interface Usage {
  commodity: CommodityMini
  sector: Sector
  share_percent: string | null
  description: string
  source: string
  needs_review: boolean
}

export interface Composition {
  commodity: CommodityMini
  product: Product
  role: string
  source: string
  needs_review: boolean
}

export interface Impact {
  commodity: CommodityMini
  event: CommodityEvent
  direction: string
  direction_display: string
  magnitude: string | null
  description: string
  source: string
  needs_review: boolean
}

export interface User {
  id: number
  username: string
  email: string
  is_staff: boolean
}

// --- Portfolios (trading simulation) ---------------------------------------

export interface PortfolioSummary {
  currency: string
  cash: string
  total_value: string
  total_pnl: string
  total_pnl_pct: string
}

export interface Portfolio {
  id: number
  name: string
  base_currency: string
  description: string
  fee_percent: string
  fee_fixed: string
  created_at: string
  summary: PortfolioSummary
}

export interface PortfolioTransaction {
  id: number
  date: string
  kind: string
  kind_display: string
  commodity: CommodityMini | null
  amount: string
  quantity: string | null
  unit_price: string | null
  fee: string
  note: string
  created_at: string
}

export interface PortfolioPosition {
  commodity: CommodityMini
  quantity: string
  avg_cost: string
  price: string
  cost_basis: string
  market_value: string
  unrealized_pnl: string
  weight: string
}

export interface PortfolioValuation {
  as_of: string
  currency: string
  cash: string
  invested: string
  positions_value: string
  total_value: string
  net_deposits: string
  realized_pnl: string
  unrealized_pnl: string
  total_pnl: string
  total_pnl_pct: string
  fees_total: string
  positions: PortfolioPosition[]
}

export interface PortfolioHistoryPoint {
  date: string
  value: string
  invested: string
  cash: string
}

export interface TransactionPreview {
  kind: string
  date: string
  amount: string
  quantity: string | null
  unit_price: string | null
  fee: string
  cash_before: string
  cash_after: string
}
