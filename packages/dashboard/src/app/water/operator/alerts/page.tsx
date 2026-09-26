'use client'

import { useEffect, useMemo, useState } from 'react'
import { Bell, CheckCircle2, Search, ShieldAlert, ArrowUpCircle, CheckCircle, ClipboardList, History, X } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { TimelinePanel } from '@/components/ui/timeline'
import { waterApi } from '@/features/water/api'
import { useAuth } from '@/context/AuthContext'
import { fmtNumber, fmtDateTime } from '@/lib/format'
import { normalizeSeverity } from '@/lib/severity'
import type { OperationalAlert, AssignableUser, InstructionTemplate, TimelineItem } from '@/features/water/types'

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
  const { user } = useAuth()
  const roles = useMemo(() => {
    const set = new Set((user?.roles || []).map(r => r.toLowerCase()))
    const r = (user?.role || '').toLowerCase()
    if (r) set.add(r)
    return set
  }, [user])
  const canIssue = ['admin', 'water_supervisor', 'aquavision_analyst'].some(x => roles.has(x))
  const canEscalate = ['admin', 'water_supervisor'].some(x => roles.has(x))

  const [alerts, setAlerts] = useState<OperationalAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [issueFor, setIssueFor] = useState<OperationalAlert | null>(null)
  const [timelineFor, setTimelineFor] = useState<number | null>(null)
  const [timeline, setTimeline] = useState<TimelineItem[]>([])
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadAlerts = () => {
    const params: any = { limit: 100 }
    if (statusFilter) params.status = statusFilter
    if (severityFilter) params.severity = severityFilter
    waterApi.getOperationalAlerts(params).then(setAlerts).finally(() => setLoading(false))
  }

  useEffect(() => { loadAlerts() }, [statusFilter, severityFilter])

  const handleAck = async (id: number) => {
    setError(null)
    try { await waterApi.ackOperationalAlert(id, user?.username || 'Operator'); loadAlerts() }
    catch (e: any) { setError(e?.response?.data?.detail || 'Ack failed') }
  }
  const handleInvestigate = async (id: number) => {
    setError(null)
    try { await waterApi.investigateOperationalAlert(id, user?.username || 'Operator'); loadAlerts() }
    catch (e: any) { setError(e?.response?.data?.detail || 'Investigate failed') }
  }
  const handleEscalate = async (id: number) => {
    setError(null)
    try { await waterApi.escalateOperationalAlert(id, user?.username || 'Operator'); loadAlerts() }
    catch (e: any) { setError(e?.response?.data?.detail || 'Escalate failed') }
  }
  const handleResolve = async (id: number) => {
    setError(null)
    const notes = window.prompt('Resolution summary (what was done / verified):', '')
    if (notes === null) return
    try {
      await waterApi.resolveOperationalAlert(id, user?.username || 'Operator', notes || undefined)
      loadAlerts()
    } catch (e: any) { setError(e?.response?.data?.detail || 'Resolve failed') }
  }

  const openTimeline = async (alertId: number) => {
    if (timelineFor === alertId) { setTimelineFor(null); return }
    setTimelineFor(alertId)
    setTimelineLoading(true)
    try { setTimeline(await waterApi.getAlertTimeline(alertId)) }
    catch (e: any) { setError(e?.response?.data?.detail || 'Timeline failed to load') }
    finally { setTimelineLoading(false) }
  }

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

        {error && (
          <div className="rounded-xl border border-crit/25 bg-crit-soft px-4 py-3 text-sm text-crit">{error}</div>
        )}

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
                          <div className="flex flex-col items-end gap-3 sm:min-w-[160px]">
                            <div className="flex flex-col items-end gap-1.5">
                              <Badge tone={statusStyle.tone}>
                                {STATUS_LABELS[alert.status] || alert.status.replace(/_/g, ' ')}
                              </Badge>
                              {alert.status === 'NEW' && alert.sla_due_at && (
                                <span className={`text-[10px] font-semibold ${new Date(alert.sla_due_at) < new Date() ? 'text-crit' : 'text-ink-subtle'}`}>
                                  SLA {new Date(alert.sla_due_at) < new Date() ? 'breached' : `due ${fmtDateTime(alert.sla_due_at)}`}
                                </span>
                              )}
                              {alert.assigned_to && (
                                <span className="text-[10px] text-ink-subtle">Owner: {alert.assigned_to}</span>
                              )}
                            </div>

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
                              {canEscalate && ['NEW', 'ACKNOWLEDGED', 'INVESTIGATING'].includes(alert.status) && (
                                <button onClick={() => handleEscalate(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-soft">
                                  <ArrowUpCircle className="h-3.5 w-3.5" /> Escalate
                                </button>
                              )}
                              {(alert.status === 'NEW' || alert.status === 'ACKNOWLEDGED' || alert.status === 'INVESTIGATING' || alert.status === 'ESCALATED') && (
                                <button onClick={() => handleResolve(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-ok/25 bg-ok-soft px-3 py-1.5 text-xs font-medium text-ok transition-colors hover:bg-ok-soft">
                                  <CheckCircle className="h-3.5 w-3.5" /> Resolve
                                </button>
                              )}
                              {canIssue && (alert.status === 'NEW' || alert.status === 'ACKNOWLEDGED' || alert.status === 'INVESTIGATING' || alert.status === 'ESCALATED') && (
                                <button onClick={() => setIssueFor(alert)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-surface-alt px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-soft">
                                  <ClipboardList className="h-3.5 w-3.5" /> Issue
                                </button>
                              )}
                              <button onClick={() => openTimeline(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-brand/25 hover:text-brand">
                                <History className="h-3.5 w-3.5" /> Timeline
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                      {timelineFor === alert.id && (
                        <TimelinePanel loading={timelineLoading} items={timeline} />
                      )}
                    </Card>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>

      {issueFor && (
        <IssueModal
          alert={issueFor}
          onClose={() => setIssueFor(null)}
          onIssued={() => { setIssueFor(null); loadAlerts() }}
        />
      )}
    </AppShell>
  )
}

// ─── Issue instruction modal (supervisor/admin → officer) ────────────────────

function IssueModal({
  alert, onClose, onIssued,
}: {
  alert: OperationalAlert
  onClose: () => void
  onIssued: () => void
}) {
  const [assignables, setAssignables] = useState<AssignableUser[]>([])
  const [templates, setTemplates] = useState<Record<string, InstructionTemplate>>({})
  const [assigneeId, setAssigneeId] = useState<number | ''>('')
  const [templateKey, setTemplateKey] = useState('')
  const [text, setText] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    waterApi.getAssignables('field_officer').then(setAssignables).catch(() => setAssignables([]))
    waterApi.getInstructionTemplates().then(setTemplates).catch(() => setTemplates({}))
  }, [])

  const pickTemplate = (key: string) => {
    setTemplateKey(key)
    if (key && templates[key]) setText(templates[key].text)
  }

  const submit = async () => {
    const assignee = assignables.find(a => a.id === assigneeId)
    if (!assignee) { setErr('Select who the instruction is assigned to'); return }
    if (text.trim().length < 5) { setErr('Instruction text is required (min 5 characters)'); return }
    setBusy(true)
    setErr(null)
    try {
      await waterApi.issueInstruction(alert.id, {
        instruction_text: text.trim(),
        assigned_to: assignee.username,
        assigned_to_user_id: assignee.id,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
        template_key: templateKey || undefined,
      })
      onIssued()
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to issue instruction')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-line bg-surface p-5 shadow-card"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-ink">Issue instruction</h2>
            <p className="text-xs text-ink-subtle">
              Alert #{alert.id} · {alert.asset_name || `Asset ${alert.asset_id}`} · {alert.alert_type}
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg border border-line p-1.5 text-ink-muted hover:text-ink" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Assign to</label>
            <select
              value={assigneeId}
              onChange={e => setAssigneeId(e.target.value ? Number(e.target.value) : '')}
              className="w-full rounded-xl border border-line-strong bg-surface-alt px-3 py-2.5 text-sm text-ink focus:border-brand/25 focus:outline-none"
            >
              <option value="">Select field officer…</option>
              {assignables.map(a => (
                <option key={a.id} value={a.id}>{a.name} ({a.email})</option>
              ))}
            </select>
            {assignables.length === 0 && (
              <p className="mt-1 text-[11px] text-ink-subtle">No active field officers found.</p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Template (optional)</label>
            <select
              value={templateKey}
              onChange={e => pickTemplate(e.target.value)}
              className="w-full rounded-xl border border-line-strong bg-surface-alt px-3 py-2.5 text-sm text-ink focus:border-brand/25 focus:outline-none"
            >
              <option value="">Free text</option>
              {Object.entries(templates).map(([key, t]) => (
                <option key={key} value={key}>{t.title}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
              Instruction <span className="text-crit">*</span>
            </label>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              rows={4}
              placeholder="What should the officer do, where, and what to record…"
              className="w-full rounded-xl border border-line-strong bg-surface-alt px-3 py-2.5 text-sm text-ink placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Due by (optional, enables overdue tracking)</label>
            <input
              type="datetime-local"
              value={dueAt}
              onChange={e => setDueAt(e.target.value)}
              className="w-full rounded-xl border border-line-strong bg-surface-alt px-3 py-2.5 text-sm text-ink focus:border-brand/25 focus:outline-none"
            />
          </div>

          {err && <p className="text-xs text-crit">{err}</p>}

          <div className="flex gap-2 pt-1">
            <button
              onClick={submit} disabled={busy}
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-brand px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
            >
              <ClipboardList className="h-4 w-4" /> {busy ? 'Issuing…' : 'Issue instruction'}
            </button>
            <button
              onClick={onClose}
              className="rounded-xl border border-line-strong px-4 py-2.5 text-sm text-ink-muted transition hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
