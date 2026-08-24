// packages/dashboard/src/app/water/indicators/page.tsx
// AquaVision Indicators - Real observation metrics by region.
'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Activity, TrendingUp, TrendingDown, Droplets, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  Tooltip as RTooltip, CartesianGrid, Legend, BarChart, Bar,
} from 'recharts'
import { waterApi } from '@/features/water/api'
import type { AssetWeeklySummary } from '@/features/water/types'
import { fmtNumber } from '@/lib/format'

const REFRESH_MS = 60_000

const PROVINCE_COLORS: Record<string, string> = {
  KPK: '#38bdf8',
  AJK: '#a78bfa',
  Punjab: '#34d399',
  Sindh: '#fbbf24',
}

interface RegionAggregate {
  province: string
  weeks: Record<string, {
    observations: number
    totalInflow: number
    totalOutflow: number
    totalDischarge: number
    avgLevel: number | null
    levelCount: number
    assetCount: number
    sources: Set<string>
  }>
  totalObs: number
  assetCount: number
  assets: string[]
}

function aggregateByRegion(summaries: AssetWeeklySummary[]): RegionAggregate[] {
  const byProvince = new Map<string, RegionAggregate>()

  for (const asset of summaries) {
    const prov = asset.province || 'Unknown'
    if (!byProvince.has(prov)) {
      byProvince.set(prov, { province: prov, weeks: {}, totalObs: 0, assetCount: 0, assets: [] })
    }
    const reg = byProvince.get(prov)!
    reg.totalObs += asset.total_observations
    reg.assetCount += 1
    reg.assets.push(asset.asset_name)

    for (const w of asset.weeks) {
      if (!reg.weeks[w.week_start]) {
        reg.weeks[w.week_start] = {
          observations: 0, totalInflow: 0, totalOutflow: 0, totalDischarge: 0,
          avgLevel: null, levelCount: 0, assetCount: 0, sources: new Set(),
        }
      }
      const wk = reg.weeks[w.week_start]
      wk.observations += w.observations
      wk.totalInflow += (w.avg_inflow || 0) * w.observations
      wk.totalOutflow += (w.avg_outflow || 0) * w.observations
      wk.totalDischarge += (w.avg_discharge || 0) * w.observations
      if (w.avg_level_ft) { wk.avgLevel = (wk.avgLevel || 0) + w.avg_level_ft; wk.levelCount += 1 }
      wk.assetCount += 1
      for (const s of w.data_sources) wk.sources.add(s)
    }
  }

  return Array.from(byProvince.values()).sort((a, b) => b.totalObs - a.totalObs)
}

function RegionChart({ region }: { region: RegionAggregate }) {
  const data = Object.entries(region.weeks)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-16)
    .map(([wk, w]) => ({
      week: wk,
      inflow: w.observations > 0 ? Math.round(w.totalInflow / w.observations) : 0,
      outflow: w.observations > 0 ? Math.round(w.totalOutflow / w.observations) : 0,
      discharge: w.observations > 0 ? Math.round(w.totalDischarge / w.observations) : 0,
    }))

  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`inflow-${region.province}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
            </linearGradient>
            <linearGradient id={`outflow-${region.province}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="week" tick={{ fontSize: 9, fill: '#64748b' }} />
          <YAxis tick={{ fontSize: 9, fill: '#64748b' }} />
          <RTooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(v: any) => fmtNumber(v)}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Area type="monotone" dataKey="inflow" stroke="#38bdf8" strokeWidth={1.5} fill={`url(#inflow-${region.province})`} name="Avg Inflow" />
          <Area type="monotone" dataKey="outflow" stroke="#34d399" strokeWidth={1.5} fill={`url(#outflow-${region.province})`} name="Avg Outflow" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function TrendArrow({ current, previous }: { current: number; previous: number }) {
  if (!previous) return null
  const pct = ((current - previous) / previous) * 100
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium ${pct > 0 ? 'text-amber-400' : 'text-sky-400'}`}>
      {pct > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

function SourceBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    IRSA: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    KAGGLE: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
    'FFD/PMD': 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium border ${colors[source] || 'bg-slate-700/50 text-slate-400 border-slate-600/50'}`}>
      {source}
    </span>
  )
}

