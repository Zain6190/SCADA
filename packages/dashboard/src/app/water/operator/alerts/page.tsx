'use client'

import { useEffect, useState } from 'react'
import { waterApi } from '@/features/water/api'
import type { OperationalAlert } from '@/features/water/types'

const SEVERITY_STYLES: Record<string, { bg: string; border: string; text: string; dot: string; badge: string }> = {
  CRITICAL: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-900', dot: 'bg-red-500', badge: 'bg-red-100 text-red-700 border-red-200' },
  WARNING: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-900', dot: 'bg-amber-500', badge: 'bg-amber-100 text-amber-700 border-amber-200' },
  ADVISORY: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-900', dot: 'bg-yellow-500', badge: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  WATCH: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-900', dot: 'bg-blue-500', badge: 'bg-blue-100 text-blue-700 border-blue-200' },
  NORMAL: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-900', dot: 'bg-emerald-500', badge: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
}

const STATUS_STYLES: Record<string, string> = {
  NEW: 'bg-red-100 text-red-700 border-red-200',
  ACKNOWLEDGED: 'bg-blue-100 text-blue-700 border-blue-200',
  INVESTIGATING: 'bg-amber-100 text-amber-700 border-amber-200',
  ESCALATED: 'bg-purple-100 text-purple-700 border-purple-200',
  RESOLVED: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  FALSE_OR_INVALID_DATA: 'bg-slate-100 text-slate-700 border-slate-200',
}

function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US')
}

