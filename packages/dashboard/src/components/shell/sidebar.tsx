'use client'

import { useEffect, useId, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { BookOpen, ChevronDown, ChevronRight, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { sectionsForPortal, activeNavHref, moduleForPath, type NavItem, type NavSectionId } from '@/lib/navigation'
import { modulesForUser, type PortalUserLike } from '@/lib/rbac'
import { useAuth } from '@/context/AuthContext'
import { BrandMark } from '@/components/shared/brand-mark'
import styles from './sidebar.module.css'

function NavItemLink({ href, label, icon: Icon, active, onNavigate }: {
  href: string; label: string; icon: LucideIcon; active: boolean; onNavigate?: () => void
}) {
  const displayLabel = href === '/portal' ? 'All Workspaces' : href === '/water/command-center' ? 'Water Command Center' : label
  return (
    <Link href={href} onClick={onNavigate} aria-current={active ? 'page' : undefined}
      className={cn(styles.navItem, active && styles.active)}>
      <Icon size={18} strokeWidth={1.7} aria-hidden />
      <span>{displayLabel}</span>
      {active && <ChevronRight className={styles.currentArrow} size={15} aria-hidden />}
    </Link>
  )
}

function PortalSwitcher({ pathname, user, onNavigate }: {
  pathname: string; user: PortalUserLike | null; onNavigate?: () => void
}) {
  const router = useRouter()
  const id = useId()
  const allowed = modulesForUser(user)
  const allPortals: { id: NavSectionId; label: string; href: string }[] = [
    { id: 'command', label: 'All Workspaces', href: '/portal' },
    { id: 'aqua', label: 'AquaVision · Water', href: '/water' },
    { id: 'crop', label: 'Crop Yield', href: '/crop' },
    { id: 'geo', label: 'GeoVision', href: '/geo' },
    { id: 'system', label: 'System & Reports', href: '/system' },
    { id: 'admin', label: 'Administration', href: '/admin' },
  ]
  const portals = allPortals.filter(p => allowed.includes(p.id))
  const current = portals.find(p => p.id === moduleForPath(pathname)) ?? portals[0]
  if (!current) return null
  return (
    <div className={styles.workspace}>
      <label htmlFor={id}>Workspace</label>
      <div className={styles.selectWrap}>
        <select id={id} value={current.id} disabled={portals.length === 1} onChange={event => {
          const destination = portals.find(p => p.id === event.target.value)
          if (destination) { router.push(destination.href); onNavigate?.() }
        }}>
          {portals.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <ChevronDown size={16} aria-hidden />
      </div>
    </div>
  )
}

function NavigationGroup({ title, items, currentHref, pathname, defaultOpen, onNavigate }: {
  title: string; items: NavItem[]; currentHref?: string; pathname: string; defaultOpen?: boolean; onNavigate?: () => void
}) {
  const id = useId()
  const containsActive = items.some(item => item.href === currentHref)
  const [open, setOpen] = useState(!!defaultOpen || containsActive)
  useEffect(() => { if (containsActive) setOpen(true) }, [pathname, containsActive])
  if (!items.length) return null
  return (
    <div className={styles.group}>
      <button type="button" className={styles.groupButton} aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>
        <span>{title}</span><ChevronDown size={16} className={cn(styles.chevron, open && styles.expanded)} aria-hidden />
      </button>
      <div id={id} hidden={!open} className={styles.groupLinks}>
        {items.map(item => <NavItemLink key={item.href} {...item} active={item.href === currentHref} onNavigate={onNavigate} />)}
      </div>
    </div>
  )
}

const shortcuts = ['/water', '/water/command-center', '/water/operator/alerts', '/water/operator/tasks']

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, loading } = useAuth()
  const pathname = usePathname()
  const resolving = loading || !user
  const currentHref = activeNavHref(pathname)
  const allowed = modulesForUser(user)
  const portalSections = sectionsForPortal(pathname).filter(section => allowed.includes(section.id))
  return (
    <div className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.brandIcon}><BrandMark width={34} height={34} /></div>
        <div><p>IBCP-SCADA</p><span>Indus Basin Operations</span></div>
      </div>
      {!resolving && <PortalSwitcher pathname={pathname} user={user} onNavigate={onNavigate} />}
      <nav aria-label="Workspace navigation" className={styles.navigation}>
        {resolving && <NavSkeleton />}
        {!resolving && portalSections.map(section => (
          <div key={section.id}>
            <p className={styles.sectionLabel}>{section.id === 'aqua' ? 'Daily workspace' : section.title}</p>
            {section.id === 'aqua' ? <>
              <div className={styles.shortcuts}>
                {shortcuts.map(href => section.items.find(item => item.href === href)).filter((item): item is NavItem => !!item).map(item =>
                  <NavItemLink key={item.href} {...item} active={item.href === currentHref} onNavigate={onNavigate} />)}
              </div>
              <NavigationGroup title="Operations" items={section.items.filter(item => item.group === 'Operational' && !shortcuts.includes(item.href) && item.href !== '/water/stress-alerts')}
                currentHref={currentHref} pathname={pathname} defaultOpen onNavigate={onNavigate} />
              <NavigationGroup title="Analysis & Forecasts" items={section.items.filter(item => (item.group === 'Analysis' && !shortcuts.includes(item.href)) || item.href === '/water/stress-alerts')}
                currentHref={currentHref} pathname={pathname} onNavigate={onNavigate} />
              <NavigationGroup title="Maps" items={section.items.filter(item => item.group === 'Maps')}
                currentHref={currentHref} pathname={pathname} onNavigate={onNavigate} />
            </> : <div className={styles.shortcuts}>{section.items.map(item =>
              <NavItemLink key={item.href} {...item} active={item.href === currentHref} onNavigate={onNavigate} />)}</div>}
          </div>
        ))}
        {!resolving && !portalSections.length && <p className="px-3 py-6 text-sm text-ink-subtle">No modules available for your role.</p>}
      </nav>
      {!resolving && <div className={styles.footer}>
        <NavItemLink href="/key-terms" label="Key Terms" icon={BookOpen} active={pathname.startsWith('/key-terms')} onNavigate={onNavigate} />
      </div>}
    </div>
  )
}

function NavSkeleton() {
  return <div className="space-y-2" aria-hidden>{[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="h-11 animate-pulse rounded-lg bg-surface-alt" />)}</div>
}
