// packages/dashboard/src/app/portal/page.tsx
// Command Center - a portal launcher (not a data dashboard). Each approved,
// authenticated user may open it, but only sees the portal cards granted by
// their role and permissions. Portal data lives in each portal, not here.
'use client'

import Link from 'next/link'
import { Droplets, Sprout, Layers, ShieldCheck, LayoutDashboard } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '@/context/AuthContext'
import { modulesForUser, type PortalUserLike } from '@/lib/rbac'

const AQUA = 'bg-brand-soft text-brand'
const CROP = 'bg-ok-soft text-ok'
const GEO = 'bg-brand-soft text-brand'
const SYS = 'bg-warn-soft text-warn'

const ACCESS_TONE: Record<string, 'emerald' | 'sky' | 'amber' | 'red' | 'slate'> = {
  ACTIVE: 'emerald',
  APPROVED: 'sky',
  PENDING: 'amber',
  REJECTED: 'red',
  SUSPENDED: 'red',
  REVOKED: 'slate',
}

export default function CommandCenterPage() {
  const { user } = useAuth()

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Command Center"
          description="Portal launcher. Open a portal to view its data — only the portals your role & permissions allow are shown."
          icon={<LayoutDashboard className="h-6 w-6" />}
        />

        {user && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
            <span className="text-ink-muted">
              Signed in as <span className="font-medium text-ink">{user.full_name}</span>
            </span>
            <Badge tone="slate">{user.role}</Badge>
            {user.access_status && (
              <Badge tone={ACCESS_TONE[user.access_status] ?? 'slate'}>{user.access_status}</Badge>
            )}
          </div>
        )}

        {/* Portal cards - only the modules this user's permissions allow */}
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {portalCards(user).map(({ title, href, icon, accent, description, badge }) => (
            <ModuleCard
              key={href}
              title={title}
              href={href}
              icon={icon}
              accent={accent}
              description={description}
              badge={badge}
            />
          ))}
          {portalCards(user).length === 0 && (
            <div className="col-span-full">
              <p className="rounded-xl border border-line bg-surface p-6 text-center text-sm text-ink-subtle">
                No portals are enabled for your account. Contact an administrator
                to request access.
              </p>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}

function ModuleCard({
  title,
  href,
  icon,
  accent,
  description,
  badge,
}: {
  title: string
  href: string
  icon: React.ReactNode
  accent: string
  description: string
  badge?: React.ReactNode
}) {
  return (
    <Link href={href}>
      <Card className="group h-full transition-colors hover:border-line-strong">
        <CardBody className="flex h-full flex-col">
          <div className="flex items-start justify-between">
            <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${accent}`}>{icon}</div>
            {badge}
          </div>
          <h3 className="mt-4 text-base font-semibold text-ink">{title}</h3>
          <p className="mt-2 flex-1 text-xs leading-5 text-ink-subtle">{description}</p>
          <span className="mt-4 text-xs font-medium text-brand opacity-0 transition-opacity group-hover:opacity-100">
            Open →
          </span>
        </CardBody>
      </Card>
    </Link>
  )
}

function portalCards(user: PortalUserLike | null) {
  const modules = modulesForUser(user)
  return modules
    .filter((m) => m !== 'command')
    .map((m) => PORTAL_CARD_MAP[m])
    .filter(Boolean)
}

const PORTAL_CARD_MAP: Record<
  string,
  { title: string; href: string; icon: React.ReactNode; accent: string; description: string; badge?: React.ReactNode }
> = {
  aqua: {
    title: 'AquaVision · Water',
    href: '/water',
    icon: <Droplets className="h-6 w-6" />,
    accent: AQUA,
    description:
      'Water availability, WAI stress index, early warning, and operational telemetry across the Indus Basin — GEE MODIS/CHIRPS and the XGBoost pipeline.',
  },
  crop: {
    title: 'Crop Portal',
    href: '/crop',
    icon: <Sprout className="h-6 w-6" />,
    accent: CROP,
    description:
      'Regional yield forecasting, crop health, and NDVI/SAVI insights for irrigation planning.',
  },
  geo: {
    title: 'Land · GeoVision',
    href: '/geo',
    icon: <Layers className="h-6 w-6" />,
    accent: GEO,
    description:
      'Remote-sensing overview and derived land indices visualization.',
  },
  system: {
    title: 'System',
    href: '/system',
    icon: <ShieldCheck className="h-6 w-6" />,
    accent: SYS,
    description:
      'Platform administration: system health, audit trail, and portal access control.',
    badge: <Badge tone="amber">Administrators only</Badge>,
  },
}