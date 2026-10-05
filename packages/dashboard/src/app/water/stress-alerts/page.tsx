'use client'

import { Suspense, useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, X } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useWaterRegions } from '@/features/water/hooks'
import type { StressAlertRow } from '@/features/water/types'
import { fmtDateTime, titleCase } from '@/lib/format'

const isOpenStatus = (status: string | null | undefined) =>
  (status ?? '').toUpperCase() !== 'RESOLVED'

const SEVERITY_TONE: Record<string, 'red' | 'amber' | 'sky' | 'emerald'> = {
  Critical: 'red',
  Severe: 'amber',
  Warning: 'sky',
  Stressed: 'sky',
  Moderate: 'emerald',
}

const STATUS_TONE: Record<string, 'red' | 'sky' | 'emerald' | 'slate'> = {
  NEW: 'red',
  ACKNOWLEDGED: 'sky',
  RESOLVED: 'emerald',
}

const ALERT_LABELS: Record<string, string> = {
  WAI_CRITICAL: 'WAI Critical',
  WAI_SEVERE: 'WAI Severe',
  RAINFALL_DEFICIT: 'Rainfall Deficit',
  HIGH_ET: 'High Evapotranspiration',
}

export default function StressAlertsPage() {
  return (
    <Suspense fallback={<Spinner label="Loading stress alerts" />}>
      <StressAlertsView />
    </Suspense>
  )
}

function StressAlertsView() {
  const searchParams = useSearchParams()
  const regionId = Number(searchParams.get('region_id')) || null
  const regions = useWaterRegions()
  const regionName = regionId
    ? (regions.data ?? []).find((r) => r.id === regionId)?.name ?? `Region ${regionId}`
    : null

  const [alerts, setAlerts] = useState<StressAlertRow[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')

  const loadAlerts = useCallback(() => {
    const params: { limit: number; status?: string; severity?: string; region_id?: number } = { limit: 100 }
    if (statusFilter) params.status = statusFilter
    if (severityFilter) params.severity = severityFilter
    if (regionId) params.region_id = regionId
    waterApi.getStressAlerts(params).then(setAlerts).finally(() => setLoading(false))
  }, [statusFilter, severityFilter, regionId])

  useEffect(() => { loadAlerts() }, [loadAlerts])

  const handleAck = async (id: number) => { await waterApi.ackStressAlert(id); loadAlerts() }
  const handleResolve = async (id: number) => { await waterApi.resolveStressAlert(id); loadAlerts() }

  const activeAlerts = alerts.filter(a => isOpenStatus(a.status))
  const resolvedAlerts = alerts.filter(a => !isOpenStatus(a.status))

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Stress Alerts"
          description="Region-level WAI alerts from the prediction pipeline"
          icon={<AlertTriangle className="h-6 w-6" />}
          accent="bg-warn-soft text-warn"
          action={
            <div className="flex items-center gap-2">
              {regionId && (
                <Link
                  href="/water/stress-alerts"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-brand/25 bg-brand-soft px-3 py-2 text-sm font-medium text-brand transition-colors hover:border-brand/50"
                >
                  {regionName}
                  <X className="h-3.5 w-3.5" />
                </Link>
              )}
              <button onClick={loadAlerts} className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2 text-sm text-ink-muted transition-colors hover:border-brand/25 hover:text-brand">
                Refresh
              </button>
            </div>
          }
        />

        {loading ? (
          <Spinner label="Loading stress alerts" />
        ) : (
          <>
            {/* Filters */}
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Status</label>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2.5 text-sm text-ink-muted focus:border-brand/25 focus:outline-none">
                  <option value="">All Status</option>
                  <option value="New">New</option>
                  <option value="Acknowledged">Acknowledged</option>
                  <option value="Resolved">Resolved</option>
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-ink-subtle">Severity</label>
                <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)} className="rounded-xl border border-line-strong bg-surface-alt px-4 py-2.5 text-sm text-ink-muted focus:border-brand/25 focus:outline-none">
                  <option value="">All Severity</option>
                  <option value="Critical">Critical</option>
                  <option value="Severe">Severe</option>
                  <option value="Warning">Warning</option>
                </select>
              </div>
            </div>

            {/* Summary */}
            <div className="flex gap-4 text-sm">
              <span className="text-ink-subtle">Active: <strong className="text-ink">{activeAlerts.length}</strong></span>
              <span className="text-ink-subtle">Resolved: <strong className="text-ink-muted">{resolvedAlerts.length}</strong></span>
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
                            <span className="font-bold text-ink">{alert.region_name || `Region ${alert.region_id}`}</span>
                            <Badge tone={SEVERITY_TONE[alert.severity] || 'slate'}>{alert.severity}</Badge>
                            <Badge tone={STATUS_TONE[(alert.status || '').toUpperCase()] || 'slate'}>{titleCase(alert.status)}</Badge>
                            <span className="text-sm text-ink-muted">{ALERT_LABELS[alert.alert_type] || alert.alert_type}</span>
                          </div>

                          {/* WAI Metrics */}
                          <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                            {alert.wai_score != null && (
                              <span className="text-ink-subtle">
                                WAI: <strong className="font-mono text-ink">{alert.wai_score.toFixed(1)}</strong>
                              </span>
                            )}
                            {alert.rainfall_anomaly != null && (
                              <span className="text-ink-subtle">
                                Rainfall: <strong className={`font-mono ${alert.rainfall_anomaly < 0 ? 'text-crit' : 'text-ok'}`}>
                                  {alert.rainfall_anomaly > 0 ? '+' : ''}{alert.rainfall_anomaly.toFixed(1)}%
                                </strong>
                              </span>
                            )}
                            {alert.et_anomaly != null && (
                              <span className="text-ink-subtle">
                                ET: <strong className={`font-mono ${alert.et_anomaly > 25 ? 'text-warn' : 'text-ink'}`}>
                                  {alert.et_anomaly > 0 ? '+' : ''}{alert.et_anomaly.toFixed(1)}%
                                </strong>
                              </span>
                            )}
                            {alert.confidence != null && (
                              <span className="text-ink-subtle">
                                Confidence: <strong className="font-mono text-ink">{(alert.confidence * 100).toFixed(0)}%</strong>
                              </span>
                            )}
                          </div>

                          {alert.notes && (
                            <p className="mt-2 text-xs text-ink-subtle italic">{alert.notes}</p>
                          )}

                          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px] text-ink-subtle">
                            <span>Week: {alert.week_start_date}</span>
                            <span>Created: {fmtDateTime(alert.created_at)}</span>
                            {alert.acknowledged_at && <span>Acked: {fmtDateTime(alert.acknowledged_at)}</span>}
                            {alert.resolved_at && <span>Resolved: {fmtDateTime(alert.resolved_at)}</span>}
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex flex-col items-end gap-3 sm:min-w-[120px]">
                          {(alert.status || '').toUpperCase() === 'NEW' && (
                            <button onClick={() => handleAck(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-brand/25 bg-brand-soft px-3 py-1.5 text-xs font-medium text-brand transition-colors hover:bg-brand-soft">
                              <CheckCircle className="h-3.5 w-3.5" /> Acknowledge
                            </button>
                          )}
                          {isOpenStatus(alert.status) && (
                            <button onClick={() => handleResolve(alert.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-ok/25 bg-ok-soft px-3 py-1.5 text-xs font-medium text-ok transition-colors hover:bg-ok-soft">
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
