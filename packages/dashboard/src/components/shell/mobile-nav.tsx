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
        <Dialog.Content className={cn('fixed inset-y-0 left-0 z-50 w-72 bg-canvas shadow-2xl outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-left', className)}>
          <div className="flex justify-end p-3">
            <button
              onClick={onClose}
              className="rounded-lg border border-line p-2 text-ink-muted hover:bg-surface-alt"
              aria-label="Close navigation"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <Sidebar onNavigate={onClose} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
