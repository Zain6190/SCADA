// packages/dashboard/src/app/water/analyst/page.tsx
'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Download, RefreshCw, TrendingUp, TrendingDown, Droplets, BarChart3, Activity, Building2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { waterApi } from '@/features/water/api'
import type { AssetWeeklySummary, WeeklyObservationRow } from '@/features/water/types'
import { fmtNumber, fmtDate } from '@/lib/format'

const WEEK_OPTIONS = [4, 8, 12, 16, 24, 52]
const REFRESH_MS = 60_000

function TrendBadge({ current, previous }: { current: number | null; previous: number | null }) {
  if (current == null || previous == null || previous === 0) return <span className="text-xs text-slate-600">—</span>
  const pct = ((current - previous) / previous) * 100
  const up = pct > 0
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up ? 'text-amber-400' : 'text-sky-400'}`}>
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

function SourceBadges({ sources }: { sources: string[] }) {
  const color: Record<string, string> = {
    IRSA: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    KAGGLE: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
    'FFD/PMD': 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    SENSOR_API: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  }
  return (
    <div className="flex flex-wrap gap-1">
      {sources.map(s => (
        <span key={s} className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${color[s] || 'bg-slate-700/50 text-slate-400 border-slate-600/50'}`}>
          {s}
        </span>
      ))}
    </div>
  )
}

function MiniSparkline({ data, color = 'sky' }: { data: (number | null)[]; color?: string }) {
  const vals = data.filter((v): v is number => v != null)
  if (vals.length < 2) return <div className="h-8 text-[10px] text-slate-600 flex items-center">Insufficient data</div>
  const max = Math.max(...vals)
  const min = Math.min(...vals)
  const range = max - min || 1
  const h = 32
  const w = 120
  const step = w / (vals.length - 1)
  const points = vals.map((v, i) => `${i * step},${h - ((v - min) / range) * (h - 4) - 2}`).join(' ')
  const colors: Record<string, string> = { sky: '#38bdf8', emerald: '#34d399', amber: '#fbbf24', violet: '#a78bfa' }
  return (
    <svg width={w} height={h} className="flex-shrink-0">
      <polyline fill="none" stroke={colors[color] || colors.sky} strokeWidth="1.5" points={points} />
    </svg>
  )
}

