'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ClipboardList, RefreshCw, CheckCircle2, PlayCircle, Send, ShieldCheck,
  XCircle, Bell, AlertTriangle, Clock,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { TimelinePanel } from '@/components/ui/timeline'
import { waterApi } from '@/features/water/api'
import { useAuth } from '@/context/AuthContext'
import { fmtDateTime, timeAgo } from '@/lib/format'
import type {
  AlertQueue, InstructionTemplate, TimelineItem, WorkflowInstruction,
} from '@/features/water/types'

const INSTR_STATUS: Record<string, { label: string; tone: 'sky' | 'amber' | 'violet' | 'emerald' | 'red' | 'slate' }> = {
  ISSUED: { label: 'Assigned', tone: 'sky' },
  ACCEPTED: { label: 'Accepted', tone: 'amber' },
  IN_PROGRESS: { label: 'In progress', tone: 'violet' },
  OVERDUE: { label: 'Overdue', tone: 'red' },
  REPORTED: { label: 'Report submitted', tone: 'emerald' },
  VERIFIED: { label: 'Verified', tone: 'emerald' },
  REJECTED: { label: 'Rejected', tone: 'red' },
  WAIVED: { label: 'Waived', tone: 'slate' },
}

const SEV_TONE: Record<string, 'red' | 'amber' | 'sky' | 'slate'> = {
  CRITICAL: 'red', WARNING: 'amber', ADVISORY: 'sky', WATCH: 'slate',
}

