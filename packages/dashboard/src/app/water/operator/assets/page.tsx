'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { waterApi } from '@/features/water/api'
import type { OperationalAsset } from '@/features/water/types'

function formatNumber(n: number | null | undefined, decimals = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { maximumFractionDigits: decimals })
}

function StatusBadge({ severity }: { severity: string | null }) {
  if (!severity) return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
      <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
      Normal
    </span>
  )

  const styles: Record<string, string> = {
    CRITICAL: 'bg-red-50 text-red-700 border-red-200',
    WARNING: 'bg-amber-50 text-amber-700 border-amber-200',
    ADVISORY: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    WATCH: 'bg-blue-50 text-blue-700 border-blue-200',
    NORMAL: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  }

  const dots: Record<string, string> = {
    CRITICAL: 'bg-red-500',
    WARNING: 'bg-amber-500',
    ADVISORY: 'bg-yellow-500',
    WATCH: 'bg-blue-500',
    NORMAL: 'bg-emerald-500',
  }

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${styles[severity] || 'bg-gray-50 text-gray-700 border-gray-200'}`}>
      <span className={`w-2 h-2 rounded-full ${dots[severity] || 'bg-gray-400'}`}></span>
      {severity}
    </span>
  )
}

function DataAge({ hours }: { hours: number | null }) {
  if (hours == null) return <span className="text-xs text-slate-400">No data</span>
  if (hours > 48) return <span className="text-xs font-medium text-red-600">{hours.toFixed(0)}h ago</span>
  if (hours > 24) return <span className="text-xs font-medium text-amber-600">{hours.toFixed(0)}h ago</span>
  return <span className="text-xs font-medium text-emerald-600">{hours.toFixed(0)}h ago</span>
}

export default function OperatorAssetsPage() {
  const [assets, setAssets] = useState<OperationalAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    waterApi.getOperationalAssets().then(setAssets).finally(() => setLoading(false))
  }, [])

  const filtered = filter === 'all' ? assets : assets.filter(a => a.asset_type === filter)
  const alertCounts = {
    critical: assets.filter(a => a.highest_severity === 'CRITICAL').length,
    warning: assets.filter(a => a.highest_severity === 'WARNING').length,
    watch: assets.filter(a => a.highest_severity === 'WATCH').length,
    normal: assets.filter(a => !a.highest_severity || a.highest_severity === 'NORMAL').length,
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-slate-600">
          <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Loading assets...
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Water Assets</h1>
            <p className="text-sm text-slate-500 mt-1">Real-time IRSA monitoring data</p>
          </div>
          <Link
            href="/water/operator/alerts"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm font-semibold shadow-sm transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            View Alerts
            {alertCounts.critical > 0 && (
              <span className="inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-red-500 rounded-full">
                {alertCounts.critical}
              </span>
            )}
          </Link>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
          <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
            <div className="text-sm font-medium text-slate-500">Total Assets</div>
            <div className="text-3xl font-bold text-slate-900 mt-1">{assets.length}</div>
          </div>
          <div className="bg-white rounded-2xl border border-red-200 p-4 shadow-sm">
            <div className="text-sm font-medium text-red-600">Critical</div>
            <div className="text-3xl font-bold text-red-700 mt-1">{alertCounts.critical}</div>
          </div>
          <div className="bg-white rounded-2xl border border-amber-200 p-4 shadow-sm">
            <div className="text-sm font-medium text-amber-600">Warning</div>
            <div className="text-3xl font-bold text-amber-700 mt-1">{alertCounts.warning}</div>
          </div>
          <div className="bg-white rounded-2xl border border-emerald-200 p-4 shadow-sm">
            <div className="text-sm font-medium text-emerald-600">Normal</div>
            <div className="text-3xl font-bold text-emerald-700 mt-1">{alertCounts.watch + alertCounts.normal}</div>
          </div>
        </div>

        {/* Filter */}
        <div className="flex flex-wrap gap-2">
          {[
            { key: 'all', label: 'All Assets' },
            { key: 'reservoir', label: 'Reservoirs' },
            { key: 'barrage', label: 'Barrages' },
            { key: 'river_station', label: 'River Stations' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`px-4 py-2 text-sm font-medium rounded-xl border transition-all ${
                filter === key
                  ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50 hover:border-slate-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Asset Cards (Mobile) / Table (Desktop) */}
        <div className="block lg:hidden space-y-3">
          {filtered.map(asset => (
            <Link
              key={asset.id}
              href={`/water/operator/assets/${asset.id}`}
              className="block bg-white rounded-2xl border border-slate-200 p-4 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-slate-900">{asset.canonical_name}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">{asset.asset_type.replace('_', ' ')} · {asset.river || '—'}</p>
                </div>
                <StatusBadge severity={asset.highest_severity} />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <div className="text-xs text-slate-500">Level</div>
                  <div className="font-mono font-semibold text-slate-900">{formatNumber(asset.current_level_ft, 1)}</div>
                  <div className="text-xs text-slate-400">ft</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">Inflow</div>
                  <div className="font-mono font-semibold text-slate-900">{formatNumber(asset.current_inflow)}</div>
                  <div className="text-xs text-slate-400">cusecs</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">Outflow</div>
                  <div className="font-mono font-semibold text-slate-900">{formatNumber(asset.current_outflow || asset.current_discharge)}</div>
                  <div className="text-xs text-slate-400">cusecs</div>
                </div>
              </div>

              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
                <DataAge hours={asset.data_age_hours} />
                {asset.active_alert_count > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
                    <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    {asset.active_alert_count} alert{asset.active_alert_count > 1 ? 's' : ''}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>

        {/* Desktop Table */}
        <div className="hidden lg:block bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-3.5 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">Asset</th>
                <th className="px-6 py-3.5 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">Level (ft)</th>
                <th className="px-6 py-3.5 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">Inflow (cusecs)</th>
                <th className="px-6 py-3.5 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">Outflow (cusecs)</th>
                <th className="px-6 py-3.5 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3.5 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider">Data Age</th>
                <th className="px-6 py-3.5 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider">Alerts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map(asset => (
                <tr key={asset.id} className="hover:bg-blue-50/50 transition-colors">
                  <td className="px-6 py-4">
                    <Link href={`/water/operator/assets/${asset.id}`} className="font-semibold text-blue-600 hover:text-blue-800 hover:underline">
                      {asset.canonical_name}
                    </Link>
                    <div className="text-xs text-slate-500 mt-0.5">{asset.asset_type.replace('_', ' ')} · {asset.river || '—'}</div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className="font-mono font-semibold text-slate-900">{formatNumber(asset.current_level_ft, 2)}</span>
                    {asset.warning_level_ft && (
                      <div className="text-xs text-slate-400">W: {asset.warning_level_ft}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className="font-mono font-semibold text-slate-900">{formatNumber(asset.current_inflow)}</span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className="font-mono font-semibold text-slate-900">{formatNumber(asset.current_outflow || asset.current_discharge)}</span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <StatusBadge severity={asset.highest_severity} />
                  </td>
                  <td className="px-6 py-4 text-center">
                    <DataAge hours={asset.data_age_hours} />
                  </td>
                  <td className="px-6 py-4 text-center">
                    {asset.active_alert_count > 0 ? (
                      <span className="inline-flex items-center justify-center w-7 h-7 text-xs font-bold text-white bg-red-500 rounded-full shadow-sm">
                        {asset.active_alert_count}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
