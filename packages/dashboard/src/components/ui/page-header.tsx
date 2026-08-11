// packages/dashboard/src/components/ui/page-header.tsx
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { DataFreshness } from '@/components/ui/data-freshness'

export function PageHeader({
  title,
  description,
  badge,
  icon,
  action,
  updatedAt,
  accent = 'bg-sky-500/10 text-sky-300',
  className,
}: {
  title: string
  description?: ReactNode
  badge?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  updatedAt?: string | Date | null
  accent?: string
  className?: string
}) {
  return (
    <div className={cn('flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between', className)}>
      <div className="flex items-start gap-4">
        {icon && (
          <div className={cn('hidden h-12 w-12 shrink-0 items-center justify-center rounded-2xl sm:flex', accent)}>
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-slate-100 sm:text-2xl">{title}</h1>
            {badge}
          </div>
          {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          <div className="mt-2">
            <DataFreshness updatedAt={updatedAt} />
          </div>
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
