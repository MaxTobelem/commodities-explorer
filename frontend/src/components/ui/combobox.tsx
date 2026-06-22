import { Check, ChevronDown } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { cn } from "@/lib/utils"

export interface ComboOption {
  value: string
  label: string
}

/** Lightweight searchable select (select2-style): a trigger that opens a panel
 * with a text filter and a scrollable, keyboard-navigable list. No extra deps. */
export function Combobox({
  value,
  onChange,
  options,
  placeholder = "— choisir —",
  searchPlaceholder = "Rechercher…",
  disabled,
  className,
}: {
  value: string
  onChange: (v: string) => void
  options: ComboOption[]
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = options.find((o) => o.value === value)
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
  }, [options, query])

  // Focus the filter input and wire up click-outside while open (no setState here).
  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => inputRef.current?.focus(), 0)
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => {
      clearTimeout(t)
      document.removeEventListener("mousedown", onDoc)
    }
  }, [open])

  const toggle = () => {
    if (!open) {
      setQuery("")
      setActive(0)
    }
    setOpen((o) => !o)
  }

  const choose = (v: string) => {
    onChange(v)
    setOpen(false)
  }

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={toggle}
        className="flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
      >
        <span className={cn("line-clamp-1 text-left", !selected && "text-muted-foreground")}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown className="size-4 shrink-0 opacity-50" />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover text-popover-foreground shadow-md">
          <div className="p-1">
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setActive(0)
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault()
                  setActive((a) => Math.min(a + 1, filtered.length - 1))
                } else if (e.key === "ArrowUp") {
                  e.preventDefault()
                  setActive((a) => Math.max(a - 1, 0))
                } else if (e.key === "Enter") {
                  e.preventDefault()
                  if (filtered[active]) choose(filtered[active].value)
                } else if (e.key === "Escape") {
                  setOpen(false)
                }
              }}
              placeholder={searchPlaceholder}
              className="flex h-8 w-full rounded-sm bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="max-h-60 overflow-y-auto p-1 pt-0">
            {filtered.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">Aucun résultat.</div>
            ) : (
              filtered.map((o, i) => (
                <button
                  key={o.value}
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(o.value)}
                  className={cn(
                    "flex w-full cursor-pointer items-center justify-between rounded-sm px-2 py-1.5 text-left text-sm",
                    i === active && "bg-accent text-accent-foreground",
                  )}
                >
                  <span className="line-clamp-1">{o.label}</span>
                  {o.value === value && <Check className="size-4 shrink-0" />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
