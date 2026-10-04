// packages/dashboard/src/app/water/indicators/page.tsx
// AquaVision Indicators - WAI (actual vs predicted), monitored regions, observed flows.
'use client'

import { useMemo, useState } from 'react'
import { Activity, TrendingUp, TrendingDown, RefreshCw, LineChart as LineIcon, Table2 } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Button } from '@/components/ui/button'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  Tooltip as RTooltip, CartesianGrid, Legend,
  LineChart, Line,
} from 'recharts'
import { waterApi } from '@/features/water/api'
import type { AssetWeeklySummary, WaterIndicator, WaterPrediction, Region } from '@/features/water/types'
import { fmtNumber } from '@/lib/format'

const REFRESH_MS = 60_000

const PROVINCE_COLORS: Record<string, string> = {
  KPK: '#38bdf8',
  AJK: '#a78bfa',
  Punjab: '#34d399',
  Sindh: '#fbbf24',
}

const SEVERITY_COLOR: Record<string, string> = {
  Critical: 'text-crit bg-crit-soft border-crit/25',
  Severe: 'text-warn bg-warn-soft border-warn/25',
  Stressed: 'text-brand bg-brand-soft border-brand/25',
  Moderate: 'text-ok bg-ok-soft border-ok/25',
  Normal: 'text-ok bg-ok-soft border-ok/25',
}

const SEVERITY_RANK: Record<string, number> = { Critical: 0, Severe: 1, Stressed: 2, Moderate: 3, Normal: 4 }

const ACTUAL_COLOR = '#38bdf8'
const PREDICTED_COLOR = '#fbbf24'

// Mirrors domain/water_classifier.py: classify_severity (low score == high stress).
function severityFromWai(wai: number | null): string | null {
  if (wai == null) return null
  if (wai < 25) return 'Critical'
  if (wai < 40) return 'Severe'
  if (wai < 55) return 'Stressed'
  if (wai < 70) return 'Moderate'
  return 'Normal'
}

function SeverityChip({ severity }: { severity?: string | null }) {
  if (!severity) return <span className="text-ink-subtle">—</span>
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold border ${SEVERITY_COLOR[severity] || 'text-ink-muted bg-surface-sunken border-line-strong'}`}>
      {severity}
    </span>
  )
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
    origins: Set<string>
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
          avgLevel: null, levelCount: 0, assetCount: 0, sources: new Set(), origins: new Set(),
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
      for (const o of w.data_origins || []) wk.origins.add(o)
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

// Provenance from data_origin — makes simulator rows instantly visible.
const ORIGIN_COLOR: Record<string, string> = {
  REAL: 'bg-ok-soft text-ok border-ok/25',
  REANALYSIS: 'bg-brand-soft text-brand border-brand/25',
  SYNTHETIC: 'bg-warn-soft text-warn border-warn/25',
  OFFICIAL_REPLAY: 'bg-surface-sunken text-ink-muted border-line-strong',
}

function OriginBadge({ origin }: { origin: string }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border ${ORIGIN_COLOR[origin] || 'bg-surface-sunken text-ink-muted border-line-strong'}`}>
      {origin}
    </span>
  )
}

// ─── WAI: national summary ─────────────────────────────────────────────────

