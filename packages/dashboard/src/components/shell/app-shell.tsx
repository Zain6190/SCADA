'use client'

// packages/dashboard/src/components/shell/app-shell.tsx
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Sidebar } from '@/components/shell/sidebar'
import { TopBar } from '@/components/shell/topbar'
import { MobileNavigationDrawer } from '@/components/shell/mobile-nav'
import { AccessDenied } from '@/components/shell/access-denied'
import { moduleForPath } from '@/lib/navigation'
import { modulesForUser } from '@/lib/rbac'
import { useAuth } from '@/context/AuthContext'
import { cn } from '@/lib/utils'

export function AppShell({ children, className, navigationClassName }: {
  children: React.ReactNode
  className?: string
  navigationClassName?: string
}) {
  const [navOpen, setNavOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const { user, loading } = useAuth()

  // The user is restored from sessionStorage inside an effect, so `user` is
  // null on the first paint. Without waiting for `loading` every portal would
  // flash "Access Restricted" before the session resolves.
  const resolving = loading || !user

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [loading, user, router])

  const module = moduleForPath(pathname)
  const allowed = !!user && modulesForUser(user).includes(module)

  return (
    <div className={cn('min-h-screen bg-canvas text-ink', className)}>
      <div className="lg:grid lg:grid-cols-[240px_1fr]">
        {/* nav-surface re-declares the theme tokens in their inverted form,
            so the rail is deep green on every portal without per-page CSS. */}
        <aside className={cn('nav-surface sticky top-0 hidden h-screen border-r border-line lg:block', navigationClassName)}>
          <Sidebar />
        </aside>

        <div className="flex min-h-screen flex-col">
          <TopBar onOpenNav={() => setNavOpen(true)} />
          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
            {resolving ? (
              <SessionSkeleton />
            ) : allowed ? (
              children
            ) : (
              <AccessDenied module={module} pathname={pathname} />
            )}
          </main>
          <footer className="border-t border-line px-6 py-4">
            <p className="text-center text-[11px] text-ink-subtle">
              IBCP-SCADA · Indus Basin Cyber-Physical System · AquaVision AI (XGBoost · GEE MODIS/CHIRPS) · Simulation & telemetry
            </p>
          </footer>
        </div>
      </div>

      <MobileNavigationDrawer open={navOpen} onClose={() => setNavOpen(false)} className={navigationClassName} />
    </div>
  )
}

/** Placeholder shown while the session is being restored. */
function SessionSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading session">
      <div className="h-8 w-64 animate-pulse rounded-lg bg-surface-alt" />
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-xl bg-surface/70" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-xl bg-surface/70" />
    </div>
  )
}
