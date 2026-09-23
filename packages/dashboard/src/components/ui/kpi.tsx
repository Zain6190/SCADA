// packages/dashboard/src/components/ui/kpi.tsx
// A reading, not a marketing stat: monospace tabular figures so the number
// does not shift width when it refreshes, and an optional severity rail on
// the left edge when the value needs attention.
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'
import { SEVERITY_STYLES, normalizeSeverity } from '@/lib/severity'

export function KpiCard({
  label,
  value,
  detail,
  icon: Icon,
  accent,
  trend,
  severity,
  onClick,
  footer,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  icon?: LucideIcon
  accent?: string
  trend?: { value: string; positive?: boolean; neutral?: boolean }
  /** Draws a coloured rail on the left edge for at-risk readings. */
  severity?: string | null
  onClick?: () => void
  footer?: ReactNode
}) {
  const level = severity ? normalizeSeverity(severity) : null
  const rail = level && level !== 'Normal' ? SEVERITY_STYLES[level].dot.replace('bg-', 'border-l-') : null

  return (
    <div
      onClick={onClick}
      className={cn(
        'rounded-lg border border-line bg-surface p-4 shadow-card transition-colors',
        rail && 'border-l-[3px]',
        rail,
        onClick && 'cursor-pointer hover:border-brand/40'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-micro font-semibold uppercase text-ink-subtle">{label}</p>
          <p className="mt-2.5 truncate font-mono text-metric font-semibold tabular-nums text-ink">{value}</p>
        </div>
        {Icon && (
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded',
              accent || 'bg-brand-soft text-brand'
            )}
          >
            <Icon className="h-4.5 w-4.5" />
          </div>
        )}
      </div>
      {trend && (
        <div className="mt-2 flex items-center gap-2">
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-caption font-semibold',
              trend.neutral
                ? 'bg-surface-alt text-ink-muted'
                : trend.positive
                  ? 'bg-ok-soft text-ok'
                  : 'bg-crit-soft text-crit'
            )}
          >
            {trend.value}
          </span>
        </div>
      )}
      {detail && <p className="mt-2 text-caption leading-5 text-ink-subtle">{detail}</p>}
      {footer}
    </div>
  )
}
