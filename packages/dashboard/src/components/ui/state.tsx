// packages/dashboard/src/components/ui/state.tsx
// The three states every data surface needs. Loading, empty and error look
// like siblings: same box, same rhythm, different meaning — so a page never
// invents its own variant.
import { Loader2, AlertTriangle, Inbox, Lock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

export function Spinner({ label = 'Loading', className }: { label?: string; className?: string }) {
  return (
    <div className={cn('flex items-center gap-2.5 text-ink-muted', className)} role="status">
      <Loader2 className="h-4 w-4 animate-spin text-brand" aria-hidden />
      <span className="text-sm">{label}…</span>
    </div>
  )
}

function StateShell({
  tone = 'neutral',
  icon,
  title,
  message,
  action,
  className,
}: {
  tone?: 'neutral' | 'crit'
  icon: React.ReactNode
  title: string
  message?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2.5 rounded-lg border px-6 py-8 text-center',
        tone === 'crit' ? 'border-crit/25 bg-crit-soft' : 'border-line bg-surface',
        className
      )}
    >
      {icon}
      <div>
        <p className={cn('text-sm font-semibold', tone === 'crit' ? 'text-crit' : 'text-ink')}>{title}</p>
        {message && <p className="mx-auto mt-1 max-w-[42ch] text-caption leading-5 text-ink-subtle">{message}</p>}
      </div>
      {action}
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
    <StateShell
      tone="crit"
      icon={<AlertTriangle className="h-5 w-5 text-crit" aria-hidden />}
      title={title}
      message={message}
      action={
        onRetry ? (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
      className={className}
    />
  )
}

export function EmptyState({
  title = 'No data available',
  message,
  action,
  className,
}: {
  title?: string
  message?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <StateShell
      icon={<Inbox className="h-5 w-5 text-ink-subtle" aria-hidden />}
      title={title}
      message={message}
      action={action}
      className={className}
    />
  )
}

/** Shown when the data exists but the signed-in role may not see it. */
export function RestrictedState({
  title = 'Analyst access required',
  message,
  action,
  className,
}: {
  title?: string
  message?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <StateShell
      icon={<Lock className="h-5 w-5 text-ink-subtle" aria-hidden />}
      title={title}
      message={message}
      action={action}
      className={className}
    />
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-surface-sunken', className)} />
}
