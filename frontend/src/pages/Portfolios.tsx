import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2, Wallet } from "lucide-react"
import { type MouseEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { type Currency, formatPrice } from "@/lib/format"
import type { Paginated, Portfolio } from "@/lib/types"

function cur(p: Portfolio): Currency {
  return p.base_currency.toLowerCase() as Currency
}

export function Portfolios() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const list = useQuery({
    queryKey: ["portfolios"],
    queryFn: () => api.get<Paginated<Portfolio>>("/portfolios/"),
  })

  const [name, setName] = useState("")
  const [currency, setCurrency] = useState("EUR")
  const [feePercent, setFeePercent] = useState("0.20")
  const [feeFixed, setFeeFixed] = useState("0")
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      api.post<Portfolio>("/portfolios/", {
        name,
        base_currency: currency,
        fee_percent: feePercent,
        fee_fixed: feeFixed,
      }),
    onSuccess: (pf) => {
      qc.invalidateQueries({ queryKey: ["portfolios"] })
      navigate(`/portfolios/${pf.id}`)
    },
    onError: () => setError("Création impossible — vérifie les champs."),
  })

  const remove = useMutation({
    mutationFn: (pid: number) => api.del(`/portfolios/${pid}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolios"] }),
  })

  const onDelete = (e: MouseEvent, p: Portfolio) => {
    e.preventDefault()
    e.stopPropagation()
    if (confirm(`Supprimer le portefeuille « ${p.name} » et toutes ses transactions ?`)) {
      remove.mutate(p.id)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Wallet className="size-5" />
        <h1 className="text-xl font-semibold tracking-tight">Mes portefeuilles</h1>
      </div>

      {/* Create */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nouveau portefeuille</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 items-end"
            onSubmit={(e) => {
              e.preventDefault()
              setError(null)
              if (name.trim()) create.mutate()
            }}
          >
            <div className="space-y-1.5 lg:col-span-2">
              <Label htmlFor="name">Nom</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Métaux industriels" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="currency">Devise</Label>
              <select
                id="currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
              >
                <option value="EUR">Euro (€)</option>
                <option value="USD">Dollar ($)</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="feep">Frais %</Label>
                <Input id="feep" value={feePercent} onChange={(e) => setFeePercent(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="feef">Frais fixe</Label>
                <Input id="feef" value={feeFixed} onChange={(e) => setFeeFixed(e.target.value)} />
              </div>
            </div>
            <div className="sm:col-span-2 lg:col-span-4 flex items-center gap-3">
              <Button type="submit" disabled={!name.trim() || create.isPending}>
                <Plus className="size-4" /> Créer
              </Button>
              {error && <span className="text-sm text-destructive">{error}</span>}
              <span className="text-xs text-muted-foreground">
                Frais par défaut 0,20 % (modifiable) — niveau courtier retail.
              </span>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* List */}
      {list.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (list.data?.results ?? []).length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun portefeuille pour le moment — créez-en un ci-dessus.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(list.data?.results ?? []).map((p) => {
            const pnl = Number(p.summary.total_pnl_pct)
            return (
              <Link key={p.id} to={`/portfolios/${p.id}`} className="group relative block">
                <button
                  type="button"
                  onClick={(e) => onDelete(e, p)}
                  aria-label="Supprimer le portefeuille"
                  className="absolute right-2 top-2 z-10 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-secondary hover:text-destructive group-hover:opacity-100 focus:opacity-100"
                >
                  <Trash2 className="size-4" />
                </button>
                <Card className="h-full transition-colors hover:border-primary/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center justify-between gap-6">
                      <span className="truncate">{p.name}</span>
                      <span className="text-xs font-normal text-muted-foreground shrink-0">{p.base_currency}</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-semibold tabular-nums">
                      {formatPrice(p.summary.total_value, cur(p))}
                    </div>
                    <div className={`text-sm font-medium tabular-nums ${pnl >= 0 ? "text-emerald-600" : "text-destructive"}`}>
                      {pnl >= 0 ? "+" : ""}
                      {pnl.toFixed(1)}% · {formatPrice(p.summary.total_pnl, cur(p))}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
