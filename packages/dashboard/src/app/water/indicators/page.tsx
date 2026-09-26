// packages/dashboard/src/app/water/indicators/page.tsx
// AquaVision Indicators - Real observation metrics by region.
'use client'

import { useMemo, useState, useEffect } from 'react'
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
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-medium ${pct > 0 ? 'text-warn' : 'text-brand'}`}>
      {pct > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

function SourceBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    IRSA: 'bg-brand-soft text-brand border-brand/25',
    KAGGLE: 'bg-brand-soft text-brand border-brand/25',
    'FFD/PMD': 'bg-warn-soft text-warn border-warn/25',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium border ${colors[source] || 'bg-surface-sunken text-ink-muted border-line-strong'}`}>
      {source}
    </span>
  )
}

// ─── WAI Summary Section ────────────────────────────────────────────────────

interface WAIIndicator {
  id: number
  region_id: number
  week_start_date: string
  wai_score: number | null
  severity: string | null
  rainfall_mm_30day: number | null
  rainfall_anomaly: number | null
  et_mm_8day: number | null
  et_anomaly: number | null
  surface_water_change_pct: number | null
}

const SEVERITY_COLOR: Record<string, string> = {
  Critical: 'text-crit bg-crit-soft border-crit/25',
  Severe: 'text-warn bg-warn-soft border-warn/25',
  Stressed: 'text-brand bg-brand-soft border-brand/25',
  Moderate: 'text-ok bg-ok-soft border-ok/25',
  Normal: 'text-ok bg-ok-soft border-ok/25',
}

