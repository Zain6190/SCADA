// packages/dashboard/src/components/shared/Navigation.tsx
'use client'

import { useAuth } from '@/context/AuthContext'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Satellite, Droplets, Sprout, LogOut, User } from 'lucide-react'

export default function Navigation() {
  const { user, logout } = useAuth()
  const pathname = usePathname()

  const navItems = [
    { name: 'AquaVision', href: '/water', icon: Droplets },
    { name: 'GeoVision AI', href: '/geovision', icon: Satellite },
    { name: 'Flood SCADA', href: '/flood', icon: Droplets },
    { name: 'Soil Monitoring', href: '/soil', icon: Sprout },
  ]

  return (
    <nav className="bg-white/80 backdrop-blur-sm border-b border-line px-4 py-3 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-brand rounded-lg flex items-center justify-center shadow-card">
              <LayoutDashboard className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-ink text-sm">IBCP-SCADA</span>
          </div>

          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href || 
                             (item.href !== '/' && pathname?.startsWith(item.href))
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200
                    ${isActive 
                      ? 'bg-brand-soft text-brand shadow-sm' 
                      : 'text-ink-subtle hover:bg-surface hover:text-ink'
                    }`}
                >
                  <item.icon className={`w-4 h-4 ${isActive ? 'text-brand' : 'text-ink-muted'}`} />
                  <span>{item.name}</span>
                </Link>
              )
            })}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-ink-subtle hidden md:block">
            {user?.full_name || user?.username}
          </span>
          <button
            onClick={logout}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-crit hover:bg-crit-soft rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden md:inline">Logout</span>
          </button>
        </div>
      </div>
    </nav>
  )
}