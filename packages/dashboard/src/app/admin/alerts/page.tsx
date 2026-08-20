// packages/dashboard/src/app/admin/alerts/page.tsx
// Alert Management - list, filter, acknowledge, resolve operational alerts.
'use client'

import { useState } from 'react'
import { Bell, Filter, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import {
  useOperationalAlerts,
  useAckOperationalAlert,
  useResolveOperationalAlert,
} from '@/features/water/hooks'
import { timeAgo } from '@/lib/format'
import type { OperationalAlert } from '@/features/water/types'

const AMBER = 'bg-amber-500/10 text-amber-300'

type StatusFilter = 'ALL' | 'NEW' | 'ACKNOWLEDGED' | 'RESOLVED'
type SeverityFilter = 'ALL' | 'CRITICAL' | 'WARNING' | 'WATCH'

export default function AdminAlertsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL')

  const alertsQuery = useOperationalAlerts()
  const ack = useAckOperationalAlert()
  const resolve = useResolveOperationalAlert()

  const allAlerts = alertsQuery.data ?? []

  const filtered = allAlerts.filter((a) => {
    if (statusFilter !== 'ALL' && a.status !== statusFilter) return false
    if (severityFilter !== 'ALL' && (a.severity as string) !== severityFilter) return false
    return true
  })

  const counts = {
    all: allAlerts.length,
    new: allAlerts.filter((a) => a.status === 'NEW').length,
    acked: allAlerts.filter((a) => a.status === 'ACKNOWLEDGED').length,
    resolved: allAlerts.filter((a) => a.status === 'RESOLVED').length,
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Alert Management"
          description="View, filter, acknowledge, and resolve operational alerts across all assets."
          icon={<Bell className="h-6 w-6" />}
          accent={AMBER}
          badge={
            <Badge tone="amber">
              {counts.new} new
            </Badge>
          }
        />

        {/* Status tabs */}
        <div className="flex flex-wrap gap-2">
          {(['ALL', 'NEW', 'ACKNOWLEDGED', 'RESOLVED'] as const).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                statusFilter === status
                  ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30'
                  : 'text-slate-400 hover:bg-slate-800 border border-transparent'
              }`}
            >
              {status === 'ALL' ? `All (${counts.all})` : `${status} (${status === 'NEW' ? counts.new : status === 'ACKNOWLEDGED' ? counts.acked : counts.resolved})`}
            </button>
          ))}
        </div>

        {/* Severity filter */}
        <div className="flex flex-wrap gap-2">
          {(['ALL', 'CRITICAL', 'WARNING', 'WATCH'] as const).map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                severityFilter === sev
                  ? sev === 'CRITICAL' ? 'bg-red-500/15 text-red-300 border border-red-500/30'
                    : sev === 'WARNING' ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                    : sev === 'WATCH' ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30'
                    : 'bg-slate-500/15 text-slate-300 border border-slate-500/30'
                  : 'text-slate-400 hover:bg-slate-800 border border-transparent'
              }`}
            >
              {sev === 'ALL' ? 'All severities' : sev}
            </button>
          ))}
        </div>

        {/* Alert list */}
        <Card>
          <CardHeader
            title="Alerts"
            subtitle={`${filtered.length} alerts matching filters`}
            icon={<AlertTriangle className="h-5 w-5" />}
            accent={AMBER}
          />
          <CardBody className="p-0">
            {alertsQuery.isPending ? (
              <div className="p-8"><Spinner /></div>
            ) : filtered.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No alerts" message="No alerts match the current filters." />
              </div>
            ) : (
              <div className="divide-y divide-slate-800/70">
                {filtered.map((a) => (
                  <AdminAlertRow
                    key={a.id}
                    alert={a}
                    busy={ack.isPending || resolve.isPending}
                    onAck={() => ack.mutate({ alertId: a.id })}
                    onResolve={() => resolve.mutate({ alertId: a.id })}
                  />
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}

function AdminAlertRow({
  alert,
  busy,
  onAck,
  onResolve,
}: {
  alert: OperationalAlert
  busy: boolean
  onAck: () => void
  onResolve: () => void
}) {
  return (
    <div className="px-5 py-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-xs text-slate-500">#{alert.id}</p>
            <SeverityBadge severity={alert.severity} />
            <Badge tone={alert.status === 'NEW' ? 'amber' : alert.status === 'ACKNOWLEDGED' ? 'sky' : 'emerald'}>
              {alert.status}
            </Badge>
          </div>
          <h3 className="mt-2 text-sm font-semibold text-slate-100">{alert.alert_type}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{alert.message}</p>
          <p className="mt-0.5 text-xs text-slate-500">{timeAgo(alert.created_at)}</p>
          
          {/* Downstream Impact */}
          {alert.downstream_impact_summary && (
            <div className="mt-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
              <p className="text-xs font-medium text-amber-300 mb-2">DOWNSTREAM IMPACT</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div>
                  <p className="text-slate-400">Population Exposed</p>
                  <p className="text-white font-medium">{alert.downstream_population_exposed?.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-slate-400">Bridges at Risk</p>
                  <p className="text-white font-medium">{alert.downstream_bridges_at_risk}</p>
                </div>
                <div>
                  <p className="text-slate-400">Hospitals at Risk</p>
                  <p className="text-white font-medium">{alert.downstream_hospitals_at_risk}</p>
                </div>
                <div>
                  <p className="text-slate-400">Furthest Arrival</p>
                  <p className="text-white font-medium">{alert.downstream_furthest_asset} (+{alert.downstream_furthest_arrival_hours?.toFixed(0)}h)</p>
                </div>
              </div>
            </div>
          )}
          
          {/* Flood Classification */}
          {alert.flood_probability != null && alert.flood_probability > 0 && (
            <div className="mt-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
              <p className="text-xs font-medium text-red-300 mb-2">FLOOD CLASSIFICATION</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div>
                  <p className="text-slate-400">Probability</p>
                  <p className="text-white font-medium">{(alert.flood_probability * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-slate-400">Severity</p>
                  <p className="text-white font-medium">{alert.flood_severity}</p>
                </div>
                <div>
                  <p className="text-slate-400">Confidence</p>
                  <p className="text-white font-medium">{alert.flood_confidence}</p>
                </div>
                <div>
                  <p className="text-slate-400">Recommendation</p>
                  <p className="text-white font-medium">{alert.flood_recommendation}</p>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {alert.status === 'NEW' && (
            <button
              onClick={onAck}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-300 hover:bg-sky-500/20 transition disabled:opacity-50"
            >
              <CheckCircle2 className="h-3.5 w-3.5" /> Ack
            </button>
          )}
          {alert.status !== 'RESOLVED' && (
            <button
              onClick={onResolve}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 transition disabled:opacity-50"
            >
              <XCircle className="h-3.5 w-3.5" /> Resolve
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
