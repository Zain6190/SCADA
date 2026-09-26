'use client'

// packages/dashboard/src/components/shell/topbar.tsx
import { useAuth } from '@/context/AuthContext'
import { SystemStatusIndicator } from '@/components/shell/system-status'
import { LogOut, Bell, Menu, User } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { API_BASE_URL } from '@/lib/config'
import Link from 'next/link'

export function TopBar({ onOpenNav }: { onOpenNav: () => void }) {
  const { user, logout } = useAuth()

  const { data: queue } = useQuery({
    queryKey: ['alerts', 'queue-badge'],
    queryFn: async () => {
      const token = typeof window !== 'undefined' ? sessionStorage.getItem('access_token') : null
      const res = await fetch(`${API_BASE_URL}/water/alerts/queue`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error('bad')
      return (await res.json()) as { counts: { badge: number } }
    },
    refetchInterval: 60_000,
    retry: false,
  })

  const openCount = queue?.counts?.badge ?? 0

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between gap-4 border-b border-line bg-surface px-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenNav}
          className="rounded-lg border border-line p-2 text-ink-muted hover:bg-surface-alt lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" />
        </button>
        <span className="hidden text-[11px] font-medium uppercase tracking-[0.2em] text-ink-subtle sm:block">
          Indus Basin · Water Distribution & Irrigation SCADA
        </span>
      </div>

      <div className="flex items-center gap-3">
        <SystemStatusIndicator />
        <Link
          href="/water/operator/alerts"
          className="relative rounded-lg border border-line bg-surface p-2 text-ink-muted hover:bg-surface-alt"
          aria-label="Alerts"
        >
          <Bell className="h-4 w-4" />
          {openCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-crit text-[9px] font-bold text-white">
              {openCount}
            </span>
          )}
        </Link>
        <div className="hidden items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 md:flex">
          <User className="h-4 w-4 text-ink-muted" />
          <span className="text-xs text-ink-muted">{user?.full_name || user?.username || 'Operator'}</span>
        </div>
        <button
          onClick={logout}
          className="rounded-lg border border-line p-2 text-ink-muted hover:bg-crit-soft hover:text-crit"
          aria-label="Logout"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </header>
  )
}