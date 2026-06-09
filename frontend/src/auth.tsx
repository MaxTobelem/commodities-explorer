import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

import { api } from "@/lib/api"
import type { User } from "@/lib/types"

interface AuthContextValue {
  user: User | null
  loading: boolean
  requestCode: (email: string) => Promise<void>
  verifyCode: (email: string, code: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // GET /auth/me also sets the CSRF cookie (ensure_csrf_cookie) for later POSTs.
    api
      .get<User>("/auth/me/")
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const requestCode = async (email: string) => {
    await api.post("/auth/request-code/", { email })
  }

  const verifyCode = async (email: string, code: string) => {
    const u = await api.post<User>("/auth/verify-code/", { email, code })
    setUser(u)
  }

  const logout = async () => {
    await api.post("/auth/logout/")
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, requestCode, verifyCode, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
