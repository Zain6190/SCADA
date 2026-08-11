// packages/dashboard/src/components/ui/data-freshness.tsx
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/format'
import { Badge } from '@/components/ui/badge'

export function DataFreshness({
  updatedAt,
  source,
  className,
}: {
  updatedAt?: string | Date | null
  source?: string
  className?: string
}) {
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <Badge tone="sky" className="normal-case">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
        </span>
        Live
      </Badge>
      {updatedAt && (
        <span className="text-[11px] text-slate-500">
          Updated {timeAgo(updatedAt)}
        </span>
      )}
      {source && <span className="text-[11px] text-slate-600">· {source}</span>}
    </div>
  )
}
