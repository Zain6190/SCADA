// packages/dashboard/src/components/ui/kpi.tsx
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

export function KpiCard({
  label,
  value,
  detail,
  icon: Icon,
  accent,
  trend,
  onClick,
  footer,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  icon?: LucideIcon
  accent?: string
  trend?: { value: string; positive?: boolean; neutral?: boolean }
  onClick?: () => void
  footer?: ReactNode
}) {
  const accentCls =
    accent ||
    (Icon ? 'bg-sky-500/10 text-sky-300' : 'bg-slate-500/10 text-slate-300')

  return (
    <div
      onClick={onClick}
      className={cn(
        'rounded-2xl border border-slate-800/80 bg-slate-900/50 p-5 shadow-lg shadow-black/20 backdrop-blur transition-colors',
        onClick && 'cursor-pointer hover:border-sky-500/40'
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
            {label}
          </p>
          <p className="mt-1.5 truncate text-2xl font-semibold text-slate-100">{value}</p>
        </div>
        {Icon && (
          <div className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-xl', accentCls)}>
            <Icon className="h-5 w-5" />
          </div>
        )}
      </div>
      {trend && (
        <div className="mt-2 flex items-center gap-2">
          <span
            className={cn(
              'rounded-md px-1.5 py-0.5 text-[11px] font-semibold',
              trend.neutral
                ? 'bg-slate-500/10 text-slate-400'
                : trend.positive
                  ? 'bg-emerald-500/10 text-emerald-300'
                  : 'bg-red-500/10 text-red-300'
            )}
          >
            {trend.value}
          </span>
        </div>
      )}
      {detail && <p className="mt-2 text-xs leading-5 text-slate-500">{detail}</p>}
      {footer}
    </div>
  )
}
