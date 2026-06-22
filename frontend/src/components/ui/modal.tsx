import { X } from "lucide-react"
import { type ReactNode, useEffect } from "react"
import { createPortal } from "react-dom"

import { cn } from "@/lib/utils"

/** Minimal accessible modal dialog (portal + overlay), no extra deps. */
export function Modal({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  className?: string
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className={cn("relative z-10 w-full max-w-md rounded-lg border bg-background p-5 shadow-lg", className)}>
        {title && (
          <div className="mb-4 flex items-center justify-between gap-4">
            <h2 className="text-base font-semibold">{title}</h2>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Fermer">
              <X className="size-4" />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  )
}
