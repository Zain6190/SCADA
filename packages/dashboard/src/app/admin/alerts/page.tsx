// packages/dashboard/src/app/admin/alerts/page.tsx
// Alert Management - workflow health (KPIs), escalations board, list, ack/resolve.
'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { Bell, Filter, CheckCircle2, XCircle, AlertTriangle, Activity, Timer, Send, TrendingUp } from 'lucide-react'
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
import { waterApi } from '@/features/water/api'
import { useAuth } from '@/context/AuthContext'
import { timeAgo, fmtDateTime } from '@/lib/format'
import type { OperationalAlert, AlertKpis, EscalationsBoard } from '@/features/water/types'

const AMBER = 'bg-warn-soft text-warn'

type StatusFilter = 'ALL' | 'NEW' | 'ACKNOWLEDGED' | 'RESOLVED'
type SeverityFilter = 'ALL' | 'CRITICAL' | 'WARNING' | 'WATCH'

export default function AdminAlertsPage() {
  const { user } = useAuth()
  const role = (user?.role || '').toLowerCase()
  const roles = new Set((user?.roles || []).map(r => r.toLowerCase()))
  if (role) roles.add(role)
  const isAdmin = roles.has('admin')

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL')
  const [kpis, setKpis] = useState<AlertKpis | null>(null)
  const [escalations, setEscalations] = useState<EscalationsBoard | null>(null)
  const [boardError, setBoardError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [testBusy, setTestBusy] = useState(false)

  const alertsQuery = useOperationalAlerts()
  const ack = useAckOperationalAlert()
  const resolve = useResolveOperationalAlert()

  const loadBoard = () => {
    setBoardError(null)
    Promise.all([waterApi.getAlertKpis(), waterApi.getEscalations()])
      .then(([k, e]) => { setKpis(k); setEscalations(e) })
      .catch((err) => setBoardError(err?.response?.data?.detail || 'Board unavailable'))
  }
  useEffect(() => { loadBoard() }, [])

  const sendTest = async () => {
    setTestBusy(true)
    setTestResult(null)
    try {
      const res = await waterApi.sendTestAlert()
      setTestResult(
        res.channels_configured
          ? `Test alert #${res.alert_id}: sent=${res.dispatch?.sent ?? 0}, suppressed=${res.dispatch?.suppressed ?? 0}, failed=${res.dispatch?.failed ?? 0} → ${res.recipients.join(', ')}`
          : `Test alert #${res.alert_id} recorded, but no notification channels are configured (set SMTP/Slack in settings).`,
      )
    } catch (e: any) {
      setTestResult(e?.response?.data?.detail || 'Test failed')
    } finally {
      setTestBusy(false)
    }
  }

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
          action={
            <div className="flex flex-wrap gap-2">
              <button
                onClick={loadBoard}
                className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2 text-sm text-ink-muted transition-colors hover:border-brand/25 hover:text-brand"
              >
                Refresh board
              </button>
              {isAdmin && (
                <button
                  onClick={sendTest}
                  disabled={testBusy}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-brand/25 bg-brand-soft px-4 py-2 text-sm font-medium text-brand transition-colors hover:bg-brand-soft disabled:opacity-50"
                >
                  <Send className="h-4 w-4" /> {testBusy ? 'Sending…' : 'Send test alert'}
                </button>
              )}
            </div>
          }
        />

        {testResult && (
          <div className="rounded-xl border border-line-strong bg-surface-alt px-4 py-3 text-sm text-ink-muted">{testResult}</div>
        )}
        {boardError && (
          <div className="rounded-xl border border-crit/25 bg-crit-soft px-4 py-3 text-sm text-crit">{boardError}</div>
        )}

        {/* Workflow health KPIs */}
        {kpis && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard icon={<AlertTriangle className="h-4 w-4" />} label="Open alerts" value={String(kpis.open_total)} tone="amber" />
            <KpiCard icon={<CheckCircle2 className="h-4 w-4" />} label="ACK SLA compliance" value={kpis.ack_sla_compliance_pct != null ? `${kpis.ack_sla_compliance_pct}%` : '—'} tone="sky" sub={kpis.ack_sla_window_30d ? `last ${kpis.ack_sla_window_30d} alerts` : 'no SLA window'} />
            <KpiCard icon={<TrendingUp className="h-4 w-4" />} label="Avg time to resolve" value={kpis.mttr_hours_30d != null ? `${kpis.mttr_hours_30d}h` : '—'} tone="emerald" sub="last 30 days" />
            <KpiCard icon={<Timer className="h-4 w-4" />} label="Overdue instructions" value={String(kpis.overdue_instructions)} tone={kpis.overdue_instructions > 0 ? 'red' : 'slate'} />
            <KpiCard icon={<Activity className="h-4 w-4" />} label="Open instructions" value={String(kpis.open_instructions)} tone="violet" />
            <KpiCard icon={<Bell className="h-4 w-4" />} label="Escalations (7d)" value={String(kpis.escalations_7d)} tone={kpis.escalations_7d > 0 ? 'red' : 'slate'} />
          </div>
        )}

        {/* Escalations board */}
        {escalations && (escalations.counts.escalated > 0 || escalations.counts.sla_breached > 0 || escalations.counts.instructions_overdue > 0) && (
          <Card className="border-l-4 border-l-crit">
            <CardHeader
              title="Needs attention"
              subtitle={`${escalations.counts.escalated} escalated · ${escalations.counts.sla_breached} SLA breached · ${escalations.counts.instructions_overdue} overdue instructions`}
              icon={<AlertTriangle className="h-5 w-5" />}
              accent="bg-crit-soft text-crit"
            />
            <CardBody className="space-y-3 p-4">
              {escalations.escalated.map(a => (
                <div key={`e-${a.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface-alt px-3 py-2 text-sm">
                  <span className="text-ink">
                    <strong>#{a.id}</strong> {a.asset_name || `Asset ${a.asset_id}`} · {a.alert_type}
                    {a.escalated_to && <span className="ml-2 text-xs text-ink-subtle">→ {a.escalated_to}</span>}
                  </span>
                  <span className="text-xs text-ink-subtle">{a.escalated_at ? fmtDateTime(a.escalated_at) : timeAgo(a.created_at)}</span>
                </div>
              ))}
              {escalations.sla_breached.map(a => (
                <div key={`s-${a.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-crit/25 bg-crit-soft px-3 py-2 text-sm">
                  <span className="text-crit">
                    <strong>#{a.id}</strong> {a.asset_name || `Asset ${a.asset_id}`} · ACK SLA breached
                  </span>
                  <span className="text-xs">due {a.sla_due_at ? fmtDateTime(a.sla_due_at) : '—'}</span>
                </div>
              ))}
              {escalations.instructions_overdue.map(i => (
                <div key={`i-${i.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-warn/25 bg-warn-soft px-3 py-2 text-sm">
                  <span className="text-warn">
                    <strong>#{i.id}</strong> {i.asset_name || `Asset ${i.asset_id}`} · overdue → {i.assigned_to}
                  </span>
                  <span className="text-xs">{i.due_at ? fmtDateTime(i.due_at) : ''}</span>
                </div>
              ))}
            </CardBody>
          </Card>
        )}

        {/* Status tabs */}
        <div className="flex flex-wrap gap-2">
          {(['ALL', 'NEW', 'ACKNOWLEDGED', 'RESOLVED'] as const).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                statusFilter === status
                  ? 'bg-brand-soft text-brand border border-brand/25'
                  : 'text-ink-muted hover:bg-surface-alt border border-transparent'
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
                  ? sev === 'CRITICAL' ? 'bg-crit-soft text-crit border border-crit/25'
                    : sev === 'WARNING' ? 'bg-warn-soft text-warn border border-warn/25'
                    : sev === 'WATCH' ? 'bg-brand-soft text-brand border border-brand/25'
                    : 'bg-surface-sunken text-ink-muted border border-line-strong'
                  : 'text-ink-muted hover:bg-surface-alt border border-transparent'
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
              <div className="divide-y divide-line">
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
            <p className="font-mono text-xs text-ink-subtle">#{alert.id}</p>
            <SeverityBadge severity={alert.severity} />
            <Badge tone={alert.status === 'NEW' ? 'amber' : alert.status === 'ACKNOWLEDGED' ? 'sky' : 'emerald'}>
              {alert.status}
            </Badge>
          </div>
          <h3 className="mt-2 text-sm font-semibold text-ink">{alert.alert_type}</h3>
          <p className="mt-0.5 text-xs text-ink-subtle">{alert.message}</p>
          <p className="mt-0.5 text-xs text-ink-subtle">{timeAgo(alert.created_at)}</p>
          
          {/* Downstream Impact */}
          {alert.downstream_impact_summary && (
            <div className="mt-3 p-3 rounded-lg bg-warn-soft border border-warn/25">
              <p className="text-xs font-medium text-warn mb-2">DOWNSTREAM IMPACT</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div>
                  <p className="text-ink-muted">Population Exposed</p>
                  <p className="text-white font-medium">{alert.downstream_population_exposed?.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-ink-muted">Bridges at Risk</p>
                  <p className="text-white font-medium">{alert.downstream_bridges_at_risk}</p>
                </div>
                <div>
                  <p className="text-ink-muted">Hospitals at Risk</p>
                  <p className="text-white font-medium">{alert.downstream_hospitals_at_risk}</p>
                </div>
                <div>
                  <p className="text-ink-muted">Furthest Arrival</p>
                  <p className="text-white font-medium">{alert.downstream_furthest_asset} (+{alert.downstream_furthest_arrival_hours?.toFixed(0)}h)</p>
                </div>
              </div>
            </div>
          )}
          
          {/* Flood Classification */}
          {alert.flood_probability != null && alert.flood_probability > 0 && (
            <div className="mt-2 p-3 rounded-lg bg-crit-soft border border-crit/25">
              <p className="text-xs font-medium text-crit mb-2">FLOOD CLASSIFICATION</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div>
                  <p className="text-ink-muted">Probability</p>
                  <p className="text-white font-medium">{(alert.flood_probability * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-ink-muted">Severity</p>
                  <p className="text-white font-medium">{alert.flood_severity}</p>
                </div>
                <div>
                  <p className="text-ink-muted">Confidence</p>
                  <p className="text-white font-medium">{alert.flood_confidence}</p>
                </div>
                <div>
                  <p className="text-ink-muted">Recommendation</p>
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
              className="flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-1.5 text-xs font-medium text-brand hover:bg-brand-soft transition disabled:opacity-50"
            >
              <CheckCircle2 className="h-3.5 w-3.5" /> Ack
            </button>
          )}
          {alert.status !== 'RESOLVED' && (
            <button
              onClick={onResolve}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-ok/25 bg-ok-soft px-3 py-1.5 text-xs font-medium text-ok hover:bg-ok-soft transition disabled:opacity-50"
            >
              <XCircle className="h-3.5 w-3.5" /> Resolve
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

const KPI_TONES: Record<string, string> = {
  amber: 'text-warn', sky: 'text-brand', emerald: 'text-ok',
  red: 'text-crit', slate: 'text-ink-muted', violet: 'text-ink',
}

function KpiCard({
  icon, label, value, tone, sub,
}: {
  icon: ReactNode
  label: string
  value: string
  tone: string
  sub?: string
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-ink-subtle">
        <span className={KPI_TONES[tone] || 'text-ink-muted'}>{icon}</span>
        <span className="truncate text-[10px] font-semibold uppercase tracking-wider">{label}</span>
      </div>
      <p className={`mt-2 text-xl font-bold ${KPI_TONES[tone] || 'text-ink'}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-ink-subtle">{sub}</p>}
    </Card>
  )
}
