'use client'

// packages/dashboard/src/components/shell/app-shell.tsx
import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { Sidebar } from '@/components/shell/sidebar'
import { TopBar } from '@/components/shell/topbar'
import { MobileNavigationDrawer } from '@/components/shell/mobile-nav'
import { AccessDenied } from '@/components/shell/access-denied'
import { moduleForPath } from '@/lib/navigation'
import { modulesForUser } from '@/lib/rbac'
import { useAuth } from '@/context/AuthContext'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)
  const pathname = usePathname()
  const { user } = useAuth()

  const module = moduleForPath(pathname)
  const allowed = modulesForUser(user).includes(module)

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(56,189,248,0.06),_transparent_45%),radial-gradient(ellipse_at_bottom_right,_rgba(139,92,246,0.05),_transparent_40%)]" />
      <div className="relative lg:grid lg:grid-cols-[240px_1fr]">
        <aside className="sticky top-0 hidden h-screen border-r border-slate-800/80 bg-slate-950/80 backdrop-blur lg:block">
          <Sidebar />
        </aside>

        <div className="flex min-h-screen flex-col">
          <TopBar onOpenNav={() => setNavOpen(true)} />
          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
            {allowed ? children : <AccessDenied module={module} pathname={pathname} />}
          </main>
          <footer className="border-t border-slate-800/60 px-6 py-4">
            <p className="text-center text-[11px] text-slate-600">
              IBCP-SCADA · Indus Basin Cyber-Physical System · AquaVision AI (XGBoost · GEE MODIS/CHIRPS) · Simulation & telemetry
            </p>
          </footer>
        </div>
      </div>

      <MobileNavigationDrawer open={navOpen} onClose={() => setNavOpen(false)} />
    </div>
  )
}