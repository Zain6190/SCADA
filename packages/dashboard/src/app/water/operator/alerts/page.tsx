'use client'

import { useEffect, useState } from 'react'
import { Bell, CheckCircle2, Search, ShieldAlert, ArrowUpCircle, CheckCircle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtNumber, fmtDateTime } from '@/lib/format'
import { normalizeSeverity } from '@/lib/severity'
import type { OperationalAlert } from '@/features/water/types'

const STATUS_STYLES: Record<string, { bg: string; text: string; border: string; tone: 'slate' | 'sky' | 'amber' | 'violet' | 'emerald' | 'red' }> = {
  NEW: { bg: 'bg-red-500/10', text: 'text-red-300', border: 'border-red-500/30', tone: 'red' },
  ACKNOWLEDGED: { bg: 'bg-sky-500/10', text: 'text-sky-300', border: 'border-sky-500/30', tone: 'sky' },
  INVESTIGATING: { bg: 'bg-amber-500/10', text: 'text-amber-300', border: 'border-amber-500/30', tone: 'amber' },
  ESCALATED: { bg: 'bg-violet-500/10', text: 'text-violet-300', border: 'border-violet-500/30', tone: 'violet' },
  RESOLVED: { bg: 'bg-emerald-500/10', text: 'text-emerald-300', border: 'border-emerald-500/30', tone: 'emerald' },
  FALSE_OR_INVALID_DATA: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/30', tone: 'slate' },
}

const STATUS_LABELS: Record<string, string> = {
  NEW: 'New',
  ACKNOWLEDGED: 'Acknowledged',
  INVESTIGATING: 'Investigating',
  ESCALATED: 'Escalated',
  RESOLVED: 'Resolved',
  FALSE_OR_INVALID_DATA: 'Invalid',
}

const SEVERITY_BORDER: Record<string, string> = {
  CRITICAL: 'border-l-red-400',
  WARNING: 'border-l-amber-400',
  ADVISORY: 'border-l-yellow-400',
  WATCH: 'border-l-sky-400',
  NORMAL: 'border-l-emerald-400',
}

