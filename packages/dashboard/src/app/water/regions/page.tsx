// packages/dashboard/src/app/water/regions/page.tsx
// AquaVision Regions - provinces & districts with alert counts.
'use client'

import { useEffect, useState } from 'react'
import { MapPin } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useWaterRegions, useWaterAlerts } from '@/features/water/hooks'
import { waterApi } from '@/features/water/api'
import Link from 'next/link'

export default function RegionsPage() {
  const regionsQuery = useWaterRegions()
  const alertsQuery = useWaterAlerts()

  const regions = regionsQuery.data ?? []
  const alerts = alertsQuery.data ?? []
  const openAlertCount = alerts.filter((a) => a.status !== 'RESOLVED').length

  const [satellite, setSatellite] = useState<any>(null)
  useEffect(() => {
    waterApi.getSatelliteReportSection().then(setSatellite).catch(() => setSatellite(null))
  }, [])
  const provinces = regions.filter((r) => r.type === 'province')
  const districts = regions.filter((r) => r.type !== 'province')

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Regions"
          description="Provinces and districts. Satellite rainfall, ET, and surface water come from the weekly index."
          icon={<MapPin className="h-6 w-6" />}
          action={regions.length ? <Badge tone="sky">{regions.length} regions</Badge> : undefined}
        />

        {regionsQuery.isPending ? (
          <Spinner />
        ) : regionsQuery.isError ? (
          <ErrorState onRetry={() => regionsQuery.refetch()} />
        ) : regions.length === 0 ? (
          <EmptyState title="No regions" message="Run the region ingest pipeline." />
        ) : (
          <>
            {satellite?.image_week && (
              <Card>
                <CardHeader
                  title="Satellite week"
                  subtitle={`Image week ${satellite.image_week}`}
                />
                <CardBody className="space-y-1 text-sm text-slate-300">
                  {(satellite.worst_districts || []).map((row: any) => (
                    <p key={row.region_id}>
                      {row.name}: rain {row.rainfall_mm ?? '—'} mm, ET {row.et_mm ?? '—'} mm, surface water {row.surface_water_km2 ?? '—'} km²
                    </p>
                  ))}
                </CardBody>
              </Card>
            )}
            <RegionTable title="Provinces" rows={provinces} openAlertCount={openAlertCount} />
            {districts.length > 0 && <RegionTable title="Districts" rows={districts} openAlertCount={openAlertCount} />}
          </>
        )}
      </div>
    </AppShell>
  )
}

function RegionTable({
  title,
  rows,
  openAlertCount,
}: {
  title: string
  rows: Array<{ id: number; name: string; type: string; code?: string | null }>
  openAlertCount: number
}) {
  if (!rows.length) return null
  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={`${rows.length} regions`}
        icon={<MapPin className="h-5 w-5" />}
        accent="bg-brand-soft text-brand"
        action={openAlertCount > 0 ? <Badge tone="amber">{openAlertCount} open alerts</Badge> : undefined}
      />
      <CardBody className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-surface text-[11px] uppercase tracking-wider text-ink-subtle">
            <tr>
              <Th>Name</Th>
              <Th>Code</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.id} className="text-ink-muted hover:bg-surface-alt">
                <Td>
                  <Link href={`/water/regions/${r.id}`} className="font-medium text-ink hover:text-brand">
                    {r.name}
                  </Link>
                </Td>
                <Td><Badge tone="slate">{r.code || '\u2014'}</Badge></Td>
                <Td className="text-right text-[11px] text-ink-subtle">
                  <Link href={`/water/regions/${r.id}`}>View →</Link>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  )
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  const text = children ? (Array.isArray(children) ? children.join('') : String(children)) : ''
  return <th className={`px-4 py-2.5 font-medium ${className ?? ''}`}>{text}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-2.5 text-xs ${className ?? ''}`}>{children}</td>
}