export default function AnalystWorkspacePage() {
  const [weeks, setWeeks] = useState(16)
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null)

  const { data: summaries, isLoading, refetch, isFetching } = useQuery<AssetWeeklySummary[]>({
    queryKey: ['weekly-summary', weeks, selectedAsset],
    queryFn: () => waterApi.getWeeklySummary(weeks, selectedAsset ?? undefined),
    refetchInterval: REFRESH_MS,
  })

  // Aggregate stats
  const stats = useMemo(() => {
    if (!summaries?.length) return null
    const totalObs = summaries.reduce((s, a) => s + a.total_observations, 0)
    const totalAssets = summaries.length
    const allWeeks = summaries.flatMap(a => a.weeks)
    const latestWeeks = allWeeks.filter(w => {
      const d = new Date(w.week_start)
      const now = new Date()
      const diff = (now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24)
      return diff <= 14
    })
    const avgInflow = latestWeeks.length
      ? latestWeeks.reduce((s, w) => s + (w.avg_inflow || 0), 0) / latestWeeks.filter(w => w.avg_inflow).length
      : null
    const sources = new Set(allWeeks.flatMap(w => w.data_sources))
    return { totalObs, totalAssets, avgInflow, sources: Array.from(sources) }
  }, [summaries])

  const handleExportCSV = () => {
    if (!summaries?.length) return
    const rows: string[] = ['Asset,River,Province,Week Start,Observations,Avg Inflow,Avg Level,Avg Discharge,Max Inflow,Min Inflow,Sources']
    for (const a of summaries) {
      for (const w of a.weeks) {
        rows.push([
          w.asset_name, w.river || '', w.province || '', w.week_start, w.observations,
          w.avg_inflow ?? '', w.avg_level_ft ?? '', w.avg_discharge ?? '',
          w.max_inflow ?? '', w.min_inflow ?? '', w.data_sources.join('+'),
        ].join(','))
      }
    }
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `analyst-observations-${new Date().toISOString().slice(0, 10)}.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      {/* Ambient gradient */}
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(56,189,248,0.04),_transparent_40%),radial-gradient(ellipse_at_bottom_right,_rgba(139,92,246,0.03),_transparent_35%)]" />

      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-slate-800/70 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto max-w-screen-2xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/water" className="p-1.5 rounded-lg hover:bg-slate-800/60 transition-colors">
              <ArrowLeft className="w-4 h-4 text-slate-400" />
            </Link>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">Analyst Workspace</h1>
              <p className="text-[11px] text-slate-500">Real observation data from IRSA, Kaggle, and FFD sources</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-1.5 rounded-lg hover:bg-slate-800/60 transition-colors disabled:opacity-40"
            >
              <RefreshCw className={`w-4 h-4 text-slate-400 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={handleExportCSV} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/50 text-xs text-slate-300 transition-colors">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-screen-2xl px-6 py-6 space-y-6">
        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Assets Tracked', value: stats?.totalAssets ?? '—', icon: Building2, color: 'sky' },
            { label: 'Total Observations', value: stats?.totalObs?.toLocaleString() ?? '—', icon: BarChart3, color: 'emerald' },
            { label: 'Avg Inflow (latest)', value: stats?.avgInflow ? fmtNumber(stats.avgInflow) : '—', icon: Droplets, color: 'violet' },
            { label: 'Data Sources', value: stats?.sources?.length ?? '—', icon: Activity, color: 'amber' },
          ].map((kpi) => (
            <div key={kpi.label} className="rounded-xl border border-slate-800/80 bg-slate-900/50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center bg-${kpi.color}-500/10`}>
                  <kpi.icon className={`w-3.5 h-3.5 text-${kpi.color}-400`} />
                </div>
                <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">{kpi.label}</span>
              </div>
              <div className="text-xl font-semibold text-slate-100">{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-slate-500">Weeks:</span>
            {WEEK_OPTIONS.map(w => (
              <button
                key={w}
                onClick={() => setWeeks(w)}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${weeks === w ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
              >
                {w}
              </button>
            ))}
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-slate-500">Asset:</span>
            <button
              onClick={() => setSelectedAsset(null)}
              className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${selectedAsset === null ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
            >
              All
            </button>
            {summaries?.map(a => (
              <button
                key={a.asset_id}
                onClick={() => setSelectedAsset(a.asset_id)}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${selectedAsset === a.asset_id ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-500 hover:text-slate-300 border border-transparent'}`}
              >
                {a.asset_name.split(' ')[0]}
              </button>
            ))}
          </div>
        </div>

        {/* Loading / Empty */}
        {isLoading && (
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/50 p-12 text-center">
            <RefreshCw className="w-5 h-5 text-slate-600 animate-spin mx-auto mb-2" />
            <p className="text-sm text-slate-500">Loading observations...</p>
          </div>
        )}

        {!isLoading && (!summaries || summaries.length === 0) && (
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/50 p-12 text-center">
            <BarChart3 className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-sm text-slate-400">No observation data available</p>
            <p className="text-xs text-slate-600 mt-1">Run IRSA/FFD ingestion or load Kaggle data</p>
          </div>
        )}

        {/* Asset cards */}
        {summaries?.map(asset => (
          <AssetCard key={asset.asset_id} asset={asset} />
        ))}
      </main>
    </div>
  )
}


function AssetCard({ asset }: { asset: AssetWeeklySummary }) {
  const latest = asset.weeks[asset.weeks.length - 1]
  const previous = asset.weeks.length > 1 ? asset.weeks[asset.weeks.length - 2] : null
  const inflowTrend = latest?.avg_inflow != null && previous?.avg_inflow != null
    ? latest.avg_inflow - previous.avg_inflow : null

  // Sparkline data
  const inflowSeries = asset.weeks.map(w => w.avg_inflow)
  const levelSeries = asset.weeks.map(w => w.avg_level_ft)

  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-900/50 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-800/60 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">{asset.asset_name}</h3>
          <p className="text-[11px] text-slate-500">{asset.river} · {asset.province} · {asset.total_observations.toLocaleString()} obs · {asset.date_range}</p>
        </div>
        <div className="flex items-center gap-3">
          {latest?.avg_inflow != null && (
            <div className="text-right">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Latest Inflow</div>
              <div className="text-sm font-semibold text-slate-200">{fmtNumber(latest.avg_inflow)} <span className="text-[10px] text-slate-500">cusecs</span></div>
              {inflowTrend != null && (
                <div className={`text-[11px] font-medium ${inflowTrend > 0 ? 'text-amber-400' : 'text-sky-400'}`}>
                  {inflowTrend > 0 ? '▲' : '▼'} {Math.abs(inflowTrend).toFixed(0)} cusecs/wk
                </div>
              )}
            </div>
          )}
          <MiniSparkline data={inflowSeries} color="sky" />
        </div>
      </div>

      {/* Weekly table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800/50">
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-slate-500">Week</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Obs</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Inflow</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Min/Max</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Level</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Outflow</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-slate-500">Avg Discharge</th>
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-slate-500">Sources</th>
            </tr>
          </thead>
          <tbody>
            {[...asset.weeks].reverse().map((w, i) => (
              <tr key={w.week_start} className={`border-b border-slate-800/30 ${i === 0 ? 'bg-sky-500/5' : 'hover:bg-slate-800/30'} transition-colors`}>
                <td className="px-4 py-2 font-medium text-slate-300">
                  {w.week_start}
                  {i === 0 && <span className="ml-1.5 text-[9px] text-sky-400 font-semibold">LATEST</span>}
                </td>
                <td className="px-4 py-2 text-right text-slate-400">{w.observations}</td>
                <td className="px-4 py-2 text-right font-medium text-slate-200">{w.avg_inflow != null ? fmtNumber(w.avg_inflow) : '—'}</td>
                <td className="px-4 py-2 text-right text-slate-500">
                  {w.min_inflow != null && w.max_inflow != null ? `${fmtNumber(w.min_inflow)} – ${fmtNumber(w.max_inflow)}` : '—'}
                </td>
                <td className="px-4 py-2 text-right text-slate-300">{w.avg_level_ft != null ? `${w.avg_level_ft.toFixed(1)} ft` : '—'}</td>
                <td className="px-4 py-2 text-right text-slate-300">{w.avg_outflow != null ? fmtNumber(w.avg_outflow) : '—'}</td>
                <td className="px-4 py-2 text-right text-slate-300">{w.avg_discharge != null ? fmtNumber(w.avg_discharge) : '—'}</td>
                <td className="px-4 py-2"><SourceBadges sources={w.data_sources} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
