// packages/dashboard/src/app/system/page.tsx
// AquaVision System Health - service uptime, alert state, and thresholds.
'use client'

import type { ReactNode } from 'react'
import { Cpu, Server, Bell, BellRing, SlidersHorizontal } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { ProgressBar } from '@/components/ui/progress'
import { useWaterOverview, useWaterAlerts, useWaterThresholds } from '@/features/water/hooks'
import { fmtNumber } from '@/lib/format'
import type { WaterThreshold } from '@/features/water/types'

const AMBER = 'bg-amber-500/10 text-amber-300'

type AlertStatus = 'New' | 'Acknowledged' | 'Resolved'

function statusCount(alerts: { status: string }[], status: AlertStatus): number {
  return alerts.filter((a) => a.status === status).length
}

export default function SystemHealthPage() {
  const overview = useWaterOverview()
  const alertsQuery = useWaterAlerts()
  const thresholdsQuery = useWaterThresholds()

  const serviceOnline = Boolean(overview.data)
  const alerts = alertsQuery.data ?? []
  const thresholds = thresholdsQuery.data ?? []

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
            value={overview.data?.active_alerts ?? alerts.filter((a) => a.status !== 'Resolved').length}
            detail={`${statusCount(alerts, 'New')} new · ${statusCount(alerts, 'Acknowledged')} acked`}
            icon={Bell}
            accent={AMBER}
          />
          <KpiCard
            label="Thresholds Configured"
            value={thresholds.length}
            detail="Anomaly detection rules"
            icon={SlidersHorizontal}
            accent={AMBER}
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
                  <Badge tone={thresholds.length || alerts.length ? 'emerald' : 'red'}>
                    {thresholds.length || alerts.length ? 'Online' : 'Offline'}
                  </Badge>
                }
              />
              <ServiceRow
                name="GEE Pipeline"
                detail="Google Earth Engine processing run"
                badge={<Badge tone="violet">Simulation</Badge>}
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
                <div className="p-8" >
                  <ErrorState title="Alert queue unavailable" onRetry={() => alertsQuery.refetch()} />
                </div >
              ) : alerts.length === 0 ? (
                <div className="p-8">
                  <EmptyState title="No alerts tracked" message="The anomaly pipeline has not emitted events." />
                </div>
              ) : (
                <div className="space-y-5 p-5">
                  {(
                    [
                      ['New', statusCount(alerts, 'New'), 'amber'],
                      ['Acknowledged', statusCount(alerts, 'Acknowledged'), 'sky'],
                      ['Resolved', statusCount(alerts, 'Resolved'), 'emerald'],
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

        <Card>
          <CardHeader
            title="Thresholds"
            subtitle="Configured anomaly-detection rules"
            icon={<SlidersHorizontal className="h-5 w-5" />}
            accent={AMBER}
            action={<Badge tone="slate">{fmtNumber(thresholds.length, 0)} rules</Badge>}
          />
          <CardBody className="p-0">
            {thresholdsQuery.isPending ? (
              <div className="p-8"><Spinner label="Loading thresholds" /></div>
            ) : thresholdsQuery.isError ? (
              <div className="p-8">
                <ErrorState title="Thresholds unavailable" onRetry={() => thresholdsQuery.refetch()} />
              </div>
            ) : thresholds.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No thresholds configured" message="Define anomaly rules to drive alert generation." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-5 py-3 font-medium">Threshold</th>
                      <th className="px-5 py-3 font-medium">Value</th>
                      <th className="px-5 py-3 font-medium">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {thresholds.map((t) => (
                      <ThresholdRow key={t.id} threshold={t} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
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

function ThresholdRow({ threshold }: { threshold: WaterThreshold }) {
  return (
    <tr className="transition-colors hover:bg-slate-800/20">
      <td className="px-5 py-3 font-medium text-slate-200">{threshold.threshold_name}</td>
      <td className="px-5 py-3 font-mono text-slate-300">{fmtNumber(threshold.value)}</td>
      <td className="px-5 py-3 text-slate-400">{threshold.description ?? '—'}</td>
    </tr>
  )
}