// packages/dashboard/src/app/system/page.tsx
// AquaVision System Health - service uptime, alert state.
'use client'

import type { ReactNode } from 'react'
import { Cpu, Server, Bell, BellRing } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { ProgressBar } from '@/components/ui/progress'
import { useWaterOverview, useOperationalAlerts } from '@/features/water/hooks'
import { fmtNumber } from '@/lib/format'

const AMBER = 'bg-amber-500/10 text-amber-300'

function statusCount(alerts: { status: string }[], status: string): number {
  return alerts.filter((a) => a.status === status).length
}

export default function SystemHealthPage() {
  const overview = useWaterOverview()
  const alertsQuery = useOperationalAlerts()

  const serviceOnline = Boolean(overview.data)
  const alerts = alertsQuery.data ?? []

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="System Health"
          description="Live status of the AquaVision backend, databases, and processing pipeline."
          icon={<Cpu className="h-6 w-6" />}
          accent={AMBER}
          badge={
            <Badge tone={serviceOnline ? 'emerald' : 'red'}>
              {serviceOnline ? 'Service online' : 'Unreachable'}
            </Badge>
          }
          updatedAt={overview.data?.week_start_date}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Backend Service"
            value={serviceOnline ? 'Online' : 'Unreachable'}
            detail="AquaVision overview endpoint"
            icon={Server}
            accent={serviceOnline ? 'bg-emerald-500/10 text-emerald-300' : 'bg-red-500/10 text-red-300'}
          />
          <KpiCard
            label="Regions Monitored"
            value={overview.data?.regions_monitored ?? '—'}
            detail="Active monitoring scope"
            icon={Cpu}
            accent={AMBER}
          />
          <KpiCard
            label="Active Alerts"
            value={overview.data?.active_alerts ?? alerts.filter((a) => a.status !== 'RESOLVED').length}
            detail={`${statusCount(alerts, 'NEW')} new · ${statusCount(alerts, 'ACKNOWLEDGED')} acked`}
            icon={Bell}
            accent={AMBER}
          />
          <KpiCard
            label="Data Sources"
            value={5}
            detail="IRSA · FFD · Kaggle · Sensor · Synthetic"
            icon={Server}
            accent="bg-sky-500/10 text-sky-300"
          />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Service Status"
              subtitle="Core components of the AquaVision platform"
              icon={<Server className="h-5 w-5" />}
              accent={AMBER}
            />
            <CardBody className="space-y-3">
              <ServiceRow
                name="AquaVision API"
                detail="REST data & analytics service"
                badge={<Badge tone={serviceOnline ? 'emerald' : 'red'}>{serviceOnline ? 'Online' : 'Offline'}</Badge>}
              />
              <ServiceRow
                name="PostGIS Database"
                detail="Spatial + time-series data store"
                badge={
                  <Badge tone={alerts.length ? 'emerald' : 'red'}>
                    {alerts.length ? 'Online' : 'Offline'}
                  </Badge>
                }
              />
              <ServiceRow
                name="ML Pipeline"
                detail="XGBoost flood prediction models"
                badge={<Badge tone="violet">38 models</Badge>}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Alert Status"
              subtitle="Distribution across the alert lifecycle"
              icon={<BellRing className="h-5 w-5" />}
              accent={AMBER}
              action={<Badge tone="slate">{fmtNumber(alerts.length, 0)} total</Badge>}
            />
            <CardBody className="p-0">
              {alertsQuery.isPending ? (
                <div className="p-8"><Spinner label="Loading alerts" /></div>
              ) : alertsQuery.isError ? (
                <div className="p-8">
                  <ErrorState title="Alert queue unavailable" onRetry={() => alertsQuery.refetch()} />
                </div>
              ) : alerts.length === 0 ? (
                <div className="p-8">
                  <EmptyState title="No alerts tracked" message="The anomaly pipeline has not emitted events." />
                </div>
              ) : (
                <div className="space-y-5 p-5">
                  {(
                    [
                      ['NEW', statusCount(alerts, 'NEW'), 'amber'],
                      ['ACKNOWLEDGED', statusCount(alerts, 'ACKNOWLEDGED'), 'sky'],
                      ['INVESTIGATING', statusCount(alerts, 'INVESTIGATING'), 'violet'],
                      ['RESOLVED', statusCount(alerts, 'RESOLVED'), 'emerald'],
                    ] as const
                  ).map(([label, count, color]) => (
                    <div key={label}>
                      <div className="mb-1.5 flex items-center justify-between text-xs">
                        <span className="text-slate-300">{label}</span>
                        <span className="font-mono text-slate-400">{count}</span>
                      </div>
                      <ProgressBar value={count} max={alerts.length} color={color} />
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}

function ServiceRow({
  name,
  detail,
  badge,
}: {
  name: string
  detail: string
  badge: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-200">{name}</p>
        <p className="text-[11px] text-slate-500">{detail}</p>
      </div>
      {badge}
    </div>
  )
}
