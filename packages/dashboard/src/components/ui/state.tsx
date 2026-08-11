// packages/dashboard/src/components/ui/state.tsx
import { Loader2, AlertTriangle, Inbox } from 'lucide-react'
import { cn } from '@/lib/utils'

export function Spinner({ label = 'Loading', className }: { label?: string; className?: string }) {
  return (
    <div className={cn('flex items-center gap-3 text-slate-400', className)}>
      <Loader2 className="h-4 w-4 animate-spin text-sky-400" />
      <span className="text-sm">{label}…</span>
    </div>
  )
}

export function ErrorState({
  title = 'Failed to load data',
  message,
  onRetry,
  className,
}: {
  title?: string
  message?: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/5 px-6 py-10 text-center',
        className
      )}
    >
      <AlertTriangle className="h-6 w-6 text-red-400" />
      <div>
        <p className="text-sm font-semibold text-red-300">{title}</p>
        {message && <p className="mt-1 text-xs text-slate-500">{message}</p>}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 transition-colors hover:bg-red-500/20"
        >
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title = 'No data available',
  message,
  className,
}: {
  title?: string
  message?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/40 px-6 py-10 text-center',
        className
      )}
    >
      <Inbox className="h-6 w-6 text-slate-600" />
      <div>
        <p className="text-sm font-semibold text-slate-400">{title}</p>
        {message && <p className="mt-1 text-xs text-slate-600">{message}</p>}
      </div>
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-slate-800/60', className)} />
}
