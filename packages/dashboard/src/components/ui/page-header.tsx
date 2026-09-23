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
  accent = 'bg-brand-soft text-brand',
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
    <div className={cn('flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between', className)}>
      <div className="flex items-start gap-3">
        {icon && (
          <div className={cn('hidden h-10 w-10 shrink-0 items-center justify-center rounded sm:flex', accent)}>
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-h2 font-semibold text-ink sm:text-h1">{title}</h1>
            {badge}
          </div>
          {description && <p className="mt-1 max-w-[80ch] text-sm text-ink-muted">{description}</p>}
          <div className="mt-2">
            <DataFreshness updatedAt={updatedAt} />
          </div>
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