function NationalWaiCard({ rows, week }: { rows: WaterIndicator[]; week: string }) {
  const scored = rows.filter(r => r.wai_score != null)
  const avg = scored.length ? scored.reduce((s, r) => s + Number(r.wai_score), 0) / scored.length : null
  const sevCounts = new Map<string, number>()
  for (const r of rows) {
    if (r.severity) sevCounts.set(r.severity, (sevCounts.get(r.severity) || 0) + 1)
  }
  const severities = Array.from(sevCounts.entries()).sort(
    (a, b) => (SEVERITY_RANK[a[0]] ?? 9) - (SEVERITY_RANK[b[0]] ?? 9),
  )
  const national = severityFromWai(avg)

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-4 w-4 text-brand" />
        <h2 className="text-sm font-semibold text-ink">Water Availability Index — national</h2>
        <SeverityChip severity={national} />
        <span className="ml-auto text-[11px] font-mono text-ink-subtle">week {week} · {rows.length} regions</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div>
          <div className="text-ink-subtle">Avg WAI</div>
          <div className="text-2xl font-bold text-ink">{avg != null ? avg.toFixed(1) : '—'}</div>
        </div>
        <div>
          <div className="text-ink-subtle mb-1">Severity spread</div>
          <div className="flex flex-wrap gap-1">
            {severities.map(([sev, n]) => (
              <span key={sev} className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${SEVERITY_COLOR[sev] || 'text-ink-muted border-line-strong'}`}>
                {n} {sev}
              </span>
            ))}
            {!severities.length && <span className="text-ink-subtle">—</span>}
          </div>
        </div>
        <div>
          <div className="text-ink-subtle">Rainfall / ET</div>
          <div className="font-mono text-ink-muted">Awaiting finalized CHIRPS/ERA5 (source lag)</div>
        </div>
        <div>
          <div className="text-ink-subtle">Surface water</div>
          <div className="font-mono text-ink-muted">Synced weekly from Sentinel-2</div>
        </div>
      </div>
    </div>
  )
}

// ─── WAI: predicted vs actual ──────────────────────────────────────────────

interface ChartPoint {
  week: string
  actual: number | null
  predicted: number | null
}

interface DetailRow {
  week: string
  predicted: number | null
  predictedSeverity: string | null
  actual: number | null
  actualSeverity: string | null
  error: number | null
  confidence: number | null
  n: number
}

function PredictedVsActualCard({
  predictions, indicators,
}: {
  predictions: WaterPrediction[]
  indicators: WaterIndicator[]
}) {
  const [selected, setSelected] = useState<string>('national')

  const targetWeeks = useMemo(
    () => Array.from(new Set(predictions.map(p => p.target_week_start_date))).sort(),
    [predictions],
  )

  const rows = useMemo(
    () => (selected === 'national' ? predictions : predictions.filter(p => String(p.region_id) === selected)),
    [predictions, selected],
  )

  // Actual WAI by (region, week); national line = average across regions.
  const actualByWeek = useMemo(() => {
    const scoped = selected === 'national'
      ? indicators
      : indicators.filter(i => String(i.region_id) === selected)
    const byWeek = new Map<string, number[]>()
    for (const i of scoped) {
      if (i.wai_score == null) continue
      const list = byWeek.get(i.week_start_date) || []
      list.push(Number(i.wai_score))
      byWeek.set(i.week_start_date, list)
    }
    const avgMap = new Map<string, number>()
    byWeek.forEach((vals, wk) => avgMap.set(wk, vals.reduce((a, b) => a + b, 0) / vals.length))
    return avgMap
  }, [indicators, selected])

  const chartData: ChartPoint[] = useMemo(() => {
    const weeks = new Set<string>(targetWeeks)
    actualByWeek.forEach((_v, wk) => weeks.add(wk))
    const sorted = Array.from(weeks).sort()
    const predByWeek = new Map<string, number[]>()
    for (const p of rows) {
      if (p.predicted_wai_score == null) continue
      const list = predByWeek.get(p.target_week_start_date) || []
      list.push(Number(p.predicted_wai_score))
      predByWeek.set(p.target_week_start_date, list)
    }
    return sorted.map(wk => {
      const act = actualByWeek.get(wk)
      const pred = predByWeek.get(wk)
      return {
        week: wk.slice(0, 7),
        actual: act != null ? Math.round(act * 10) / 10 : null,
        predicted: pred && pred.length
          ? Math.round((pred.reduce((a, b) => a + b, 0) / pred.length) * 10) / 10
          : null,
      }
    })
  }, [targetWeeks, actualByWeek, rows])

  // Detail rows: per-target-week predicted vs actual.
  const detail = useMemo(() => {
    if (selected === 'national') {
      return targetWeeks.map(wk => {
        const wkRows = rows.filter(p => p.target_week_start_date === wk)
        if (!wkRows.length) return null
        const predVals = wkRows.filter(p => p.predicted_wai_score != null).map(p => Number(p.predicted_wai_score))
        const actVals = wkRows.filter(p => p.actual_wai_score != null).map(p => Number(p.actual_wai_score))
        const avgPred = predVals.length ? predVals.reduce((a, b) => a + b, 0) / predVals.length : null
        const avgAct = actVals.length ? actVals.reduce((a, b) => a + b, 0) / actVals.length : null
        const confs = wkRows.filter(p => p.confidence != null).map(p => Number(p.confidence))
        return {
          week: wk,
          predicted: avgPred,
          predictedSeverity: severityFromWai(avgPred),
          actual: avgAct,
          actualSeverity: severityFromWai(avgAct),
          error: avgPred != null && avgAct != null ? Math.abs(avgAct - avgPred) : null,
          confidence: confs.length ? confs.reduce((a, b) => a + b, 0) / confs.length : null,
          n: wkRows.length,
        }
      }).filter(Boolean) as DetailRow[]
    }
    return rows.map(p => ({
      week: p.target_week_start_date,
      predicted: p.predicted_wai_score != null ? Number(p.predicted_wai_score) : null,
      predictedSeverity: p.predicted_severity || null,
      actual: p.actual_wai_score != null ? Number(p.actual_wai_score) : null,
      actualSeverity: p.actual_severity || null,
      error: p.absolute_error != null ? Number(p.absolute_error) : null,
      confidence: p.confidence != null ? Number(p.confidence) : null,
      n: 1,
    })).sort((a, b) => b.week.localeCompare(a.week))
  }, [rows, targetWeeks, selected])

  const modelVersions = useMemo(
    () => Array.from(new Set(rows.map(p => p.model_version))).join(', ') || '—',
    [rows],
  )

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <LineIcon className="h-4 w-4 text-warn" />
        <h2 className="text-sm font-semibold text-ink">Predicted vs actual WAI</h2>
        <span className="text-[11px] text-ink-subtle">model {modelVersions}</span>
        <select
          value={selected}
          onChange={e => setSelected(e.target.value)}
          className="ml-auto rounded-lg border border-line bg-surface px-3 py-1.5 text-xs text-ink focus:outline-none focus:border-brand"
        >
          <option value="national">National (avg)</option>
          {Array.from(new Map(predictions.map(p => [p.region_id, p.region_name || `Region ${p.region_id}`])).entries())
            .sort((a, b) => a[1].localeCompare(b[1]))
            .map(([id, name]) => (
              <option key={id} value={String(id)}>{name}</option>
            ))}
        </select>
      </div>
      <p className="text-[11px] text-ink-subtle mb-3">
        Solid = observed indicator · dashed = model prediction · gaps mean no data, never zero.
      </p>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#64748b' }} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
            <RTooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(v: any, name: any) => [`${v}`, name === 'actual' ? 'Actual' : 'Predicted']}
            />
            <Legend formatter={(v) => (v === 'actual' ? 'Actual' : 'Predicted')} wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="actual" stroke={ACTUAL_COLOR} strokeWidth={2.5} dot={{ r: 3 }} name="actual" />
            <Line type="monotone" dataKey="predicted" stroke={PREDICTED_COLOR} strokeWidth={2} strokeDasharray="7 5" dot={{ r: 3 }} name="predicted" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-x-auto mt-3">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line">
              <th className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Target week</th>
              <th className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Predicted WAI</th>
              <th className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Predicted severity</th>
              <th className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Actual WAI</th>
              <th className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Actual severity</th>
              <th className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">|Error|</th>
              <th className="px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Confidence</th>
              <th className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Status</th>
            </tr>
          </thead>
          <tbody>
            {detail.map(d => (
              <tr key={d.week} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-medium text-ink-muted">{d.week}</td>
                <td className="px-3 py-2 text-right font-medium text-warn">{d.predicted != null ? d.predicted.toFixed(1) : '—'}</td>
                <td className="px-3 py-2"><SeverityChip severity={d.predictedSeverity} /></td>
                <td className="px-3 py-2 text-right font-medium text-ink">{d.actual != null ? d.actual.toFixed(1) : '—'}</td>
                <td className="px-3 py-2"><SeverityChip severity={d.actualSeverity} /></td>
                <td className="px-3 py-2 text-right font-mono text-ink-muted">{d.error != null ? `±${d.error.toFixed(1)}` : '—'}</td>
                <td className="px-3 py-2 text-right font-mono text-ink-muted">{d.confidence != null ? `${(d.confidence * 100).toFixed(1)}%` : '—'}</td>
                <td className="px-3 py-2">
                  {d.actual != null
                    ? <span className="text-[10px] font-semibold text-ok">SCORED</span>
                    : <span className="text-[10px] font-semibold text-warn">AWAITING ACTUAL</span>}
                </td>
              </tr>
            ))}
            {!detail.length && (
              <tr><td colSpan={8} className="px-3 py-4 text-center text-ink-subtle">No predictions recorded yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── WAI: upcoming prediction ──────────────────────────────────────────────

function UpcomingCard({ predictions }: { predictions: WaterPrediction[] }) {
  const upcoming = useMemo(() => {
    const weeks = Array.from(new Set(predictions.map(p => p.target_week_start_date))).sort()
    const last = weeks[weeks.length - 1]
    if (!last) return null
    const rows = predictions.filter(p => p.target_week_start_date === last)
    const vals = rows.filter(p => p.predicted_wai_score != null).map(p => Number(p.predicted_wai_score))
    const confs = rows.filter(p => p.confidence != null).map(p => Number(p.confidence))
    const sevCounts = new Map<string, number>()
    for (const r of rows) if (r.predicted_severity) sevCounts.set(r.predicted_severity, (sevCounts.get(r.predicted_severity) || 0) + 1)
    return {
      week: last,
      model: Array.from(new Set(rows.map(r => r.model_version))).join(', '),
      n: rows.length,
      avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null,
      min: vals.length ? Math.min(...vals) : null,
      max: vals.length ? Math.max(...vals) : null,
      conf: confs.length ? confs.reduce((a, b) => a + b, 0) / confs.length : null,
      severities: Array.from(sevCounts.entries()).sort((a, b) => (SEVERITY_RANK[a[0]] ?? 9) - (SEVERITY_RANK[b[0]] ?? 9)),
    }
  }, [predictions])

  if (!upcoming) return null

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="h-4 w-4 text-warn" />
        <h2 className="text-sm font-semibold text-ink">Next predicted week</h2>
        <span className="ml-auto text-[11px] font-mono text-ink-subtle">{upcoming.week} · {upcoming.model}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div>
          <div className="text-ink-subtle">Avg predicted WAI</div>
          <div className="text-2xl font-bold text-ink">{upcoming.avg != null ? upcoming.avg.toFixed(1) : '—'}</div>
          {upcoming.min != null && (
            <div className="text-[10px] text-ink-subtle">range {upcoming.min.toFixed(1)} – {upcoming.max?.toFixed(1)}</div>
          )}
        </div>
        <div>
          <div className="text-ink-subtle mb-1">Predicted severity</div>
          <div className="flex flex-wrap gap-1">
            {upcoming.severities.map(([sev, n]) => (
              <span key={sev} className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${SEVERITY_COLOR[sev] || 'text-ink-muted border-line-strong'}`}>
                {n} {sev}
              </span>
            ))}
          </div>
        </div>
        <div>
          <div className="text-ink-subtle">Avg confidence</div>
          <div className="font-mono text-ink">{upcoming.conf != null ? `${(upcoming.conf * 100).toFixed(1)}%` : '—'}</div>
        </div>
        <div>
          <div className="text-ink-subtle">Regions covered</div>
          <div className="font-mono text-ink">{upcoming.n}</div>
        </div>
      </div>
    </div>
  )
}