export default function OperatorAlertsPage() {
  const [alerts, setAlerts] = useState<OperationalAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const loadAlerts = () => {
    const params: any = { limit: 100 }
    if (statusFilter) params.status = statusFilter
    if (severityFilter) params.severity = severityFilter
    waterApi.getOperationalAlerts(params).then(setAlerts).finally(() => setLoading(false))
  }

  useEffect(() => { loadAlerts() }, [statusFilter, severityFilter])

  const handleAck = async (id: number) => { await waterApi.ackOperationalAlert(id, 'Operator'); loadAlerts() }
  const handleInvestigate = async (id: number) => { await waterApi.investigateOperationalAlert(id, 'Operator'); loadAlerts() }
  const handleEscalate = async (id: number) => { await waterApi.escalateOperationalAlert(id, 'Operator'); loadAlerts() }
  const handleResolve = async (id: number) => { await waterApi.resolveOperationalAlert(id, 'Operator'); loadAlerts() }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Operational Alerts"
          description="Full workflow: Ack → Investigate → Escalate → Resolve"
          icon={<Bell className="h-6 w-6" />}
          accent="bg-red-500/10 text-red-300"
          action={
            <button onClick={loadAlerts} className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm text-slate-300 transition-colors hover:border-sky-500/40 hover:text-sky-300">
              Refresh
            </button>
          }
        />

        {loading ? (
          <Spinner label="Loading alerts" />
        ) : (
          <>
            {/* Filters */}
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-500">Status</label>
                <select
                  value={statusFilter}
                  onChange={e => setStatusFilter(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2.5 text-sm text-slate-300 focus:border-sky-500/50 focus:outline-none"
                >
                  <option value="">All Status</option>
                  <option value="NEW">New</option>
                  <option value="ACKNOWLEDGED">Acknowledged</option>
                  <option value="INVESTIGATING">Investigating</option>
                  <option value="ESCALATED">Escalated</option>
                  <option value="RESOLVED">Resolved</option>
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-500">Severity</label>
                <select
                  value={severityFilter}
                  onChange={e => setSeverityFilter(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2.5 text-sm text-slate-300 focus:border-sky-500/50 focus:outline-none"
                >
                  <option value="">All Severity</option>
                  <option value="CRITICAL">Critical</option>
                  <option value="WARNING">Warning</option>
                  <option value="WATCH">Watch</option>
                </select>
              </div>
            </div>

            <p className="text-xs text-slate-500">
              <span className="font-semibold text-slate-400">{alerts.length}</span> alert{alerts.length !== 1 ? 's' : ''}
            </p>

            {alerts.length === 0 ? (
              <EmptyState title="No alerts found" message="All systems operating normally" />
            ) : (
              <div className="space-y-3">
                {alerts.map(alert => {
                  const isExpanded = expandedId === alert.id
                  const statusStyle = STATUS_STYLES[alert.status] || STATUS_STYLES.NEW
                  const borderClass = SEVERITY_BORDER[alert.severity] || 'border-l-slate-500'
                  return (
                    <Card key={alert.id} className={`border-l-4 ${borderClass} overflow-hidden`}>
                      <div className="p-4 sm:p-5">
                        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <span className="font-bold text-slate-100">{alert.asset_name || `Asset ${alert.asset_id}`}</span>
                              <span className="text-slate-600">·</span>
                              <span className="text-sm text-slate-400">{alert.alert_type.replace(/_/g, ' ')}</span>
                              {alert.alert_source && <Badge tone="slate">{alert.alert_source}</Badge>}
                              {alert.episode_id && <Badge tone="sky">EP-{alert.episode_id}</Badge>}
                            </div>

                            <p className="text-sm text-slate-400 mb-3">{alert.message}</p>

                            {/* Readings */}
                            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                              {alert.reading_level_ft != null && (
                                <span className="text-slate-500">
                                  Level: <strong className="font-mono text-slate-200">{alert.reading_level_ft.toFixed(2)} ft</strong>
                                </span>
                              )}
                              {alert.reading_inflow_cusecs != null && (
                                <span className="text-slate-500">
                                  Inflow: <strong className="font-mono text-slate-200">{fmtNumber(alert.reading_inflow_cusecs, 0)}</strong>
                                </span>
                              )}
                              {alert.reading_outflow_cusecs != null && (
                                <span className="text-slate-500">
                                  Outflow: <strong className="font-mono text-slate-200">{fmtNumber(alert.reading_outflow_cusecs, 0)}</strong>
                                </span>
                              )}
                              {alert.rate_of_change_ft_6h != null && (
                                <span className="text-slate-500">
                                  Rate: <strong className="font-mono text-slate-200">+{alert.rate_of_change_ft_6h.toFixed(2)} ft/6h</strong>
                                </span>
                              )}
                            </div>

                            {/* Downstream Impact */}
                            {alert.downstream_population_exposed != null && alert.downstream_population_exposed > 0 && (
                              <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
                                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-amber-400">Downstream Impact</p>
                                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-amber-300/80">
                                  <span>Population: <strong>{fmtNumber(alert.downstream_population_exposed, 0)}</strong></span>
                                  {alert.downstream_bridges_at_risk != null && alert.downstream_bridges_at_risk > 0 && (
                                    <span>Bridges: <strong>{alert.downstream_bridges_at_risk}</strong></span>
                                  )}
                                  {alert.downstream_hospitals_at_risk != null && alert.downstream_hospitals_at_risk > 0 && (
                                    <span>Hospitals: <strong>{alert.downstream_hospitals_at_risk}</strong></span>
                                  )}
                                  {alert.downstream_furthest_asset && (
                                    <span>Furthest: <strong>{alert.downstream_furthest_asset}</strong></span>
                                  )}
                                  {alert.downstream_furthest_arrival_hours != null && (
                                    <span>Arrival: <strong>{alert.downstream_furthest_arrival_hours.toFixed(0)}h</strong></span>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Flood Classification */}
                            {alert.flood_probability != null && (
                              <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/5 p-3">
                                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-red-400">Flood Classification</p>
                                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-red-300/80">
                                  <span>Probability: <strong>{(alert.flood_probability * 100).toFixed(1)}%</strong></span>
                                  {alert.flood_severity && <span>Severity: <strong>{alert.flood_severity}</strong></span>}
                                  {alert.flood_recommendation && <span>Rec: <strong>{alert.flood_recommendation}</strong></span>}
                                </div>
                              </div>
                            )}

                            {/* Timestamps */}
                            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px] text-slate-600">
                              <span>Created: {fmtDateTime(alert.created_at)}</span>
                              {alert.acknowledged_at && <span>Acked: {fmtDateTime(alert.acknowledged_at)}</span>}
                              {alert.resolved_at && <span>Resolved: {fmtDateTime(alert.resolved_at)}</span>}
                            </div>
                          </div>

                          {/* Right: Status + Actions */}
                          <div className="flex flex-col items-end gap-3 sm:min-w-[140px]">
                            <Badge tone={statusStyle.tone}>
                              {STATUS_LABELS[alert.status] || alert.status.replace(/_/g, ' ')}
                            </Badge>

                            <div className="flex flex-wrap gap-2 justify-end">
                              {alert.status === 'NEW' && (
                                <button onClick={() => handleAck(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-300 transition-colors hover:bg-sky-500/20">
                                  <CheckCircle2 className="h-3.5 w-3.5" /> Acknowledge
                                </button>
                              )}
                              {alert.status === 'ACKNOWLEDGED' && (
                                <button onClick={() => handleInvestigate(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-300 transition-colors hover:bg-amber-500/20">
                                  <Search className="h-3.5 w-3.5" /> Investigate
                                </button>
                              )}
                              {alert.status === 'INVESTIGATING' && (
                                <button onClick={() => handleEscalate(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-300 transition-colors hover:bg-violet-500/20">
                                  <ArrowUpCircle className="h-3.5 w-3.5" /> Escalate
                                </button>
                              )}
                              {(alert.status === 'NEW' || alert.status === 'ACKNOWLEDGED' || alert.status === 'INVESTIGATING' || alert.status === 'ESCALATED') && (
                                <button onClick={() => handleResolve(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/20">
                                  <CheckCircle className="h-3.5 w-3.5" /> Resolve
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
