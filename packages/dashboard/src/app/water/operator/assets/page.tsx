'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Warehouse, Bell, AlertTriangle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { KpiCard } from '@/components/ui/kpi'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtNumber, timeAgo } from '@/lib/format'
import type { OperationalAsset } from '@/features/water/types'

type FilterKey = 'all' | 'reservoir' | 'barrage' | 'river_station'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'All Assets' },
  { key: 'reservoir', label: 'Reservoirs' },
  { key: 'barrage', label: 'Barrages' },
  { key: 'river_station', label: 'River Stations' },
]

function DataAge({ hours }: { hours: number | null }) {
  if (hours == null) return <span className="text-[11px] text-slate-600">No data</span>
  if (hours > 48) return <span className="text-[11px] font-medium text-red-400">{hours.toFixed(0)}h ago</span>
  if (hours > 24) return <span className="text-[11px] font-medium text-amber-400">{hours.toFixed(0)}h ago</span>
  return <span className="text-[11px] font-medium text-emerald-400">{hours.toFixed(0)}h ago</span>
}

export default function OperatorAssetsPage() {
  const [assets, setAssets] = useState<OperationalAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<FilterKey>('all')

  useEffect(() => {
    waterApi.getOperationalAssets().then(setAssets).finally(() => setLoading(false))
  }, [])

  const filtered = filter === 'all' ? assets : assets.filter(a => a.asset_type === filter)
  const criticalCount = assets.filter(a => a.highest_severity === 'CRITICAL').length
  const warningCount = assets.filter(a => a.highest_severity === 'WARNING').length
  const normalCount = assets.filter(a => !a.highest_severity || a.highest_severity === 'NORMAL').length

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Assets"
          description="Real-time IRSA monitoring data"
          icon={<Warehouse className="h-6 w-6" />}
          action={
            <Link
              href="/water/operator/alerts"
              className="inline-flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-300 transition-colors hover:bg-sky-500/20"
            >
              <Bell className="h-4 w-4" />
              View Alerts
              {criticalCount > 0 && (
                <span className="inline-flex items-center justify-center w-5 h-5 text-[11px] font-bold text-white bg-red-500 rounded-full">
                  {criticalCount}
                </span>
              )}
            </Link>
          }
        />

        {loading ? (
          <Spinner label="Loading assets" />
        ) : (
          <>
            {/* Summary KPIs */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
              <KpiCard label="Total Assets" value={assets.length} icon={Warehouse} />
              <KpiCard label="Critical" value={criticalCount} icon={AlertTriangle} accent="bg-red-500/10 text-red-300" />
              <KpiCard label="Warning" value={warningCount} icon={AlertTriangle} accent="bg-amber-500/10 text-amber-300" />
              <KpiCard label="Normal" value={normalCount} icon={Warehouse} accent="bg-emerald-500/10 text-emerald-300" />
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-2">
              {FILTERS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`rounded-xl border px-4 py-2 text-sm font-medium transition-all ${
                    filter === key
                      ? 'border-sky-500/30 bg-sky-500/10 text-sky-300'
                      : 'border-slate-700 bg-slate-800/40 text-slate-400 hover:border-slate-600 hover:text-slate-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {filtered.length === 0 ? (
              <EmptyState title="No assets found" message="No assets match the current filter" />
            ) : (
              <>
                {/* Mobile: Card grid */}
                <div className="block lg:hidden space-y-3">
                  {filtered.map(asset => (
                    <Link key={asset.id} href={`/water/operator/assets/${asset.id}`}>
                      <Card className="p-4 hover:border-sky-500/30 transition-colors cursor-pointer">
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h3 className="font-semibold text-slate-100">{asset.canonical_name}</h3>
                            <p className="text-[11px] text-slate-500 mt-0.5">{asset.asset_type.replace('_', ' ')} · {asset.river || '—'}</p>
                          </div>
                          <SeverityBadge severity={asset.highest_severity} />
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                          <div>
                            <div className="text-[11px] text-slate-500">Level</div>
                            <div className="font-mono font-semibold text-slate-200">{fmtNumber(asset.current_level_ft, 1)}</div>
                            <div className="text-[11px] text-slate-600">ft</div>
                          </div>
                          <div>
                            <div className="text-[11px] text-slate-500">Inflow</div>
                            <div className="font-mono font-semibold text-slate-200">{fmtNumber(asset.current_inflow, 0)}</div>
                            <div className="text-[11px] text-slate-600">cusecs</div>
                          </div>
                          <div>
                            <div className="text-[11px] text-slate-500">Outflow</div>
                            <div className="font-mono font-semibold text-slate-200">{fmtNumber(asset.current_outflow || asset.current_discharge, 0)}</div>
                            <div className="text-[11px] text-slate-600">cusecs</div>
                          </div>
                        </div>
                        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-800/70">
                          <DataAge hours={asset.data_age_hours} />
                          {asset.active_alert_count > 0 && (
                            <Badge tone="red">{asset.active_alert_count} alert{asset.active_alert_count > 1 ? 's' : ''}</Badge>
                          )}
                        </div>
                      </Card>
                    </Link>
                  ))}
                </div>

                {/* Desktop: Table */}
                <Card className="hidden lg:block overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                          <th className="px-6 py-3.5 text-left font-semibold">Asset</th>
                          <th className="px-6 py-3.5 text-right font-semibold">Level (ft)</th>
                          <th className="px-6 py-3.5 text-right font-semibold">Inflow (cusecs)</th>
                          <th className="px-6 py-3.5 text-right font-semibold">Outflow (cusecs)</th>
                          <th className="px-6 py-3.5 text-center font-semibold">Status</th>
                          <th className="px-6 py-3.5 text-center font-semibold">Data Age</th>
                          <th className="px-6 py-3.5 text-center font-semibold">Alerts</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {filtered.map(asset => (
                          <tr key={asset.id} className="hover:bg-slate-800/30 transition-colors">
                            <td className="px-6 py-4">
                              <Link href={`/water/operator/assets/${asset.id}`} className="font-semibold text-sky-400 hover:text-sky-300 hover:underline">
                                {asset.canonical_name}
                              </Link>
                              <div className="text-[11px] text-slate-500 mt-0.5">{asset.asset_type.replace('_', ' ')} · {asset.river || '—'}</div>
                            </td>
                            <td className="px-6 py-4 text-right">
                              <span className="font-mono font-semibold text-slate-200">{fmtNumber(asset.current_level_ft, 2)}</span>
                              {asset.warning_level_ft && (
                                <div className="text-[11px] text-slate-500">W: {asset.warning_level_ft}</div>
                              )}
                            </td>
                            <td className="px-6 py-4 text-right font-mono font-semibold text-slate-200">{fmtNumber(asset.current_inflow, 0)}</td>
                            <td className="px-6 py-4 text-right font-mono font-semibold text-slate-200">{fmtNumber(asset.current_outflow || asset.current_discharge, 0)}</td>
                            <td className="px-6 py-4 text-center"><SeverityBadge severity={asset.highest_severity} /></td>
                            <td className="px-6 py-4 text-center"><DataAge hours={asset.data_age_hours} /></td>
                            <td className="px-6 py-4 text-center">
                              {asset.active_alert_count > 0 ? (
                                <span className="inline-flex items-center justify-center w-7 h-7 text-[11px] font-bold text-white bg-red-500/80 rounded-full">
                                  {asset.active_alert_count}
                                </span>
                              ) : (
                                <span className="text-[11px] text-slate-600">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
