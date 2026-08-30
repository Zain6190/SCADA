'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtDateTime } from '@/lib/format'

interface StressAlert {
  id: number
  region_id: number
  region_name: string | null
  week_start_date: string
  alert_type: string
  severity: string
  wai_score: number | null
  rainfall_anomaly: number | null
  et_anomaly: number | null
  surface_water_change_pct: number | null
  status: string
  confidence: number | null
  source: string | null
  notes: string | null
  created_at: string
  acknowledged_at: string | null
  resolved_at: string | null
}

const SEVERITY_TONE: Record<string, 'red' | 'amber' | 'sky' | 'emerald'> = {
  Critical: 'red',
  Severe: 'amber',
  Warning: 'sky',
  Stressed: 'sky',
  Moderate: 'emerald',
}

const STATUS_TONE: Record<string, 'red' | 'sky' | 'emerald' | 'slate'> = {
  New: 'red',
  Acknowledged: 'sky',
  Resolved: 'emerald',
}

const ALERT_LABELS: Record<string, string> = {
  WAI_CRITICAL: 'WAI Critical',
  WAI_SEVERE: 'WAI Severe',
  RAINFALL_DEFICIT: 'Rainfall Deficit',
  HIGH_ET: 'High Evapotranspiration',
}

export default function StressAlertsPage() {
  const [alerts, setAlerts] = useState<StressAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')

  const loadAlerts = () => {
    const params: any = { limit: 100 }
    if (statusFilter) params.status = statusFilter
    if (severityFilter) params.severity = severityFilter
    waterApi.getStressAlerts(params).then(setAlerts).finally(() => setLoading(false))
  }

  useEffect(() => { loadAlerts() }, [statusFilter, severityFilter])

  const handleAck = async (id: number) => { await waterApi.ackStressAlert(id); loadAlerts() }
  const handleResolve = async (id: number) => { await waterApi.resolveStressAlert(id); loadAlerts() }

  const activeAlerts = alerts.filter(a => a.status !== 'Resolved')
  const resolvedAlerts = alerts.filter(a => a.status === 'Resolved')

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Stress Alerts"
          description="Region-level WAI alerts from the prediction pipeline"
          icon={<AlertTriangle className="h-6 w-6" />}
          accent="bg-amber-500/10 text-amber-300"
          action={
            <button onClick={loadAlerts} className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm text-slate-300 transition-colors hover:border-sky-500/40 hover:text-sky-300">
              Refresh
            </button>
          }
        />

        {loading ? (
          <Spinner label="Loading stress alerts" />
        ) : (
          <>
            {/* Filters */}
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-500">Status</label>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2.5 text-sm text-slate-300 focus:border-sky-500/50 focus:outline-none">
                  <option value="">All Status</option>
                  <option value="New">New</option>
                  <option value="Acknowledged">Acknowledged</option>
                  <option value="Resolved">Resolved</option>
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-500">Severity</label>
                <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)} className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2.5 text-sm text-slate-300 focus:border-sky-500/50 focus:outline-none">
                  <option value="">All Severity</option>
                  <option value="Critical">Critical</option>
                  <option value="Severe">Severe</option>
                  <option value="Warning">Warning</option>
                </select>
              </div>
            </div>

            {/* Summary */}
            <div className="flex gap-4 text-sm">
              <span className="text-slate-500">Active: <strong className="text-slate-200">{activeAlerts.length}</strong></span>
              <span className="text-slate-500">Resolved: <strong className="text-slate-400">{resolvedAlerts.length}</strong></span>
            </div>

            {alerts.length === 0 ? (
              <EmptyState title="No stress alerts" message="All regions operating within normal thresholds" />
            ) : (
              <div className="space-y-3">
                {alerts.map(alert => (
                  <Card key={alert.id} className="overflow-hidden">
                    <div className="p-4 sm:p-5">
                      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <span className="font-bold text-slate-100">{alert.region_name || `Region ${alert.region_id}`}</span>
                            <Badge tone={SEVERITY_TONE[alert.severity] || 'slate'}>{alert.severity}</Badge>
                            <Badge tone={STATUS_TONE[alert.status] || 'slate'}>{alert.status}</Badge>
                            <span className="text-sm text-slate-400">{ALERT_LABELS[alert.alert_type] || alert.alert_type}</span>
                          </div>

                          {/* WAI Metrics */}
                          <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                            {alert.wai_score != null && (
                              <span className="text-slate-500">
                                WAI: <strong className="font-mono text-slate-200">{alert.wai_score.toFixed(1)}</strong>
                              </span>
                            )}
                            {alert.rainfall_anomaly != null && (
                              <span className="text-slate-500">
                                Rainfall: <strong className={`font-mono ${alert.rainfall_anomaly < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                                  {alert.rainfall_anomaly > 0 ? '+' : ''}{alert.rainfall_anomaly.toFixed(1)}%
                                </strong>
                              </span>
                            )}
                            {alert.et_anomaly != null && (
                              <span className="text-slate-500">
                                ET: <strong className={`font-mono ${alert.et_anomaly > 25 ? 'text-amber-400' : 'text-slate-200'}`}>
                                  {alert.et_anomaly > 0 ? '+' : ''}{alert.et_anomaly.toFixed(1)}%
                                </strong>
                              </span>
                            )}
                            {alert.confidence != null && (
                              <span className="text-slate-500">
                                Confidence: <strong className="font-mono text-slate-200">{(alert.confidence * 100).toFixed(0)}%</strong>
                              </span>
                            )}
                          </div>

                          {alert.notes && (
                            <p className="mt-2 text-xs text-slate-500 italic">{alert.notes}</p>
                          )}

                          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px] text-slate-600">
                            <span>Week: {alert.week_start_date}</span>
                            <span>Created: {fmtDateTime(alert.created_at)}</span>
                            {alert.acknowledged_at && <span>Acked: {fmtDateTime(alert.acknowledged_at)}</span>}
                            {alert.resolved_at && <span>Resolved: {fmtDateTime(alert.resolved_at)}</span>}
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex flex-col items-end gap-3 sm:min-w-[120px]">
                          {alert.status === 'New' && (
                            <button onClick={() => handleAck(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-300 transition-colors hover:bg-sky-500/20">
                              <CheckCircle className="h-3.5 w-3.5" /> Acknowledge
                            </button>
                          )}
                          {alert.status !== 'Resolved' && (
                            <button onClick={() => handleResolve(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/20">
                              <CheckCircle className="h-3.5 w-3.5" /> Resolve
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
