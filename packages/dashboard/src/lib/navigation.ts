// packages/dashboard/src/lib/navigation.ts
import {
  LayoutDashboard,
  Droplets,
  Sprout,
  Satellite,
  MapIcon,
  Activity,
  LineChart,
  Bell,
  MapPin,
  FileText,
  Cpu,
  ScrollText,
  ShieldCheck,
  ShieldAlert,
  BarChart3,
  Gauge,
  Workflow,
  Users,
  Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  label: string
  href: string
  icon: LucideIcon
  section: NavSectionId
}

export type NavSectionId = 'command' | 'aqua' | 'crop' | 'geo' | 'system' | 'admin'

export interface NavSection {
  id: NavSectionId
  title: string
  accent: string
  items: NavItem[]
}

export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'command',
    title: 'Command',
    accent: 'text-slate-300',
    items: [{ label: 'Command Center', href: '/', icon: LayoutDashboard, section: 'command' }],
  },
  {
    id: 'aqua',
    title: 'AquaVision · Water',
    accent: 'text-sky-400',
    items: [
      { label: 'Overview', href: '/water', icon: Droplets, section: 'aqua' },
      { label: 'Assets', href: '/water/operator/assets', icon: Workflow, section: 'aqua' },
      { label: 'Alerts', href: '/water/operator/alerts', icon: Bell, section: 'aqua' },
      { label: 'FFD Bulletins', href: '/water/ffd', icon: FileText, section: 'aqua' },
      { label: 'Operations', href: '/water/operator', icon: Workflow, section: 'aqua' },
      { label: 'Analyst', href: '/water/analyst', icon: LineChart, section: 'aqua' },
      { label: 'Live Map', href: '/water/map', icon: MapIcon, section: 'aqua' },
      { label: 'Indicators', href: '/water/indicators', icon: Activity, section: 'aqua' },
      { label: 'Regions', href: '/water/regions', icon: MapIcon, section: 'aqua' },
      { label: 'Predictions', href: '/water/predictions', icon: LineChart, section: 'aqua' },
      { label: 'Anomalies', href: '/water/anomalies', icon: ShieldAlert, section: 'aqua' },
      { label: 'Alerts (Weekly)', href: '/water/alerts', icon: ScrollText, section: 'aqua' },
    ],
  },
  {
    id: 'crop',
    title: 'Crop Yield · Agriculture',
    accent: 'text-emerald-400',
    items: [
      { label: 'Overview', href: '/crop', icon: Sprout, section: 'crop' },
      { label: 'Historical Yield', href: '/crop/historical', icon: BarChart3, section: 'crop' },
      { label: 'Regional Forecast', href: '/crop/regions', icon: MapIcon, section: 'crop' },
    ],
  },
  {
    id: 'geo',
    title: 'GeoVision · Remote Sensing',
    accent: 'text-violet-400',
    items: [
      { label: 'Overview', href: '/geo', icon: Satellite, section: 'geo' },
      { label: 'NDVI Analysis', href: '/geo/ndvi', icon: Activity, section: 'geo' },
      { label: 'Regional Index', href: '/geo/regions', icon: MapIcon, section: 'geo' },
    ],
  },
  {
    id: 'system',
    title: 'System & Reports',
    accent: 'text-amber-400',
    items: [
      { label: 'Reports', href: '/reports', icon: Gauge, section: 'system' },
      { label: 'System Health', href: '/system', icon: ScrollText, section: 'system' },
      { label: 'Audit Log', href: '/system/audit', icon: Activity, section: 'system' },
      { label: 'My Team', href: '/system/team', icon: Users, section: 'system' },
      { label: 'Portal Access', href: '/system/users', icon: ShieldCheck, section: 'system' },
      { label: 'Access Requests', href: '/system/access-requests', icon: ShieldCheck, section: 'system' },
    ],
  },
  {
    id: 'admin',
    title: 'Admin',
    accent: 'text-amber-400',
    items: [
      { label: 'Dashboard', href: '/admin', icon: Settings, section: 'admin' },
      { label: 'Pipelines', href: '/admin/pipelines', icon: Workflow, section: 'admin' },
      { label: 'Alerts', href: '/admin/alerts', icon: Bell, section: 'admin' },
      { label: 'Assets', href: '/admin/assets', icon: Gauge, section: 'admin' },
    ],
  },
]

export const SECTION_ACCENT: Record<NavSectionId, string> = {
  command: 'text-slate-300',
  aqua: 'text-sky-400',
  crop: 'text-emerald-400',
  geo: 'text-violet-400',
  system: 'text-amber-400',
  admin: 'text-amber-400',
}

/** Root path segments that scope a page to its module/portal. */
const MODULE_SEGMENT: Record<string, NavSectionId> = {
  water: 'aqua',
  crop: 'crop',
  geo: 'geo',
  reports: 'system',
  system: 'system',
  admin: 'admin',
}

/** The module/a portal a given path belongs to (or 'command' for the launcher). */
export function moduleForPath(pathname: string): NavSectionId {
  if (pathname === '/' || pathname === '') return 'command'
  const first = (pathname.split('/')[1] || '').toLowerCase()
  return MODULE_SEGMENT[first] ?? 'command'
}

/**
 * The sections shown in a portal's sidebar. Isolate the current module:
 * opening /water/* shows ONLY the aqua section; /geo/* shows only geo, etc.
 */
export function sectionsForPortal(pathname: string): NavSection[] {
  const module = moduleForPath(pathname)
  return NAV_SECTIONS.filter((section) => section.id === module)
}

export function pathIsActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(href + '/')
}

export function findSectionForPath(pathname: string): NavSection | undefined {
  if (pathname === '/') return NAV_SECTIONS[0]
  return NAV_SECTIONS.find((section) =>
    section.items.some((item) => pathIsActive(pathname, item.href))
  )
}

export function findActiveItem(pathname: string): NavItem | undefined {
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      if (pathIsActive(pathname, item.href)) return item
    }
  }
  return undefined
}