function WAISummarySection() {
  const [indicators, setIndicators] = useState<WAIIndicator[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    waterApi.getIndicators({ limit: 50 }).then(data => setIndicators(data as any[])).finally(() => setLoading(false))
  }, [])

  if (loading) return null
  if (indicators.length === 0) return null

  const latest = indicators[0]
  const severity = latest.severity || 'Unknown'
  const colorClass = SEVERITY_COLOR[severity] || 'text-ink-muted bg-surface-sunken border-line-strong'

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-4 w-4 text-brand" />
        <h2 className="text-sm font-semibold text-ink">Water Availability Index (WAI)</h2>
        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${colorClass}`}>{severity}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
        <div>
          <div className="text-ink-subtle">WAI Score</div>
          <div className="text-lg font-bold text-ink">{latest.wai_score?.toFixed(1) ?? '—'}</div>
        </div>
        <div>
          <div className="text-ink-subtle">Rainfall (30d)</div>
          <div className="font-mono text-ink">{latest.rainfall_mm_30day?.toFixed(0) ?? '—'} mm</div>
          {latest.rainfall_anomaly != null && (
            <div className={`text-[10px] ${latest.rainfall_anomaly < 0 ? 'text-crit' : 'text-ok'}`}>
              {latest.rainfall_anomaly > 0 ? '+' : ''}{latest.rainfall_anomaly.toFixed(1)}% anomaly
            </div>
          )}
        </div>
        <div>
          <div className="text-ink-subtle">ET (8-day)</div>
          <div className="font-mono text-ink">{latest.et_mm_8day?.toFixed(0) ?? '—'} mm</div>
          {latest.et_anomaly != null && (
            <div className={`text-[10px] ${latest.et_anomaly > 25 ? 'text-warn' : 'text-ink-muted'}`}>
              {latest.et_anomaly > 0 ? '+' : ''}{latest.et_anomaly.toFixed(1)}% anomaly
            </div>
          )}
        </div>
        <div>
          <div className="text-ink-subtle">Surface Water</div>
          <div className="font-mono text-ink">{latest.surface_water_change_pct != null ? `${latest.surface_water_change_pct > 0 ? '+' : ''}${latest.surface_water_change_pct.toFixed(1)}%` : '—'}</div>
        </div>
        <div>
          <div className="text-ink-subtle">Week</div>
          <div className="text-ink-muted">{latest.week_start_date}</div>
        </div>
      </div>
    </div>
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
    <div className="min-h-screen bg-canvas text-ink">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(56,189,248,0.04),_transparent_40%),radial-gradient(ellipse_at_bottom_right,_rgba(139,92,246,0.03),_transparent_35%)]" />

      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-line bg-canvas backdrop-blur">
        <div className="mx-auto max-w-screen-2xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/water" className="p-1.5 rounded-lg hover:bg-surface-alt transition-colors">
              <ArrowLeft className="w-4 h-4 text-ink-muted" />
            </Link>
            <div>
              <h1 className="text-sm font-semibold text-ink">Indicators</h1>
              <p className="text-[11px] text-ink-subtle">Regional flow summaries from real observation data</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => refetch()} disabled={isFetching}
              className="p-1.5 rounded-lg hover:bg-surface-alt transition-colors disabled:opacity-40">
              <RefreshCw className={`w-4 h-4 text-ink-muted ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-screen-2xl px-6 py-6 space-y-6">
        {/* WAI Summary */}
        <WAISummarySection />

        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Provinces', value: national?.provinces ?? '—', color: 'sky' },
            { label: 'Assets', value: national?.totalAssets ?? '—', color: 'emerald' },
            { label: 'Total Observations', value: national?.totalObs?.toLocaleString() ?? '—', color: 'violet' },
            { label: 'Data Sources', value: 'IRSA · Kaggle · FFD', color: 'amber' },
          ].map(kpi => (
            <div key={kpi.label} className="rounded-xl border border-line bg-surface p-4">
              <div className="text-[11px] font-medium uppercase tracking-wider text-ink-subtle mb-1">{kpi.label}</div>
              <div className="text-xl font-semibold text-ink">{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* Province filter */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setSelectedProvince(null)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${!selectedProvince ? 'bg-brand-soft text-brand border border-brand/25' : 'text-ink-subtle hover:text-ink-muted border border-transparent'}`}
          >
            All Provinces
          </button>
          {regions.map(r => (
            <button
              key={r.province}
              onClick={() => setSelectedProvince(r.province)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${selectedProvince === r.province ? 'bg-brand-soft text-brand border border-brand/25' : 'text-ink-subtle hover:text-ink-muted border border-transparent'}`}
            >
              {r.province} <span className="text-ink-subtle ml-1">({r.assetCount})</span>
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="rounded-xl border border-line bg-surface p-12 text-center">
            <RefreshCw className="w-5 h-5 text-ink-subtle animate-spin mx-auto mb-2" />
            <p className="text-sm text-ink-subtle">Loading indicators...</p>
          </div>
        )}

        {/* Region cards */}
        {displayRegions.map(region => {
          const latest = latestByProvince.get(region.province)
          const weeks = Object.entries(region.weeks).sort(([a], [b]) => a.localeCompare(b))
          const prevWeek = weeks.length > 1 ? weeks[weeks.length - 2] : null
          const prevInflow = prevWeek ? (prevWeek[1].observations > 0 ? prevWeek[1].totalInflow / prevWeek[1].observations : 0) : 0

          return (
            <div key={region.province} className="rounded-xl border border-line bg-surface overflow-hidden">
              {/* Header */}
              <div className="px-5 py-4 border-b border-line flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: PROVINCE_COLORS[region.province] || '#64748b' }} />
                    <h3 className="text-sm font-semibold text-ink">{region.province}</h3>
                    <span className="text-[10px] text-ink-subtle">{region.assetCount} assets · {region.totalObs.toLocaleString()} obs</span>
                  </div>
                  <p className="text-[11px] text-ink-subtle mt-0.5">{region.assets.join(' · ')}</p>
                </div>
                {latest && (
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="text-[10px] text-ink-subtle uppercase tracking-wider">Avg Inflow</div>
                      <div className="text-sm font-semibold text-ink">{fmtNumber(latest.inflow)}</div>
                      <TrendArrow current={latest.inflow} previous={prevInflow} />
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-ink-subtle uppercase tracking-wider">Avg Outflow</div>
                      <div className="text-sm font-semibold text-ink">{fmtNumber(latest.outflow)}</div>
                    </div>
                  </div>
                )}
              </div>

              {/* Chart */}
              <div className="px-5 py-3 border-b border-line">
                <RegionChart region={region} />
              </div>

              {/* Weekly detail table */}
              <div className="overflow-x-auto max-h-[300px]">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="border-b border-line">
                      <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Week</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Obs</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Inflow</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Outflow</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Discharge</th>
                      <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Assets</th>
                      <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Sources</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...weeks].reverse().map(([wk, w], i) => {
                      const avgIn = w.observations > 0 ? w.totalInflow / w.observations : 0
                      const avgOut = w.observations > 0 ? w.totalOutflow / w.observations : 0
                      const avgDis = w.observations > 0 ? w.totalDischarge / w.observations : 0
                      return (
                        <tr key={wk} className={`border-b border-line ${i === 0 ? 'bg-brand-soft' : 'hover:bg-surface-alt'} transition-colors`}>
                          <td className="px-4 py-2 font-medium text-ink-muted">
                            {wk}
                            {i === 0 && <span className="ml-1.5 text-[9px] text-brand font-semibold">LATEST</span>}
                          </td>
                          <td className="px-4 py-2 text-right text-ink-muted">{w.observations}</td>
                          <td className="px-4 py-2 text-right font-medium text-ink">{fmtNumber(avgIn)}</td>
                          <td className="px-4 py-2 text-right text-ink-muted">{fmtNumber(avgOut)}</td>
                          <td className="px-4 py-2 text-right text-ink-muted">{fmtNumber(avgDis)}</td>
                          <td className="px-4 py-2 text-right text-ink-muted">{w.assetCount}</td>
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
