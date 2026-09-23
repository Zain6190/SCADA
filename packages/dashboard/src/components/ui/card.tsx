// packages/dashboard/src/components/ui/card.tsx
// Elevation comes from a hairline border, not a shadow. Compact padding:
// 16px body, 12px header — an operator sees more rows per screen.
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
    <div className={cn('rounded-lg border border-line bg-surface shadow-card', className)}>
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
    <div className={cn('flex items-start justify-between gap-4 border-b border-line px-4 py-3', className)}>
      <div className="flex items-center gap-3">
        {icon && (
          <div
            className={cn(
              'flex h-9 w-9 items-center justify-center rounded',
              accent || 'bg-brand-soft text-brand'
            )}
          >
            {icon}
          </div>
        )}
        <div>
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-caption text-ink-subtle">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('p-4', className)}>{children}</div>
}

/** Footer strip for card-level actions or provenance notes. */
export function CardFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-center justify-between gap-3 border-t border-line bg-surface-alt/60 px-4 py-2.5', className)}>
      {children}
    </div>
  )
}
