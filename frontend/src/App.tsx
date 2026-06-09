import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { lazy, type ReactNode } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AuthProvider, useAuth } from "@/auth"
import { Layout } from "@/components/Layout"
import { Login } from "@/pages/Login"

// Lazy-loaded routes: recharts and the d3/topojson map only load on the pages
// that use them, keeping the initial bundle small.
const Explorer = lazy(() => import("@/pages/Explorer").then((m) => ({ default: m.Explorer })))
const Compare = lazy(() => import("@/pages/Compare").then((m) => ({ default: m.Compare })))
const CommodityDetail = lazy(() =>
  import("@/pages/CommodityDetail").then((m) => ({ default: m.CommodityDetail })),
)
const CountryDetail = lazy(() =>
  import("@/pages/EntityDetails").then((m) => ({ default: m.CountryDetail })),
)
const SectorDetail = lazy(() =>
  import("@/pages/EntityDetails").then((m) => ({ default: m.SectorDetail })),
)
const ProductDetail = lazy(() =>
  import("@/pages/EntityDetails").then((m) => ({ default: m.ProductDetail })),
)
const EventDetail = lazy(() =>
  import("@/pages/EntityDetails").then((m) => ({ default: m.EventDetail })),
)

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="grid min-h-svh place-items-center text-sm text-muted-foreground">
        Chargement…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Explorer />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/commodity/:slug" element={<CommodityDetail />} />
        <Route path="/country/:iso3" element={<CountryDetail />} />
        <Route path="/sector/:slug" element={<SectorDetail />} />
        <Route path="/product/:slug" element={<ProductDetail />} />
        <Route path="/event/:slug" element={<EventDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