// ─── All monitored regions (latest week) ───────────────────────────────────

function RegionsTableCard({ rows, week, regions }: { rows: WaterIndicator[]; week: string; regions: Region[] }) {
  const [sevFilter, setSevFilter] = useState<string>('ALL')

  const nameOf = useMemo(() => {
    const m = new Map<number, string>()
    for (const r of regions) m.set(r.id, r.name)
    return m
  }, [regions])

  const presentSeverities = useMemo(
    () => Array.from(new Set(rows.map(r => r.severity).filter(Boolean) as string[]))
      .sort((a, b) => (SEVERITY_RANK[a] ?? 9) - (SEVERITY_RANK[b] ?? 9)),
    [rows],
  )

  const sorted = useMemo(() => {
    const list = sevFilter === 'ALL' ? rows : rows.filter(r => r.severity === sevFilter)
    return [...list].sort((a, b) => {
      const ra = SEVERITY_RANK[a.severity ?? ''] ?? 9
      const rb = SEVERITY_RANK[b.severity ?? ''] ?? 9
      if (ra !== rb) return ra - rb
      return Number(a.wai_score ?? 999) - Number(b.wai_score ?? 999)
    })
  }, [rows, sevFilter])

  return (
    <div className="rounded-xl border border-line bg-surface overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center gap-2 flex-wrap">
        <Table2 className="h-4 w-4 text-brand" />
        <h2 className="text-sm font-semibold text-ink">All monitored regions</h2>
        <span className="text-[11px] font-mono text-ink-subtle">week {week} · {rows.length} regions</span>
        <div className="ml-auto flex gap-1.5 flex-wrap">
          {['ALL', ...presentSeverities].map(s => (
            <button
              key={s}
              onClick={() => setSevFilter(s)}
              className={`px-2 py-1 rounded text-[10px] font-semibold border transition-colors ${
                sevFilter === s
                  ? 'bg-brand-soft text-brand border-brand/25'
                  : 'text-ink-subtle hover:text-ink-muted border-line'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line">
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Region</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">WAI</th>
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Severity</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Rain 30d</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">ET 8d</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Surface water Δ</th>
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Data status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(r => (
              <tr key={r.region_id} className="border-b border-line last:border-0 hover:bg-surface-alt transition-colors">
                <td className="px-4 py-2 font-medium text-ink">{nameOf.get(r.region_id) || `Region ${r.region_id}`}</td>
                <td className="px-4 py-2 text-right font-semibold text-ink">{r.wai_score != null ? Number(r.wai_score).toFixed(1) : '—'}</td>
                <td className="px-4 py-2"><SeverityChip severity={r.severity} /></td>
                <td className="px-4 py-2 text-right font-mono text-ink-muted">
                  {r.rainfall_mm_30day != null ? `${Number(r.rainfall_mm_30day).toFixed(0)} mm` : <span className="text-warn">source lag</span>}
                  {r.rainfall_anomaly != null && (
                    <span className={`ml-1 text-[10px] ${Number(r.rainfall_anomaly) < 0 ? 'text-crit' : 'text-ok'}`}>
                      {Number(r.rainfall_anomaly) > 0 ? '+' : ''}{Number(r.rainfall_anomaly).toFixed(0)}%
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-right font-mono text-ink-muted">
                  {r.et_mm_8day != null ? `${Number(r.et_mm_8day).toFixed(0)} mm` : <span className="text-warn">source lag</span>}
                </td>
                <td className={`px-4 py-2 text-right font-mono ${r.surface_water_change_pct == null ? 'text-ink-subtle' : Number(r.surface_water_change_pct) >= 0 ? 'text-ok' : 'text-warn'}`}>
                  {r.surface_water_change_pct != null
                    ? `${Number(r.surface_water_change_pct) > 0 ? '+' : ''}${Number(r.surface_water_change_pct).toFixed(1)}%`
                    : '—'}
                </td>
                <td className="px-4 py-2 text-[10px] font-mono text-ink-subtle">
                  {r.data_status || '—'}
                  {r.data_quality ? ` · ${r.data_quality}` : ''}
                </td>
              </tr>
            ))}
            {!sorted.length && (
              <tr><td colSpan={7} className="px-4 py-4 text-center text-ink-subtle">No indicator rows.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────────

export default function IndicatorsPage() {
  const [selectedProvince, setSelectedProvince] = useState<string | null>(null)

  const { data: summaries, isLoading, refetch, isFetching } = useQuery<AssetWeeklySummary[]>({
    queryKey: ['weekly-summary', 24],
    queryFn: () => waterApi.getWeeklySummary(24),
    refetchInterval: REFRESH_MS,
  })

  const { data: indicators } = useQuery<WaterIndicator[]>({
    queryKey: ['indicators', 500],
    queryFn: () => waterApi.getIndicators({ limit: 500 }),
    refetchInterval: REFRESH_MS,
  })

  const { data: predictions } = useQuery<WaterPrediction[]>({
    queryKey: ['predictions', 'with-actual'],
    queryFn: () => waterApi.getPredictions({ include_actual: true }),
    refetchInterval: REFRESH_MS,
  })

  const { data: regionList } = useQuery<Region[]>({
    queryKey: ['regions'],
    queryFn: () => waterApi.getRegions(),
    staleTime: 5 * 60_000,
  })

  const regions = useMemo(() => summaries ? aggregateByRegion(summaries) : [], [summaries])
  const displayRegions = selectedProvince
    ? regions.filter(r => r.province === selectedProvince)
    : regions

  // Latest indicator week (the real, current WAI rows).
  const { latestWeek, latestRows } = useMemo(() => {
    if (!indicators?.length) return { latestWeek: '', latestRows: [] as WaterIndicator[] }
    const week = indicators.map(i => i.week_start_date).sort().slice(-1)[0]
    return { latestWeek: week, latestRows: indicators.filter(i => i.week_start_date === week) }
  }, [indicators])

  // Latest observed week across assets (freshness of the flow sections).
  const obsThrough = useMemo(() => {
    let max = ''
    for (const s of summaries || []) for (const w of s.weeks) if (w.week_start > max) max = w.week_start
    return max
  }, [summaries])

  // Newest actual observation timestamp (real ingestion date, not week bucket).
  const lastObs = useMemo(() => {
    let max = ''
    for (const s of summaries || []) {
      const ts = s.last_observed_at
      if (ts && ts > max) max = ts
    }
    return max ? max.slice(0, 10) : ''
  }, [summaries])

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
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          title="Indicators"
          description="WAI actual vs predicted, all monitored regions, and observed flows — every source labelled."
          icon={<Activity className="h-6 w-6" />}
          action={
            <Button variant="ghost" size="sm" onClick={() => refetch()} loading={isFetching}>
              {!isFetching && <RefreshCw className="h-3.5 w-3.5" />} Refresh
            </Button>
          }
        />

        {/* Freshness strip */}
        <div className="rounded-xl border border-line bg-surface px-4 py-2.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] font-mono text-ink-subtle">
          <span>WAI week <span className="text-ink">{latestWeek || '—'}</span> · <span className="text-ink">{latestRows.length}</span> regions</span>
          <span>Observed flows · week <span className="text-ink">{obsThrough || '—'}</span> · last obs <span className="text-ink">{lastObs || '—'}</span></span>
          <span>Predictions <span className="text-ink">{(predictions || []).length}</span> rows · model <span className="text-ink">{predictions?.[0]?.model_version || '—'}</span></span>
        </div>

        {/* National WAI */}
        {latestWeek && <NationalWaiCard rows={latestRows} week={latestWeek} />}

        {/* Predicted vs actual + upcoming */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          <div className="xl:col-span-2">
            {predictions && indicators && (
              <PredictedVsActualCard predictions={predictions} indicators={indicators} />
            )}
          </div>
          <div className="space-y-5">
            {predictions && <UpcomingCard predictions={predictions} />}
            <div className="rounded-xl border border-line bg-surface p-4 text-[11px] leading-relaxed text-ink-subtle">
              <span className="font-semibold text-ink-muted">How to read this:</span> predictions are produced weekly by the
              XGBoost WAI model; each target week is scored against the observed indicator once the week completes.
              Rows stay <span className="text-warn font-semibold">AWAITING ACTUAL</span> until then — no number is invented.
            </div>
          </div>
        </div>

        {/* All monitored regions */}
        {latestWeek && indicators && (
          <RegionsTableCard rows={latestRows} week={latestWeek} regions={regionList || []} />
        )}

        {/* Observed flow KPIs */}
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

        {/* Observed flows section header */}
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">Observed flows by province</h2>
          <span className="text-[11px] text-ink-subtle">IRSA · Kaggle · FFD/PMD weekly aggregates</span>
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
                      <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Origin</th>
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
                          <td className="px-4 py-2">
                            <div className="flex flex-wrap gap-1">
                              {Array.from(w.origins).map(o => <OriginBadge key={o} origin={o} />)}
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
      </div>
    </AppShell>
  )
}
