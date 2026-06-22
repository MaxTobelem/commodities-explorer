import { Boxes } from "lucide-react"
import { Suspense } from "react"
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom"

import { useAuth } from "@/auth"
import { Button } from "@/components/ui/button"

const navCls = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 transition-colors ${
    isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
  }`

export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-svh flex flex-col">
      <header className="border-b sticky top-0 z-40 bg-background/80 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 h-14 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <Boxes className="size-5" />
            <span>Matières premières</span>
          </Link>
          <nav className="hidden sm:flex items-center gap-1 text-sm">
            <NavLink to="/" end className={navCls}>
              Explorer
            </NavLink>
            <NavLink to="/compare" className={navCls}>
              Comparer
            </NavLink>
            <NavLink to="/portfolios" className={navCls}>
              Portefeuilles
            </NavLink>
          </nav>
          <div className="flex items-center gap-3">
            {user && (
              <span className="text-sm text-muted-foreground hidden md:inline">{user.email}</span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await logout()
                navigate("/login")
              }}
            >
              Se déconnecter
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl w-full px-4 py-6 flex-1">
        <Suspense
          fallback={<div className="py-16 text-center text-sm text-muted-foreground">Chargement…</div>}
        >
          <Outlet />
        </Suspense>
      </main>
    </div>
  )
}
