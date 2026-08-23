// packages/dashboard/src/components/shell/sidebar.tsx
'use client'

import { cn } from '@/lib/utils'
import {
  NAV_SECTIONS,
  sectionsForPortal,
  pathIsActive,
  moduleForPath,
  type NavSectionId,
} from '@/lib/navigation'
import { modulesForUser, type PortalUserLike } from '@/lib/rbac'
import { useAuth } from '@/context/AuthContext'
import { usePathname } from 'next/navigation'
import Link from 'next/link'

function NavItemLink({
  href,
  label,
  icon: Icon,
  active,
  onNavigate,
}: {
  href: string
  label: string
  icon: any
  active: boolean
  onNavigate?: () => void
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(
        'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'bg-sky-500/10 text-sky-300'
          : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
      )}
    >
      <Icon className={cn('h-4 w-4 shrink-0', active ? 'text-sky-400' : 'text-slate-500 group-hover:text-slate-300')} />
      <span className="truncate">{label}</span>
      {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-sky-400" />}
    </Link>
  )
}

/** Quick switcher listing portals the current user can access. */
function PortalSwitcher({ pathname, user }: { pathname: string; user: PortalUserLike | null }) {
  const modules = modulesForUser(user)
  const allPortals: { id: NavSectionId; label: string; href: string }[] = [
    { id: 'command', label: 'Command Center', href: '/' },
    { id: 'aqua', label: 'AquaVision', href: '/water' },
    { id: 'crop', label: 'Crop Yield', href: '/crop' },
    { id: 'geo', label: 'GeoVision', href: '/geo' },
    { id: 'system', label: 'System', href: '/system' },
    { id: 'admin', label: 'Admin', href: '/admin' },
  ]
  const portals = allPortals.filter((p) => modules.includes(p.id))

  if (portals.length <= 1) return null
  const current = portals.find((p) => p.id === moduleForPath(pathname)) ?? portals[0]

  return (
    <div className="space-y-1 border-b border-slate-800/70 px-4 py-3">
      <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Portals</p>
      <div className="flex flex-wrap gap-1.5">
        {portals.map((p) => (
          <Link
            key={p.id}
            href={p.href}
            className={cn(
              'rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors',
              p.id === current.id
                ? 'bg-sky-500/15 text-sky-300'
                : 'text-slate-400 hover:bg-slate-800/70 hover:text-slate-200'
            )}
          >
            {p.label}
          </Link>
        ))}
      </div>
    </div>
  )
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth()
  const pathname = usePathname()

  const allowed = modulesForUser(user)
  const portalSections = sectionsForPortal(pathname).filter((section) =>
    allowed.includes(section.id)
  )

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-slate-800/70 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-cyan-600 shadow-lg shadow-sky-500/20">
          <span className="text-sm font-bold text-white">Σ</span>
        </div>
        <div>
          <p className="text-sm font-semibold tracking-wide text-slate-100">IBCP-SCADA</p>
          <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Operations Console</p>
        </div>
      </div>

      <PortalSwitcher pathname={pathname} user={user} />

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {portalSections.map((section) => {
          const groups = new Map<string, typeof section.items>()
          for (const item of section.items) {
            const g = item.group || ''
            if (!groups.has(g)) groups.set(g, [])
            groups.get(g)!.push(item)
          }
          const hasGroups = section.items.some(i => i.group)

          return (
            <div key={section.id}>
              <p className={cn('mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.2em]', section.accent)}>
                {section.title}
              </p>
              {hasGroups ? (
                Array.from(groups.entries()).map(([group, items]) => (
                  <div key={group} className="mb-3">
                    {group && (
                      <p className="mb-0.5 px-3 pt-2 text-[10px] font-medium uppercase tracking-[0.15em] text-slate-600">
                        {group}
                      </p>
                    )}
                    <div className="space-y-0.5">
                      {items.map((item) => (
                        <NavItemLink
                          key={item.href}
                          href={item.href}
                          label={item.label}
                          icon={item.icon}
                          active={pathIsActive(pathname, item.href)}
                          onNavigate={onNavigate}
                        />
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="space-y-0.5">
                  {section.items.map((item) => (
                    <NavItemLink
                      key={item.href}
                      href={item.href}
                      label={item.label}
                      icon={item.icon}
                      active={pathIsActive(pathname, item.href)}
                      onNavigate={onNavigate}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
        {portalSections.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-slate-600">
            No modules available for your role.
          </p>
        )}
      </nav>
    </div>
  )
}