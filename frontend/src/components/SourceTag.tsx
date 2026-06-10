import { ExternalLink } from "lucide-react"

import { sourceInfo } from "@/lib/sources"

/**
 * Discreet, sourced attribution: short label inline, full source name on hover
 * (native tooltip), and a link out when the source has a URL. Keeps the UI clean.
 */
export function SourceTag({ source, className = "" }: { source?: string | null; className?: string }) {
  if (!source) return null
  const info = sourceInfo(source)
  const base = `inline-flex items-center gap-1 text-xs text-muted-foreground ${className}`
  const body = (
    <>
      <span className="opacity-60">source&nbsp;:</span>
      <span>{info.label}</span>
    </>
  )
  if (info.url) {
    return (
      <a
        href={info.url}
        target="_blank"
        rel="noreferrer"
        title={info.full}
        className={`${base} hover:text-foreground hover:underline`}
      >
        {body}
        <ExternalLink className="size-3 opacity-60" />
      </a>
    )
  }
  return (
    <span className={base} title={info.full}>
      {body}
    </span>
  )
}
