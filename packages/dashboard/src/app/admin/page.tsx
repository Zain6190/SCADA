// packages/dashboard/src/app/admin/page.tsx
// Admin Dashboard - Pipeline health, alert statistics, data freshness.
'use client'

import {
  Activity,
  Server,
  Bell,
  Database,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState } from '@/components/ui/state'
import { usePipelineHealth, useWaterAlerts, useWaterAssets } from '@/features/water/hooks'
import { fmtNumber } from '@/lib/format'
import { timeAgo } from '@/lib/format'

const AMBER = 'bg-amber-500/10 text-amber-300'

function statusTone(status: string | null | undefined): 'emerald' | 'amber' | 'red' | 'slate' {
  switch (status) {
    case 'SUCCESS':
    case 'ready':
    case 'running':
    case 'online':
      return 'emerald'
    case 'PARTIAL_SUCCESS':
    case 'delayed':
      return 'amber'
    case 'FAILED':
    case 'not_ready':
    case 'unhealthy':
    case 'offline':
      return 'red'
    default:
      return 'slate'
  }
}

function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'SUCCESS': return 'Success'
    case 'PARTIAL_SUCCESS': return 'Partial'
    case 'FAILED': return 'Failed'
    case 'RUNNING': return 'Running'
    case 'QUEUED': return 'Queued'
    case 'ready': return 'Ready'
    case 'not_ready': return 'Not Ready'
    case 'running': return 'Running'
    case 'delayed': return 'Delayed'
    case 'unhealthy': return 'Unhealthy'
    default: return status ?? 'Unknown'
  }
}

