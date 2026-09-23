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
  NEW: { bg: 'bg-crit-soft', text: 'text-crit', border: 'border-crit/25', tone: 'red' },
  ACKNOWLEDGED: { bg: 'bg-brand-soft', text: 'text-brand', border: 'border-brand/25', tone: 'sky' },
  INVESTIGATING: { bg: 'bg-warn-soft', text: 'text-warn', border: 'border-warn/25', tone: 'amber' },
  ESCALATED: { bg: 'bg-brand-soft', text: 'text-brand', border: 'border-brand/25', tone: 'violet' },
  RESOLVED: { bg: 'bg-ok-soft', text: 'text-ok', border: 'border-ok/25', tone: 'emerald' },
  FALSE_OR_INVALID_DATA: { bg: 'bg-surface-sunken', text: 'text-ink-muted', border: 'border-line-strong', tone: 'slate' },
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
  CRITICAL: 'border-l-sev-critical',
  WARNING: 'border-l-sev-warning',
  ADVISORY: 'border-l-sev-stressed',
  WATCH: 'border-l-brand',
  NORMAL: 'border-l-sev-normal',
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
          accent="bg-crit-soft text-crit"
          action={
            <button onClick={loadAlerts} className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2 text-sm text-ink-muted transition-colors hover:border-brand/25 hover:text-brand">
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
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Status</label>
                <select
                  value={statusFilter}
                  onChange={e => setStatusFilter(e.target.value)}
                  className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2.5 text-sm text-ink-muted focus:border-brand/25 focus:outline-none"
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
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Severity</label>
                <select
                  value={severityFilter}
                  onChange={e => setSeverityFilter(e.target.value)}
                  className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2.5 text-sm text-ink-muted focus:border-brand/25 focus:outline-none"
                >
                  <option value="">All Severity</option>
                  <option value="CRITICAL">Critical</option>
                  <option value="WARNING">Warning</option>
                  <option value="WATCH">Watch</option>
                </select>
              </div>
            </div>

            <p className="text-xs text-ink-subtle">
              <span className="font-semibold text-ink-muted">{alerts.length}</span> alert{alerts.length !== 1 ? 's' : ''}
            </p>

            {alerts.length === 0 ? (
              <EmptyState title="No alerts found" message="All systems operating normally" />
            ) : (
              <div className="space-y-3">
                {alerts.map(alert => {
                  const isExpanded = expandedId === alert.id
                  const statusStyle = STATUS_STYLES[alert.status] || STATUS_STYLES.NEW
                  const borderClass = SEVERITY_BORDER[alert.severity] || 'border-l-line-strong'
                  return (
                    <Card key={alert.id} className={`border-l-4 ${borderClass} overflow-hidden`}>
                      <div className="p-4 sm:p-5">
                        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <span className="font-bold text-ink">{alert.asset_name || `Asset ${alert.asset_id}`}</span>
                              <span className="text-ink-subtle">·</span>
                              <span className="text-sm text-ink-muted">{alert.alert_type.replace(/_/g, ' ')}</span>
                              {alert.alert_source && <Badge tone="slate">{alert.alert_source}</Badge>}
                              {alert.episode_id && <Badge tone="sky">EP-{alert.episode_id}</Badge>}
                            </div>

                            <p className="text-sm text-ink-muted mb-3">{alert.message}</p>

                            {/* Readings */}
                            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                              {alert.reading_level_ft != null && (
                                <span className="text-ink-subtle">
                                  Level: <strong className="font-mono text-ink">{alert.reading_level_ft.toFixed(2)} ft</strong>
                                </span>
                              )}
                              {alert.reading_inflow_cusecs != null && (
                                <span className="text-ink-subtle">
                                  Inflow: <strong className="font-mono text-ink">{fmtNumber(alert.reading_inflow_cusecs, 0)}</strong>
                                </span>
                              )}
                              {alert.reading_outflow_cusecs != null && (
                                <span className="text-ink-subtle">
                                  Outflow: <strong className="font-mono text-ink">{fmtNumber(alert.reading_outflow_cusecs, 0)}</strong>
                                </span>
                              )}
                              {alert.rate_of_change_ft_6h != null && (
                                <span className="text-ink-subtle">
                                  Rate: <strong className="font-mono text-ink">+{alert.rate_of_change_ft_6h.toFixed(2)} ft/6h</strong>
                                </span>
                              )}
                            </div>

                            {/* Downstream Impact */}
                            {alert.downstream_population_exposed != null && alert.downstream_population_exposed > 0 && (
                              <div className="mt-3 rounded-xl border border-warn/25 bg-warn-soft p-3">
                                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-warn">Downstream Impact</p>
                                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-warn">
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
                              <div className="mt-3 rounded-xl border border-crit/25 bg-crit-soft p-3">
                                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-crit">Flood Classification</p>
                                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-crit">
                                  <span>Probability: <strong>{(alert.flood_probability * 100).toFixed(1)}%</strong></span>
                                  {alert.flood_severity && <span>Severity: <strong>{alert.flood_severity}</strong></span>}
                                  {alert.flood_recommendation && <span>Rec: <strong>{alert.flood_recommendation}</strong></span>}
                                </div>
                              </div>
                            )}

                            {/* Timestamps */}
                            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px] text-ink-subtle">
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
                                <button onClick={() => handleAck(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-soft">
                                  <CheckCircle2 className="h-3.5 w-3.5" /> Acknowledge
                                </button>
                              )}
                              {alert.status === 'ACKNOWLEDGED' && (
                                <button onClick={() => handleInvestigate(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-warn/25 bg-warn-soft px-3 py-1.5 text-xs font-medium text-warn transition-colors hover:bg-warn-soft">
                                  <Search className="h-3.5 w-3.5" /> Investigate
                                </button>
                              )}
                              {alert.status === 'INVESTIGATING' && (
                                <button onClick={() => handleEscalate(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-soft">
                                  <ArrowUpCircle className="h-3.5 w-3.5" /> Escalate
                                </button>
                              )}
                              {(alert.status === 'NEW' || alert.status === 'ACKNOWLEDGED' || alert.status === 'INVESTIGATING' || alert.status === 'ESCALATED') && (
                                <button onClick={() => handleResolve(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-ok/25 bg-ok-soft px-3 py-1.5 text-xs font-medium text-ok transition-colors hover:bg-ok-soft">
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