export default function IndicatorsPage() {
  const [selectedProvince, setSelectedProvince] = useState<string | null>(null)

  const { data: summaries, isLoading, refetch, isFetching } = useQuery<AssetWeeklySummary[]>({
    queryKey: ['weekly-summary', 24],
    queryFn: () => waterApi.getWeeklySummary(24),
    refetchInterval: REFRESH_MS,
  })

  const regions = useMemo(() => summaries ? aggregateByRegion(summaries) : [], [summaries])
  const displayRegions = selectedProvince
    ? regions.filter(r => r.province === selectedProvince)
    : regions

  // National totals
  const national = useMemo(() => {
    if (!regions.length) return null
    const totalObs = regions.reduce((s, r) => s + r.totalObs, 0)
    const totalAssets = regions.reduce((s, r) => s + r.assetCount, 0)
    const provinces = regions.length
    return { totalObs, totalAssets, provinces }
  }, [regions])

  // Latest week per province for trend comparison
  const latestByProvince = useMemo(() => {
    const map = new Map<string, { inflow: number; outflow: number; week: string }>()
    for (const reg of regions) {
      const weeks = Object.entries(reg.weeks).sort(([a], [b]) => b.localeCompare(a))
      if (weeks.length > 0) {
        const [wk, w] = weeks[0]
        const avgIn = w.observations > 0 ? w.totalInflow / w.observations : 0
        const avgOut = w.observations > 0 ? w.totalOutflow / w.observations : 0
        map.set(reg.province, { inflow: avgIn, outflow: avgOut, week: wk })
      }
    }
    return map
  }, [regions])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(56,189,248,0.04),_transparent_40%),radial-gradient(ellipse_at_bottom_right,_rgba(139,92,246,0.03),_transparent_35%)]" />

      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-slate-800/70 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto max-w-screen-2xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/water" className="p-1.5 rounded-lg hover:bg-slate-800/60 transition-colors">
              <ArrowLeft className="w-4 h-4 text-slate-400" />
            </Link>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">Indicators</h1>
              <p className="text-[11px] text-slate-500">Regional flow summaries from real observation data</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => refetch()} disabled={isFetching}
              className="p-1.5 rounded-lg hover:bg-slate-800/60 transition-colors disabled:opacity-40">
              <RefreshCw className={`w-4 h-4 text-slate-400 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-screen-2xl px-6 py-6 space-y-6">
        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Provinces', value: national?.provinces ?? '—', color: 'sky' },
            { label: 'Assets', value: national?.totalAssets ?? '—', color: 'emerald' },
            { label: 'Total Observations', value: national?.totalObs?.toLocaleString() ?? '—', color: 'violet' },
            { label: 'Data Sources', value: 'IRSA · Kaggle · FFD', color: 'amber' },
          ].map(kpi => (
            <div key={kpi.label} className="rounded-xl border border-slate-800/80 bg-slate-900/50 p-4">
              <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500 mb-1">{kpi.label}</div>
              <div className="text-xl font-semibold text-slate-100">{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* Province filter */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setSelectedProvince(null)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${!selectedProvince ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
          >
            All Provinces
          </button>
          {regions.map(r => (
            <button
              key={r.province}
              onClick={() => setSelectedProvince(r.province)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${selectedProvince === r.province ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
            >
              {r.province} <span className="text-slate-600 ml-1">({r.assetCount})</span>
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/50 p-12 text-center">
            <RefreshCw className="w-5 h-5 text-slate-600 animate-spin mx-auto mb-2" />
            <p className="text-sm text-slate-500">Loading indicators...</p>
          </div>
        )}

        {/* Region cards */}
        {displayRegions.map(region => {
          const latest = latestByProvince.get(region.province)
          const weeks = Object.entries(region.weeks).sort(([a], [b]) => a.localeCompare(b))
          const prevWeek = weeks.length > 1 ? weeks[weeks.length - 2] : null
          const prevInflow = prevWeek ? (prevWeek[1].observations > 0 ? prevWeek[1].totalInflow / prevWeek[1].observations : 0) : 0

          return (
            <div key={region.province} className="rounded-xl border border-slate-800/80 bg-slate-900/50 overflow-hidden">
              {/* Header */}
              <div className="px-5 py-4 border-b border-slate-800/60 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: PROVINCE_COLORS[region.province] || '#64748b' }} />
                    <h3 className="text-sm font-semibold text-slate-100">{region.province}</h3>
                    <span className="text-[10px] text-slate-500">{region.assetCount} assets · {region.totalObs.toLocaleString()} obs</span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">{region.assets.join(' · ')}</p>
                </div>
                {latest && (
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="text-[10px] text-slate-500 uppercase tracking-wider">Avg Inflow</div>
                      <div className="text-sm font-semibold text-slate-200">{fmtNumber(latest.inflow)}</div>
                      <TrendArrow current={latest.inflow} previous={prevInflow} />
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-slate-500 uppercase tracking-wider">Avg Outflow</div>
                      <div className="text-sm font-semibold text-slate-200">{fmtNumber(latest.outflow)}</div>
                    </div>
                  </div>
                )}
              </div>

              {/* Chart */}
              <div className="px-5 py-3 border-b border-slate-800/40">
                <RegionChart region={region} />
              </div>

              {/* Weekly detail table */}
              <div className="overflow-x-auto max-h-[300px]">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-900/95">
                    <tr className="border-b border-slate-800/50">
                      <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-slate-500">Week</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Obs</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Inflow</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Outflow</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Discharge</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Assets</th>
                      <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-slate-500">Sources</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...weeks].reverse().map(([wk, w], i) => {
                      const avgIn = w.observations > 0 ? w.totalInflow / w.observations : 0
                      const avgOut = w.observations > 0 ? w.totalOutflow / w.observations : 0
                      const avgDis = w.observations > 0 ? w.totalDischarge / w.observations : 0
                      return (
                        <tr key={wk} className={`border-b border-slate-800/30 ${i === 0 ? 'bg-sky-500/5' : 'hover:bg-slate-800/30'} transition-colors`}>
                          <td className="px-4 py-2 font-medium text-slate-300">
                            {wk}
                            {i === 0 && <span className="ml-1.5 text-[9px] text-sky-400 font-semibold">LATEST</span>}
                          </td>
                          <td className="px-4 py-2 text-right text-slate-400">{w.observations}</td>
                          <td className="px-4 py-2 text-right font-medium text-slate-200">{fmtNumber(avgIn)}</td>
                          <td className="px-4 py-2 text-right text-slate-300">{fmtNumber(avgOut)}</td>
                          <td className="px-4 py-2 text-right text-slate-300">{fmtNumber(avgDis)}</td>
                          <td className="px-4 py-2 text-right text-slate-400">{w.assetCount}</td>
                          <td className="px-4 py-2">
                            <div className="flex flex-wrap gap-1">
                              {Array.from(w.sources).map(s => <SourceBadge key={s} source={s} />)}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )
        })}
      </main>
    </div>
  )
}