export default function AdminDashboardPage() {
  const healthQuery = usePipelineHealth()
  const alertsQuery = useWaterAlerts()
  const assetsQuery = useWaterAssets()

  const health = healthQuery.data
  const alerts = alertsQuery.data ?? []
  const assets = assetsQuery.data ?? []

  const openAlerts = alerts.filter((a) => a.status !== 'Resolved')
  const newAlerts = alerts.filter((a) => a.status === 'New')
  const criticalAlerts = alerts.filter((a) => (a.severity as string) === 'CRITICAL' && a.status !== 'Resolved')

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Admin Dashboard"
          description="Pipeline health, alert statistics, and system overview."
          icon={<Activity className="h-6 w-6" />}
          accent={AMBER}
          badge={
            <Badge tone={healthQuery.data ? 'emerald' : healthQuery.isError ? 'red' : 'slate'}>
              {healthQuery.isPending ? 'Loading...' : healthQuery.isError ? 'Offline' : 'Online'}
            </Badge>
          }
        />

        {/* KPI strip */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Scheduler"
            value={statusLabel(health?.scheduler_status)}
            detail="Pipeline scheduler status"
            icon={Server}
            accent={`bg-${statusTone(health?.scheduler_status)}-500/10 text-${statusTone(health?.scheduler_status)}-300`}
          />
          <KpiCard
            label="Open Alerts"
            value={openAlerts.length}
            detail={`${newAlerts.length} new · ${criticalAlerts.length} critical`}
            icon={Bell}
            accent="bg-amber-500/10 text-amber-300"
          />
          <KpiCard
            label="Assets"
            value={assets.length}
            detail="Water infrastructure monitored"
            icon={Database}
            accent="bg-sky-500/10 text-sky-300"
          />
          <KpiCard
            label="IRSA Freshness"
            value={health?.data_freshness?.irsa_hours != null ? `${health.data_freshness.irsa_hours.toFixed(1)}h` : '—'}
            detail="Hours since last IRSA data"
            icon={Clock}
            accent="bg-violet-500/10 text-violet-300"
          />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Pipeline Status */}
          <Card>
            <CardHeader
              title="Pipeline Status"
              subtitle="Last IRSA and FFD ingestion runs"
              icon={<Server className="h-5 w-5" />}
              accent={AMBER}
              action={
                <button
                  onClick={() => healthQuery.refetch()}
                  disabled={healthQuery.isPending}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition"
                >
                  <RefreshCw className={`h-4 w-4 ${healthQuery.isPending ? 'animate-spin' : ''}`} />
                </button>
              }
            />
            <CardBody className="space-y-3">
              {healthQuery.isPending ? (
                <Spinner label="Loading pipeline status" />
              ) : healthQuery.isError ? (
                <ErrorState title="Pipeline status unavailable" onRetry={() => healthQuery.refetch()} />
              ) : (
                <>
                  <PipelineRow
                    name="IRSA Data Ingestion"
                    run={health?.last_irsa_run}
                    freshnessHours={health?.data_freshness?.irsa_hours}
                  />
                  <PipelineRow
                    name="FFD Bulletin Ingestion"
                    run={health?.last_ffd_run}
                    freshnessHours={health?.data_freshness?.ffd_hours}
                  />
                </>
              )}
            </CardBody>
          </Card>

          {/* Alert Summary */}
          <Card>
            <CardHeader
              title="Alert Summary"
              subtitle="Active alert distribution by severity"
              icon={<Bell className="h-5 w-5" />}
              accent="bg-red-500/10 text-red-300"
              action={<Badge tone="slate">{alerts.length} total</Badge>}
            />
            <CardBody className="space-y-3">
              {[
                { label: 'CRITICAL', count: alerts.filter((a) => (a.severity as string) === 'CRITICAL' && a.status !== 'Resolved').length, color: 'red' },
                { label: 'WARNING', count: alerts.filter((a) => (a.severity as string) === 'WARNING' && a.status !== 'Resolved').length, color: 'amber' },
                { label: 'WATCH', count: alerts.filter((a) => (a.severity as string) === 'WATCH' && a.status !== 'Resolved').length, color: 'sky' },
                { label: 'Resolved (today)', count: alerts.filter((a) => a.status === 'Resolved').length, color: 'emerald' },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full bg-${row.color}-400`} />
                    <span className="text-sm text-slate-300">{row.label}</span>
                  </div>
                  <span className="font-mono text-sm font-semibold text-slate-200">{row.count}</span>
                </div>
              ))}
            </CardBody>
          </Card>
        </div>

        {/* Recent Alerts */}
        <Card>
          <CardHeader
            title="Recent Alerts"
            subtitle="Latest operational alerts across all assets"
            icon={<AlertTriangle className="h-5 w-5" />}
            accent="bg-amber-500/10 text-amber-300"
          />
          <CardBody className="p-0">
            {alertsQuery.isPending ? (
              <div className="p-8"><Spinner /></div>
            ) : alerts.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500">No alerts in the system.</div>
            ) : (
              <div className="divide-y divide-slate-800/70">
                {alerts.slice(0, 10).map((a) => (
                  <div key={a.id} className="flex items-center justify-between gap-4 px-5 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge tone={(a.severity as string) === 'CRITICAL' ? 'red' : (a.severity as string) === 'WARNING' ? 'amber' : 'sky'}>
                          {a.severity}
                        </Badge>
                        <span className="truncate text-sm text-slate-300">{a.alertType}</span>
                      </div>
                      <p className="mt-0.5 text-xs text-slate-500">{timeAgo(a.createdAt)}</p>
                    </div>
                    <Badge tone={a.status === 'Resolved' ? 'emerald' : a.status === 'Acknowledged' ? 'sky' : 'amber'}>
                      {a.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}

function PipelineRow({
  name,
  run,
  freshnessHours,
}: {
  name: string
  run: { status: string | null; completed_at: string | null; records_stored: number | null } | null
  freshnessHours: number | null
}) {
  const tone = statusTone(run?.status)
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-slate-200">{name}</p>
          <p className="text-xs text-slate-500">
            {run?.completed_at ? `Last run: ${timeAgo(run.completed_at)}` : 'No runs yet'}
          </p>
        </div>
        <Badge tone={tone}>{statusLabel(run?.status)}</Badge>
      </div>
      {freshnessHours != null && (
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full bg-${tone === 'emerald' ? 'emerald' : tone === 'amber' ? 'amber' : 'red'}-500`}
              style={{ width: `${Math.min(100, Math.max(5, 100 - freshnessHours * 2))}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-500">{freshnessHours.toFixed(1)}h ago</span>
        </div>
      )}
    </div>
  )
}
