'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { waterApi } from '@/features/water/api'
import type { OperationalAsset, OperationalObservation, OperationalAlert, DownstreamImpact } from '@/features/water/types'

const SEVERITY_STYLES: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  CRITICAL: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-900', dot: 'bg-red-500' },
  WARNING: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-900', dot: 'bg-amber-500' },
  ADVISORY: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-900', dot: 'bg-yellow-500' },
  WATCH: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-900', dot: 'bg-blue-500' },
  NORMAL: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-900', dot: 'bg-emerald-500' },
}

function formatNumber(n: number | null | undefined, decimals = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { maximumFractionDigits: decimals })
}

function LevelGauge({ level, warning, danger, critical }: { level: number; warning?: number; danger?: number; critical?: number }) {
  const max = critical ? critical * 1.05 : (danger ? danger * 1.1 : (warning ? warning * 1.2 : level * 1.3))
  const pct = Math.min((level / max) * 100, 100)

  let color = 'bg-emerald-500'
  let barBg = 'bg-emerald-100'
  if (critical && level >= critical) { color = 'bg-red-600'; barBg = 'bg-red-100' }
  else if (danger && level >= danger) { color = 'bg-red-500'; barBg = 'bg-red-100' }
  else if (warning && level >= warning) { color = 'bg-amber-500'; barBg = 'bg-amber-100' }

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-baseline">
        <span className="text-sm font-semibold text-slate-700">Reservoir Level</span>
        <span className="font-mono text-2xl font-bold text-slate-900">{level.toFixed(2)} <span className="text-sm font-normal text-slate-500">ft</span></span>
      </div>
      <div className={`relative h-8 ${barBg} rounded-xl overflow-hidden`}>
        <div className={`absolute left-0 top-0 h-full ${color} rounded-xl transition-all duration-500`} style={{ width: `${pct}%` }} />
        {warning && (
          <div className="absolute top-0 h-full border-l-2 border-dashed border-amber-500/60" style={{ left: `${(warning / max) * 100}%` }}>
            <span className="absolute -top-6 -left-3 text-[10px] font-semibold text-amber-600 bg-white px-1 rounded">W:{warning}</span>
          </div>
        )}
        {danger && (
          <div className="absolute top-0 h-full border-l-2 border-dashed border-red-500/60" style={{ left: `${(danger / max) * 100}%` }}>
            <span className="absolute -top-6 -left-3 text-[10px] font-semibold text-red-600 bg-white px-1 rounded">D:{danger}</span>
          </div>
        )}
        {critical && (
          <div className="absolute top-0 h-full border-l-2 border-dashed border-red-700/60" style={{ left: `${(critical / max) * 100}%` }}>
            <span className="absolute -top-6 -left-3 text-[10px] font-semibold text-red-700 bg-white px-1 rounded">C:{critical}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function ReadingCard({ label, value, unit, color = 'slate' }: { label: string; value: number | null; unit: string; color?: string }) {
  const colors: Record<string, { value: string; label: string }> = {
    slate: { value: 'text-slate-900', label: 'text-slate-500' },
    blue: { value: 'text-blue-700', label: 'text-blue-500' },
    amber: { value: 'text-amber-700', label: 'text-amber-500' },
    emerald: { value: 'text-emerald-700', label: 'text-emerald-500' },
  }
  const c = colors[color] || colors.slate

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-5 shadow-sm">
      <div className={`text-sm font-medium ${c.label}`}>{label}</div>
      <div className={`text-2xl sm:text-3xl font-mono font-bold ${c.value} mt-1`}>{formatNumber(value)}</div>
      <div className="text-xs text-slate-400 mt-0.5">{unit}</div>
    </div>
  )
}

export function AssetDetailClient() {
  const params = useParams()
  const assetId = Number(params.id)

  const [asset, setAsset] = useState<OperationalAsset | null>(null)
  const [observations, setObservations] = useState<OperationalObservation[]>([])
  const [alerts, setAlerts] = useState<OperationalAlert[]>([])
  const [impact, setImpact] = useState<DownstreamImpact | null>(null)
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!assetId) return
    Promise.all([
      waterApi.getOperationalAsset(assetId),
      waterApi.getOperationalObservations(assetId, days),
      waterApi.getOperationalAlerts({ asset_id: assetId, limit: 20 }),
      waterApi.getDownstreamImpact(assetId),
    ])
      .then(([a, o, al, imp]) => { setAsset(a); setObservations(o); setAlerts(al); setImpact(imp) })
      .finally(() => setLoading(false))
  }, [assetId, days])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-slate-600">
          <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Loading...
        </div>
      </div>
    )
  }

  if (!asset) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center shadow-sm">
        <p className="text-slate-500 font-medium">Asset not found</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <Link href="/water/operator/assets" className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-800 mb-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Back to Assets
            </Link>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">{asset.canonical_name}</h1>
            <p className="text-sm text-slate-500 mt-1">{asset.asset_type.replace('_', ' ')} · {asset.river || '—'} · {asset.province || '—'}</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 px-4 py-2.5 shadow-sm">
            <div className="text-xs font-medium text-slate-500">Last updated</div>
            <div className="text-sm font-semibold text-slate-900">{asset.last_observed_at ? new Date(asset.last_observed_at).toLocaleString() : '—'}</div>
          </div>
        </div>

        {/* Current Readings */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          <ReadingCard label="Water Level" value={asset.current_level_ft} unit="ft" color="blue" />
          <ReadingCard label="Inflow" value={asset.current_inflow} unit="cusecs" color="emerald" />
          <ReadingCard label="Outflow" value={asset.current_outflow} unit="cusecs" color="amber" />
          <ReadingCard label="Discharge" value={asset.current_discharge} unit="cusecs" />
        </div>

        {/* Level Gauge */}
        {asset.current_level_ft && (
          <div className="bg-white rounded-2xl border border-slate-200 p-5 sm:p-6 shadow-sm">
            <LevelGauge
              level={asset.current_level_ft}
              warning={asset.warning_level_ft ?? undefined}
              danger={asset.critical_level_ft ? (asset.critical_level_ft - 3) : undefined}
              critical={asset.critical_level_ft ?? undefined}
            />
          </div>
        )}

        {/* Active Alerts */}
        {alerts.length > 0 && (
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <h2 className="font-bold text-slate-900 mb-4">Active Alerts ({alerts.length})</h2>
            <div className="space-y-3">
              {alerts.map(alert => {
                const style = SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.NORMAL
                return (
                  <div key={alert.id} className={`${style.bg} rounded-xl border ${style.border} p-4`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <span className={`w-2 h-2 rounded-full ${style.dot}`}></span>
                          <span className="font-semibold text-slate-900">{alert.alert_type.replace(/_/g, ' ')}</span>
                        </div>
                        <p className="text-sm text-slate-700">{alert.message}</p>
                      </div>
                      <span className="text-xs font-medium text-slate-500 whitespace-nowrap">{alert.status}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Downstream Impact */}
        {impact && impact.chain.length > 0 && (
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
              <div>
                <h2 className="font-bold text-slate-900">Downstream Impact</h2>
                <p className="text-sm text-slate-500 mt-0.5">
                  {impact.river_name} River · {impact.total_distance_km} km total · ~{impact.total_travel_time_hours}h travel
                </p>
              </div>
              {impact.source_release_cusecs && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-2.5">
                  <div className="text-xs font-medium text-blue-600">Current Release</div>
                  <div className="font-mono text-lg font-bold text-blue-700">{formatNumber(impact.source_release_cusecs)} <span className="text-xs font-normal">cusecs</span></div>
                </div>
              )}
            </div>

            <div className="space-y-3">
              {impact.chain.map((seg, idx) => {
                const segStyle = seg.downstream_alert_severity
                  ? SEVERITY_STYLES[seg.downstream_alert_severity] || SEVERITY_STYLES.NORMAL
                  : { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-900', dot: 'bg-slate-400' }

                return (
                  <div key={seg.segment_id} className={`${segStyle.bg} rounded-xl border ${segStyle.border} p-4`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <span className={`w-2 h-2 rounded-full ${segStyle.dot}`}></span>
                          <span className="font-semibold text-slate-900">{seg.downstream_asset_name}</span>
                          <span className="text-xs text-slate-500">({seg.distance_km} km)</span>
                          {seg.downstream_alert_severity && (
                            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{seg.downstream_alert_severity}</span>
                          )}
                        </div>

                        {seg.travel_time_expected_hours && (
                          <div className="text-sm text-slate-700 mb-1">
                            <span className="font-medium">Travel time:</span>{' '}
                            <span className="font-mono">{seg.travel_time_min_hours}–{seg.travel_time_max_hours}h</span>
                            <span className="text-slate-400 ml-1">(~{seg.travel_time_expected_hours}h)</span>
                          </div>
                        )}

                        {seg.arrival_window_min && seg.arrival_window_max && (
                          <div className="text-sm text-slate-700 mb-1">
                            <span className="font-medium">Arrival:</span>{' '}
                            <span className="font-mono text-xs">{new Date(seg.arrival_window_min).toLocaleString()} — {new Date(seg.arrival_window_max).toLocaleString()}</span>
                          </div>
                        )}

                        {seg.downstream_level_ft && (
                          <div className="text-sm text-slate-700">
                            <span className="font-medium">Level:</span> <span className="font-mono">{seg.downstream_level_ft} ft</span>
                            {seg.downstream_discharge && (
                              <span className="ml-3"><span className="font-medium">Discharge:</span> <span className="font-mono">{formatNumber(seg.downstream_discharge)}</span></span>
                            )}
                          </div>
                        )}

                        <div className="flex flex-wrap gap-3 mt-2 text-[11px] text-slate-400">
                          <span>Confidence: {seg.travel_time_confidence || '—'}</span>
                          <span>Source: {seg.data_source}</span>
                        </div>
                      </div>

                      {idx < impact.chain.length - 1 && (
                        <svg className="w-5 h-5 text-slate-300 flex-shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                        </svg>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
              <strong>Disclaimer:</strong> Travel times are planning estimates based on historical flood-wave observations.
              Flood depth has not been hydraulically modelled. Data: IRSA official observation + historical travel-time estimate.
            </div>
          </div>
        )}

        {/* Observation History */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <h2 className="font-bold text-slate-900">Observation History</h2>
            <div className="flex gap-2">
              {[7, 14, 30].map(d => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-lg border transition-all ${
                    days === d
                      ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                      : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {observations.length === 0 ? (
            <div className="text-center py-8 text-slate-400">No observations found</div>
          ) : (
            <div className="overflow-x-auto -mx-5 px-5">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200">
                  <tr>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-600 uppercase">Date</th>
                    <th className="px-3 py-2.5 text-right text-xs font-semibold text-slate-600 uppercase">Level</th>
                    <th className="px-3 py-2.5 text-right text-xs font-semibold text-slate-600 uppercase">Inflow</th>
                    <th className="px-3 py-2.5 text-right text-xs font-semibold text-slate-600 uppercase">Outflow</th>
                    <th className="px-3 py-2.5 text-right text-xs font-semibold text-slate-600 uppercase">Discharge</th>
                    <th className="px-3 py-2.5 text-center text-xs font-semibold text-slate-600 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {observations.map(obs => (
                    <tr key={obs.id} className="hover:bg-blue-50/50 transition-colors">
                      <td className="px-3 py-2.5 font-medium text-slate-700">{new Date(obs.observed_at).toLocaleDateString()}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-slate-900">{formatNumber(obs.water_level_ft, 2)}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-slate-900">{formatNumber(obs.inflow_cusecs)}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-slate-900">{formatNumber(obs.outflow_cusecs)}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-slate-900">{formatNumber(obs.discharge_cusecs)}</td>
                      <td className="px-3 py-2.5 text-center">
                        <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-medium">{obs.data_status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