export default function MyTasksPage() {
  const { user } = useAuth()
  const role = (user?.role || '').toLowerCase()
  const allRoles = useMemo(() => {
    const set = new Set((user?.roles || []).map(r => r.toLowerCase()))
    if (role) set.add(role)
    return set
  }, [user, role])
  const canVerify = ['admin', 'water_supervisor', 'aquavision_analyst'].some(r => allRoles.has(r))

  const [queue, setQueue] = useState<AlertQueue | null>(null)
  const [templates, setTemplates] = useState<Record<string, InstructionTemplate>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [timelineFor, setTimelineFor] = useState<number | null>(null)
  const [timeline, setTimeline] = useState<TimelineItem[]>([])
  const [timelineLoading, setTimelineLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([waterApi.getAlertQueue(), waterApi.getInstructionTemplates()])
      .then(([q, t]) => { setQueue(q); setTemplates(t) })
      .catch(e => setError(e?.response?.data?.detail || e.message || 'Failed to load queue'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const run = async (id: number, fn: () => Promise<unknown>) => {
    setBusyId(id)
    setError(null)
    try {
      await fn()
      load()
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Action failed')
    } finally {
      setBusyId(null)
    }
  }

  const openTimeline = async (alertId: number) => {
    if (timelineFor === alertId) { setTimelineFor(null); return }
    setTimelineFor(alertId)
    setTimelineLoading(true)
    try {
      setTimeline(await waterApi.getAlertTimeline(alertId))
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Timeline failed to load')
    } finally {
      setTimelineLoading(false)
    }
  }

  const counts = queue?.counts
  const myTasks = queue?.instructions_my ?? []
  const toVerify = queue?.instructions_to_verify ?? []
  const newAlerts = queue?.alerts_new ?? []

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="My Tasks"
          description={
            counts
              ? `${counts.instructions_my} assigned · ${counts.instructions_to_verify} awaiting verification · ${counts.alerts_sla_breached} SLA breached`
              : 'Your instructions and alerts, by role'
          }
          icon={<ClipboardList className="h-6 w-6" />}
          accent="bg-brand-soft text-brand"
          action={
            <button
              onClick={load}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line-strong bg-surface-alt px-4 py-2 text-sm text-ink-muted transition-colors hover:border-brand/25 hover:text-brand"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
          }
          badge={counts && counts.badge > 0 ? <Badge tone="red">{counts.badge} open</Badge> : undefined}
        />

        {error && (
          <div className="rounded-xl border border-crit/25 bg-crit-soft px-4 py-3 text-sm text-crit">{error}</div>
        )}

        {loading && !queue ? (
          <Spinner label="Loading your tasks" />
        ) : (
          <>
            {/* ── Awaiting verification (supervisor / admin / analyst) ── */}
            {canVerify && (
              <section className="space-y-3">
                <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-muted">
                  <ShieldCheck className="h-4 w-4" /> Awaiting verification
                  <Badge tone="emerald">{toVerify.length}</Badge>
                </h2>
                {toVerify.length === 0 ? (
                  <EmptyState title="Nothing to verify" message="Submitted reports will appear here" />
                ) : (
                  toVerify.map(instr => (
                    <VerifyCard
                      key={instr.id}
                      instr={instr}
                      busy={busyId === instr.id}
                      onVerify={note => run(instr.id, () => waterApi.verifyInstruction(instr.id, note))}
                      onReject={reason => run(instr.id, () => waterApi.rejectInstruction(instr.id, reason))}
                      onTimeline={() => openTimeline(instr.alert_id)}
                    />
                  ))
                )}
              </section>
            )}

            {/* ── My tasks ── */}
            <section className="space-y-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-muted">
                <ClipboardList className="h-4 w-4" /> My tasks
                <Badge tone="sky">{myTasks.length}</Badge>
              </h2>
              {myTasks.length === 0 ? (
                <EmptyState title="No tasks assigned" message="New instructions will appear here when a supervisor issues them" />
              ) : (
                myTasks.map(instr => (
                  <TaskCard
                    key={instr.id}
                    instr={instr}
                    template={instr.template_key ? templates[instr.template_key] : undefined}
                    busy={busyId === instr.id}
                    canVerify={canVerify}
                    onAccept={() => run(instr.id, () => waterApi.acceptInstruction(instr.id))}
                    onStart={() => run(instr.id, () => waterApi.progressInstruction(instr.id))}
                    onReport={(text, data) => run(instr.id, () => waterApi.reportInstruction(instr.id, text, data))}
                    onVerify={note => run(instr.id, () => waterApi.verifyInstruction(instr.id, note))}
                    onTimeline={() => openTimeline(instr.alert_id)}
                  />
                ))
              )}
            </section>

            {/* ── Alerts needing acknowledgment ── */}
            <section className="space-y-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-muted">
                <Bell className="h-4 w-4" /> Alerts needing attention
                <Badge tone={newAlerts.some(a => a.sla_breached) ? 'red' : 'sky'}>{newAlerts.length}</Badge>
              </h2>
              {newAlerts.length === 0 ? (
                <EmptyState title="No new alerts" message="Everything is acknowledged" />
              ) : (
                newAlerts.slice(0, 20).map(alert => (
                  <Card key={alert.id} className={`border-l-4 ${alert.sla_breached ? 'border-l-crit' : alert.severity === 'CRITICAL' ? 'border-l-sev-critical' : 'border-l-sev-warning'}`}>
                    <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-ink">{alert.asset_name || `Asset ${alert.asset_id}`}</span>
                          <Badge tone={SEV_TONE[alert.severity] || 'slate'}>{alert.severity}</Badge>
                          <span className="text-xs text-ink-subtle">{alert.alert_type.replace(/_/g, ' ')}</span>
                          {alert.alert_source && <Badge tone="slate">{alert.alert_source}</Badge>}
                        </div>
                        <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{alert.message}</p>
                        <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-ink-subtle">
                          <span>{timeAgo(alert.created_at)}</span>
                          {alert.sla_due_at && (
                            <span className={alert.sla_breached ? 'font-semibold text-crit' : ''}>
                              <Clock className="mr-1 inline h-3 w-3" />
                              SLA {alert.sla_breached ? 'breached' : `due ${fmtDateTime(alert.sla_due_at)}`}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button
                          onClick={() => run(alert.id, () => waterApi.ackOperationalAlert(alert.id, user?.username || 'Operator'))}
                          disabled={busyId === alert.id}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-2 text-xs font-medium text-brand transition hover:bg-brand-soft disabled:opacity-50"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" /> Acknowledge
                        </button>
                        <button
                          onClick={() => openTimeline(alert.id)}
                          className="rounded-lg border border-line-strong px-3 py-2 text-xs font-medium text-ink-muted transition hover:border-brand/25 hover:text-brand"
                        >
                          Timeline
                        </button>
                      </div>
                    </div>
                    {timelineFor === alert.id && <TimelinePanel loading={timelineLoading} items={timeline} />}
                  </Card>
                ))
              )}
            </section>
          </>
        )}
      </div>
    </AppShell>
  )
}

// ─── Task card (officer flow: accept → start → report) ───────────────────────

function TaskCard({
  instr, template, busy, canVerify, onAccept, onStart, onReport, onVerify, onTimeline,
}: {
  instr: WorkflowInstruction
  template?: InstructionTemplate
  busy: boolean
  canVerify: boolean
  onAccept: () => void
  onStart: () => void
  onReport: (text: string, data?: Record<string, unknown>) => void
  onVerify: (note: string) => void
  onTimeline: () => void
}) {
  const [showReport, setShowReport] = useState(false)
  const [reportText, setReportText] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [verifyNote, setVerifyNote] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const st = INSTR_STATUS[instr.status] || { label: instr.status, tone: 'slate' as const }
  const overdue = instr.due_at && new Date(instr.due_at) < new Date() &&
    ['ISSUED', 'ACCEPTED', 'IN_PROGRESS'].includes(instr.status)

  const submitReport = () => {
    if (reportText.trim().length < 5) {
      setFormError('Report text is required (min 5 characters)')
      return
    }
    const data: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(fields)) {
      if (v.trim()) data[k] = v.trim()
    }
    setFormError(null)
    setShowReport(false)
    setReportText('')
    setFields({})
    onReport(reportText.trim(), Object.keys(data).length ? data : undefined)
  }

  return (
    <Card className={`border-l-4 ${overdue ? 'border-l-crit' : 'border-l-brand'}`}>
      <div className="space-y-3 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-ink">{instr.asset_name || `Asset ${instr.asset_id}`}</span>
              <Badge tone={st.tone}>{st.label}</Badge>
              {instr.alert_severity && <Badge tone={SEV_TONE[instr.alert_severity] || 'slate'}>{instr.alert_severity}</Badge>}
              {instr.template_key && <Badge tone="slate">{template?.title || instr.template_key}</Badge>}
            </div>
            <p className="mt-2 text-sm text-ink">{instr.instruction_text}</p>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-subtle">
              <span>From: <strong className="text-ink-muted">{instr.issued_by}</strong> ({instr.issued_role})</span>
              <span>Issued: {timeAgo(instr.created_at)}</span>
              {instr.due_at && (
                <span className={overdue ? 'font-semibold text-crit' : ''}>
                  Due: {fmtDateTime(instr.due_at)}{overdue ? ' (overdue)' : ''}
                </span>
              )}
            </div>
            {instr.alert_message && (
              <Link
                href="/water/operator/alerts"
                className="mt-2 inline-block text-xs font-medium text-brand hover:underline"
              >
                Alert: {instr.alert_type} → open alerts page
              </Link>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            {(instr.status === 'ISSUED' || instr.status === 'OVERDUE') && (
              <button
                onClick={onAccept} disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-2 text-xs font-medium text-brand transition disabled:opacity-50"
              >
                <CheckCircle2 className="h-3.5 w-3.5" /> Accept
              </button>
            )}
            {instr.status === 'ACCEPTED' && (
              <button
                onClick={onStart} disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-warn/25 bg-warn-soft px-3 py-2 text-xs font-medium text-warn transition disabled:opacity-50"
              >
                <PlayCircle className="h-3.5 w-3.5" /> Start work
              </button>
            )}
            {['ACCEPTED', 'IN_PROGRESS', 'OVERDUE'].includes(instr.status) && (
              <button
                onClick={() => setShowReport(v => !v)} disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-ok/25 bg-ok-soft px-3 py-2 text-xs font-medium text-ok transition disabled:opacity-50"
              >
                <Send className="h-3.5 w-3.5" /> Submit report
              </button>
            )}
            <button
              onClick={onTimeline}
              className="rounded-lg border border-line-strong px-3 py-2 text-xs font-medium text-ink-muted transition hover:border-brand/25 hover:text-brand"
            >
              Timeline
            </button>
          </div>
        </div>

        {/* Own submitted report */}
        {instr.status === 'REPORTED' && instr.report_text && (
          <div className="rounded-xl border border-ok/25 bg-ok-soft p-3">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ok">
              Your report · {instr.reported_at ? fmtDateTime(instr.reported_at) : ''}
            </p>
            <p className="text-sm text-ink">{instr.report_text}</p>
            {instr.report_data && Object.keys(instr.report_data).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-ok">
                {Object.entries(instr.report_data).map(([k, v]) => (
                  <span key={k}>{k.replace(/_/g, ' ')}: <strong>{String(v)}</strong></span>
                ))}
              </div>
            )}
            <p className="mt-2 text-[11px] text-ok/80">Waiting for supervisor verification.</p>
          </div>
        )}

        {/* Verified / rejected decision */}
        {['VERIFIED', 'REJECTED', 'WAIVED'].includes(instr.status) && instr.decision_note && (
          <div className={`rounded-xl border p-3 ${instr.status === 'REJECTED' ? 'border-crit/25 bg-crit-soft' : 'border-line-strong bg-surface-alt'}`}>
            <p className={`text-[11px] font-semibold uppercase tracking-wider ${instr.status === 'REJECTED' ? 'text-crit' : 'text-ink-muted'}`}>
              {instr.status === 'REJECTED' ? 'Rejected' : instr.status === 'WAIVED' ? 'Waived' : 'Verified'} by {instr.verified_by || 'supervisor'}
            </p>
            <p className="text-sm text-ink-muted">{instr.decision_note}</p>
          </div>
        )}

        {/* Report form */}
        {showReport && (
          <div className="space-y-3 rounded-xl border border-line bg-surface-alt p-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
                Action report <span className="text-crit">*</span>
              </label>
              <textarea
                value={reportText}
                onChange={e => setReportText(e.target.value)}
                rows={3}
                placeholder="What was done, what you observed, current conditions…"
                className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
              />
            </div>
            {template && template.report_fields.map(f => (
              <div key={f}>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
                  {f.replace(/_/g, ' ')}
                </label>
                <input
                  value={fields[f] || ''}
                  onChange={e => setFields(prev => ({ ...prev, [f]: e.target.value }))}
                  className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
                  placeholder={f.replace(/_/g, ' ')}
                />
              </div>
            ))}
            {formError && <p className="text-xs text-crit">{formError}</p>}
            <div className="flex gap-2">
              <button
                onClick={submitReport} disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
              >
                <Send className="h-4 w-4" /> Submit report
              </button>
              <button
                onClick={() => setShowReport(false)}
                className="rounded-lg border border-line-strong px-4 py-2 text-sm text-ink-muted transition hover:text-ink"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Supervisor verify inline (on own task, e.g. supervisor acting) */}
        {canVerify && instr.status === 'REPORTED' && (
          <div className="flex flex-wrap items-end gap-2 rounded-xl border border-warn/25 bg-warn-soft p-3">
            <div className="min-w-[240px] flex-1">
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-warn">Verification note</label>
              <input
                value={verifyNote}
                onChange={e => setVerifyNote(e.target.value)}
                placeholder="e.g. Readings confirmed against gauge"
                className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
              />
            </div>
            <button
              onClick={() => {
                if (verifyNote.trim().length < 3) { setFormError('Verification note required'); return }
                setFormError(null); onVerify(verifyNote.trim())
              }}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-ok px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
            >
              <ShieldCheck className="h-4 w-4" /> Verify
            </button>
          </div>
        )}
        {formError && !showReport && <p className="text-xs text-crit">{formError}</p>}
      </div>
    </Card>
  )
}

// ─── Verify card (supervisor inbox) ──────────────────────────────────────────

function VerifyCard({
  instr, busy, onVerify, onReject, onTimeline,
}: {
  instr: WorkflowInstruction
  busy: boolean
  onVerify: (note: string) => void
  onReject: (reason: string) => void
  onTimeline: () => void
}) {
  const [note, setNote] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  return (
    <Card className="border-l-4 border-l-warn">
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-ink">{instr.asset_name || `Asset ${instr.asset_id}`}</span>
          <Badge tone="emerald">Report submitted</Badge>
          {instr.alert_severity && <Badge tone={SEV_TONE[instr.alert_severity] || 'slate'}>{instr.alert_severity}</Badge>}
          <span className="text-xs text-ink-subtle">#{instr.id}</span>
        </div>
        <p className="text-sm text-ink-muted">
          <strong className="text-ink">{instr.instruction_text}</strong>
        </p>
        <div className="rounded-xl border border-ok/25 bg-ok-soft p-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ok">
            Report by {instr.reported_by || instr.assigned_to} · {instr.reported_at ? fmtDateTime(instr.reported_at) : ''}
          </p>
          <p className="text-sm text-ink">{instr.report_text}</p>
          {instr.report_data && Object.keys(instr.report_data).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-ok">
              {Object.entries(instr.report_data).map(([k, v]) => (
                <span key={k}>{k.replace(/_/g, ' ')}: <strong>{String(v)}</strong></span>
              ))}
            </div>
          )}
        </div>
        {err && <p className="text-xs text-crit">{err}</p>}
        {rejecting ? (
          <div className="space-y-2">
            <input
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Rejection reason (required)"
              className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (note.trim().length < 3) { setErr('Reason required (min 3 chars)'); return }
                  setErr(null); setRejecting(false); onReject(note.trim())
                }}
                disabled={busy}
                className="rounded-lg border border-crit/25 bg-crit-soft px-3 py-2 text-xs font-medium text-crit disabled:opacity-50"
              >
                Confirm reject
              </button>
              <button onClick={() => { setRejecting(false); setErr(null) }} className="px-3 py-2 text-xs text-ink-muted">Cancel</button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <div className="flex min-w-[240px] flex-1 items-center gap-2">
              <input
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="Verification note (required)"
                className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
              />
            </div>
            <button
              onClick={() => {
                if (note.trim().length < 3) { setErr('Verification note required (min 3 chars)'); return }
                setErr(null); onVerify(note.trim())
              }}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-ok px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
            >
              <ShieldCheck className="h-4 w-4" /> Verify
            </button>
            <button
              onClick={() => { setRejecting(true); setErr(null) }}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-crit/25 bg-crit-soft px-4 py-2 text-sm font-medium text-crit transition disabled:opacity-50"
            >
              <XCircle className="h-4 w-4" /> Reject
            </button>
            <button
              onClick={onTimeline}
              className="rounded-lg border border-line-strong px-4 py-2 text-sm text-ink-muted transition hover:border-brand/25 hover:text-brand"
            >
              Timeline
            </button>
          </div>
        )}
      </div>
    </Card>
  )
}