export default function OperatorAlertsPage() {
  const [alerts, setAlerts] = useState<OperationalAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [severityFilter, setSeverityFilter] = useState<string>('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const loadAlerts = () => {
    const params: any = { limit: 100 }
    if (statusFilter) params.status = statusFilter
    if (severityFilter) params.severity = severityFilter
    waterApi.getOperationalAlerts(params).then(setAlerts).finally(() => setLoading(false))
  }

  useEffect(() => { loadAlerts() }, [statusFilter, severityFilter])

  const handleAck = async (id: number) => {
    await waterApi.ackOperationalAlert(id, 'Operator')
    loadAlerts()
  }

  const handleInvestigate = async (id: number) => {
    await waterApi.investigateOperationalAlert(id, 'Operator')
    loadAlerts()
  }

  const handleEscalate = async (id: number) => {
    await waterApi.escalateOperationalAlert(id, 'Operator')
    loadAlerts()
  }

  const handleResolve = async (id: number) => {
    await waterApi.resolveOperationalAlert(id, 'Operator')
    loadAlerts()
  }

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-slate-600">
          <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Loading alerts...
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Operational Alerts</h1>
          <p className="text-sm text-slate-500 mt-1">Active alerts from threshold engine — Full workflow: Ack → Investigate → Escalate → Resolve</p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Status</label>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-700 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Severity</label>
            <select
              value={severityFilter}
              onChange={e => setSeverityFilter(e.target.value)}
              className="border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-700 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">All Severity</option>
              <option value="CRITICAL">Critical</option>
              <option value="WARNING">Warning</option>
              <option value="WATCH">Watch</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={loadAlerts}
              className="px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 shadow-sm transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Alert Count */}
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <span className="font-semibold">{alerts.length}</span> alert{alerts.length !== 1 ? 's' : ''} found
        </div>

        {/* Alert List */}
        {alerts.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-sm">
            <svg className="w-12 h-12 text-slate-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-slate-500 font-medium">No alerts found</p>
            <p className="text-sm text-slate-400 mt-1">All systems operating normally</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map(alert => {
              const style = SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.NORMAL
              const isExpanded = expandedId === alert.id
              return (
                <div key={alert.id} className={`bg-white rounded-2xl border ${style.border} shadow-sm overflow-hidden`}>
                  {/* Severity bar */}
                  <div className={`h-1 ${style.dot}`}></div>

                  <div className="p-4 sm:p-5">
                    <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                      {/* Left: Alert info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <span className="font-bold text-slate-900">{alert.asset_name || `Asset ${alert.asset_id}`}</span>
                          <span className="text-slate-400">·</span>
                          <span className="text-sm font-medium text-slate-600">{alert.alert_type.replace(/_/g, ' ')}</span>
                          {alert.alert_source && (
                            <span className="text-xs px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">{alert.alert_source}</span>
                          )}
                          {alert.episode_id && (
                            <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">EP-{alert.episode_id}</span>
                          )}
                        </div>

                        <p className="text-sm text-slate-700 mb-3">{alert.message}</p>

                        {/* Readings */}
                        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                          {alert.reading_level_ft != null && (
                            <span className="text-slate-600">
                              Level: <strong className="text-slate-900 font-mono">{alert.reading_level_ft.toFixed(2)} ft</strong>
                            </span>
                          )}
                          {alert.reading_inflow_cusecs != null && (
                            <span className="text-slate-600">
                              Inflow: <strong className="text-slate-900 font-mono">{formatNumber(alert.reading_inflow_cusecs)}</strong>
                            </span>
                          )}
                          {alert.reading_outflow_cusecs != null && (
                            <span className="text-slate-600">
                              Outflow: <strong className="text-slate-900 font-mono">{formatNumber(alert.reading_outflow_cusecs)}</strong>
                            </span>
                          )}
                          {alert.rate_of_change_ft_6h != null && (
                            <span className="text-slate-600">
                              Rate: <strong className="text-slate-900 font-mono">+{alert.rate_of_change_ft_6h.toFixed(2)} ft/6h</strong>
                            </span>
                          )}
                        </div>

                        {/* Downstream Impact */}
                        {alert.downstream_population_exposed != null && alert.downstream_population_exposed > 0 && (
                          <div className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded-lg">
                            <p className="text-xs font-semibold text-amber-800 mb-1">Downstream Impact</p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-amber-700">
                              <span>Population: <strong>{formatNumber(alert.downstream_population_exposed)}</strong></span>
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
                          <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded-lg">
                            <p className="text-xs font-semibold text-red-800 mb-1">Flood Classification</p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-red-700">
                              <span>Probability: <strong>{(alert.flood_probability * 100).toFixed(1)}%</strong></span>
                              {alert.flood_severity && <span>Severity: <strong>{alert.flood_severity}</strong></span>}
                              {alert.flood_recommendation && <span>Rec: <strong>{alert.flood_recommendation}</strong></span>}
                            </div>
                          </div>
                        )}

                        {/* Timestamps */}
                        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-slate-400">
                          <span>Created: {new Date(alert.created_at).toLocaleString()}</span>
                          {alert.acknowledged_at && <span>Acked: {new Date(alert.acknowledged_at).toLocaleString()}</span>}
                          {alert.resolved_at && <span>Resolved: {new Date(alert.resolved_at).toLocaleString()}</span>}
                        </div>
                      </div>

                      {/* Right: Status + Actions */}
                      <div className="flex flex-col items-end gap-3 sm:min-w-[140px]">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${STATUS_STYLES[alert.status] || 'bg-slate-100 text-slate-700 border-slate-200'}`}>
                          {alert.status.replace(/_/g, ' ')}
                        </span>

                        <div className="flex flex-wrap gap-2 justify-end">
                          {alert.status === 'NEW' && (
                            <button
                              onClick={() => handleAck(alert.id)}
                              className="px-3 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 shadow-sm transition-colors"
                            >
                              Acknowledge
                            </button>
                          )}
                          {alert.status === 'ACKNOWLEDGED' && (
                            <button
                              onClick={() => handleInvestigate(alert.id)}
                              className="px-3 py-1.5 bg-amber-600 text-white text-xs font-semibold rounded-lg hover:bg-amber-700 shadow-sm transition-colors"
                            >
                              Investigate
                            </button>
                          )}
                          {alert.status === 'INVESTIGATING' && (
                            <button
                              onClick={() => handleEscalate(alert.id)}
                              className="px-3 py-1.5 bg-purple-600 text-white text-xs font-semibold rounded-lg hover:bg-purple-700 shadow-sm transition-colors"
                            >
                              Escalate
                            </button>
                          )}
                          {(alert.status === 'NEW' || alert.status === 'ACKNOWLEDGED' || alert.status === 'INVESTIGATING' || alert.status === 'ESCALATED') && (
                            <button
                              onClick={() => handleResolve(alert.id)}
                              className="px-3 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 shadow-sm transition-colors"
                            >
                              Resolve
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
