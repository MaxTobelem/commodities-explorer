import { Link } from "react-router-dom"

export interface RankItem {
  label: string
  value: number
  href?: string
  suffix?: string
}

export function RankBar({
  items,
  format,
}: {
  items: RankItem[]
  format: (n: number) => string
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Aucune donnée.</p>
  }
  const max = Math.max(...items.map((i) => i.value), 1)
  return (
    <div className="space-y-2.5">
      {items.map((item) => (
        <div key={item.label} className="space-y-1">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate">
              {item.href ? (
                <Link to={item.href} className="hover:underline">
                  {item.label}
                </Link>
              ) : (
                item.label
              )}
              {item.suffix && <span className="text-muted-foreground"> · {item.suffix}</span>}
            </span>
            <span className="tabular-nums text-muted-foreground">{format(item.value)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.max((item.value / max) * 100, 2)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
