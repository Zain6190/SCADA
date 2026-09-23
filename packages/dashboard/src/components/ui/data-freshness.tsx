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
      <Badge tone="ok">
        <span className="relative flex h-1.5 w-1.5" aria-hidden>
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-ok" />
        </span>
        Live
      </Badge>
      {updatedAt && (
        <span className="text-caption text-ink-subtle">
          Updated {timeAgo(updatedAt)}
        </span>
      )}
      {source && <span className="text-caption text-ink-subtle">· {source}</span>}
    </div>
  )
}
