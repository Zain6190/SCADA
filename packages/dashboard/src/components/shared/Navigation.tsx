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
    <nav className="bg-white/80 backdrop-blur-sm border-b border-gray-200/50 px-4 py-3 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg flex items-center justify-center shadow-md shadow-blue-500/25">
              <LayoutDashboard className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-gray-900 text-sm">IBCP-SCADA</span>
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
                      ? 'bg-blue-50 text-blue-700 shadow-sm' 
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                    }`}
                >
                  <item.icon className={`w-4 h-4 ${isActive ? 'text-blue-500' : 'text-gray-400'}`} />
                  <span>{item.name}</span>
                </Link>
              )
            })}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600 hidden md:block">
            {user?.full_name || user?.username}
          </span>
          <button
            onClick={logout}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden md:inline">Logout</span>
          </button>
        </div>
      </div>
    </nav>
  )
}