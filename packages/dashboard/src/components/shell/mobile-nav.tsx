'use client'

// packages/dashboard/src/components/shell/mobile-nav.tsx
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Sidebar } from '@/components/shell/sidebar'
import { cn } from '@/lib/utils'

export function MobileNavigationDrawer({
  open,
  onClose,
  className,
}: {
  open: boolean
  onClose: () => void
  className?: string
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in" />
        {/* The drawer is portalled outside the page, so it carries the
            inverted tokens itself rather than inheriting them. */}
        <Dialog.Content className={cn('nav-surface fixed inset-y-0 left-0 z-50 flex w-72 flex-col outline-none shadow-pop data-[state=open]:animate-in data-[state=open]:slide-in-from-left', className)}>
          <div className="flex justify-end p-3">
            <button
              onClick={onClose}
              className="rounded-lg border border-line p-2 text-ink-muted hover:bg-surface-alt"
              aria-label="Close navigation"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <Sidebar onNavigate={onClose} />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
