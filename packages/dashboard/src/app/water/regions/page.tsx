// packages/dashboard/src/app/water/regions/page.tsx
// AquaVision Regions - provinces & districts with alert counts.
'use client'

import { MapPin } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useWaterRegions, useWaterAlerts } from '@/features/water/hooks'
import Link from 'next/link'

export default function RegionsPage() {
  const regionsQuery = useWaterRegions()
  const alertsQuery = useWaterAlerts()

  const regions = regionsQuery.data ?? []
  const alerts = alertsQuery.data ?? []
  const openAlertCount = alerts.filter((a) => a.status !== 'RESOLVED').length

  const provinces = regions.filter((r) => r.type === 'province')
  const districts = regions.filter((r) => r.type !== 'province')

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Regions"
          description="Provinces and districts with open alert pressure."
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
        accent="bg-sky-500/10 text-sky-300"
        action={openAlertCount > 0 ? <Badge tone="amber">{openAlertCount} open alerts</Badge> : undefined}
      />
      <CardBody className="p-0">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
            <tr>
              <Th>Name</Th>
              <Th>Code</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {rows.map((r) => (
              <tr key={r.id} className="text-slate-300 hover:bg-slate-800/30">
                <Td>
                  <Link href={`/water/regions/${r.id}`} className="font-medium text-slate-100 hover:text-sky-300">
                    {r.name}
                  </Link>
                </Td>
                <Td><Badge tone="slate">{r.code || '\u2014'}</Badge></Td>
                <Td className="text-right text-[11px] text-slate-500">
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
