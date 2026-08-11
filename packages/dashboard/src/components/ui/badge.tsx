// packages/dashboard/src/components/ui/badge.tsx
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'
import { SEVERITY_STYLES, normalizeSeverity, type SeverityLevel } from '@/lib/severity'

export function Badge({
  children,
  className,
  tone = 'slate',
}: {
  children: ReactNode
  className?: string
  tone?: 'slate' | 'sky' | 'emerald' | 'amber' | 'violet' | 'red'
}) {
  const tones: Record<string, string> = {
    slate: 'bg-slate-500/10 text-slate-300 border-slate-500/30',
    sky: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
    emerald: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
    amber: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
    violet: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
    red: 'bg-red-500/10 text-red-300 border-red-500/30',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  )
}

/** Severity badge - always includes the label text (never color-only). */
export function SeverityBadge({
  severity,
  className,
  showDot = true,
}: {
  severity: string | null | undefined
  className?: string
  showDot?: boolean
}) {
  const level: SeverityLevel = normalizeSeverity(severity)
  const style = SEVERITY_STYLES[level]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
        style.bg,
        style.border,
        style.text,
        className
      )}
    >
      {showDot && <span className={cn('h-1.5 w-1.5 rounded-full', style.dot)} />}
      {style.label}
    </span>
  )
}
