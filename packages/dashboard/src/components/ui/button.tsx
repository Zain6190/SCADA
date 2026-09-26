// packages/dashboard/src/components/ui/button.tsx
// The only button in the product. Four variants, three sizes — a screen gets
// exactly one `primary`; everything else is secondary, ghost or danger.
import { forwardRef } from 'react'
import type { ButtonHTMLAttributes } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-brand text-brand-on hover:bg-brand-hover border-transparent',
  secondary: 'bg-surface text-ink border-line-strong hover:bg-surface-alt',
  ghost: 'bg-transparent text-ink-muted border-transparent hover:bg-surface-alt hover:text-ink',
  danger: 'bg-crit text-white hover:bg-crit/90 border-transparent',
}

const SIZES: Record<ButtonSize, string> = {
  // Heights land on the 4px rhythm; md/lg clear the 44px touch target with
  // their surrounding spacing, sm is for dense toolbars on pointer devices.
  sm: 'h-8 gap-1.5 px-2.5 text-caption',
  md: 'h-9 gap-2 px-3.5 text-sm',
  lg: 'h-11 gap-2 px-5 text-sm',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, disabled, className, children, ...props },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center rounded border font-semibold transition-colors',
        'disabled:pointer-events-none disabled:opacity-45',
        VARIANTS[variant],
        SIZES[size],
        className
      )}
      {...props}
    >
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
      {children}
    </button>
  )
})

/** Square icon-only button. `label` is required — it becomes the aria-label. */
export function IconButton({
  label,
  variant = 'ghost',
  size = 'md',
  className,
  children,
  ...props
}: Omit<ButtonProps, 'children'> & { label: string; children: React.ReactNode }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex items-center justify-center rounded border transition-colors',
        'disabled:pointer-events-none disabled:opacity-45',
        VARIANTS[variant],
        size === 'sm' ? 'h-8 w-8' : size === 'lg' ? 'h-11 w-11' : 'h-9 w-9',
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}
