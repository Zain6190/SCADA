// packages/dashboard/src/components/ui/card.tsx
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

export function Card({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-slate-800/80 bg-slate-900/50 shadow-lg shadow-black/20 backdrop-blur',
        className
      )}
    >
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  subtitle,
  icon,
  action,
  accent,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  accent?: string
  className?: string
}) {
  return (
    <div className={cn('flex items-start justify-between gap-4 border-b border-slate-800/70 px-5 py-4', className)}>
      <div className="flex items-center gap-3">
        {icon && (
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-xl',
              accent || 'bg-sky-500/10 text-sky-300'
            )}
          >
            {icon}
          </div>
        )}
        <div>
          <h3 className="text-sm font-semibold tracking-wide text-slate-200">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('p-5', className)}>{children}</div>
}
