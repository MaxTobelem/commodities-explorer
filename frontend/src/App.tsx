import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AuthProvider, useAuth } from "@/auth"
import { Layout } from "@/components/Layout"
import { CommodityDetail } from "@/pages/CommodityDetail"
import { CountryDetail, EventDetail, ProductDetail, SectorDetail } from "@/pages/EntityDetails"
import { Explorer } from "@/pages/Explorer"
import { Login } from "@/pages/Login"

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
