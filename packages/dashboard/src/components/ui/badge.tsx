// packages/dashboard/src/components/ui/badge.tsx
// A badge always carries a text label — colour never conveys meaning alone.
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'
import { SEVERITY_STYLES, normalizeSeverity, type SeverityLevel } from '@/lib/severity'

// Semantic tones are the ones to reach for. The palette names (slate, sky,
// emerald, amber, violet, red) are kept as aliases so existing pages keep
// working while they migrate to the semantic set.
const TONES = {
  neutral: 'bg-surface-alt text-ink-muted border-line',
  info: 'bg-info-soft text-info border-info/25',
  ok: 'bg-ok-soft text-ok border-ok/25',
  warn: 'bg-warn-soft text-warn border-warn/25',
  crit: 'bg-crit-soft text-crit border-crit/25',
  brand: 'bg-brand-soft text-brand border-brand/25',

  slate: 'bg-surface-alt text-ink-muted border-line',
  sky: 'bg-info-soft text-info border-info/25',
  emerald: 'bg-ok-soft text-ok border-ok/25',
  amber: 'bg-warn-soft text-warn border-warn/25',
  violet: 'bg-brand-soft text-brand border-brand/25',
  red: 'bg-crit-soft text-crit border-crit/25',
} as const

export type BadgeTone = keyof typeof TONES

export function Badge({
  children,
  className,
  tone = 'neutral',
}: {
  children: ReactNode
  className?: string
  tone?: BadgeTone
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-micro font-semibold uppercase',
        TONES[tone] ?? TONES.neutral,
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
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-micro font-semibold uppercase',
        style.bg,
        style.border,
        style.text,
        className
      )}
    >
      {showDot && <span className={cn('h-1.5 w-1.5 rounded-full', style.dot)} aria-hidden />}
      {style.label}
    </span>
  )
}
