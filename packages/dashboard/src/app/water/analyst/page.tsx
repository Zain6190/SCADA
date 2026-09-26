// packages/dashboard/src/app/water/analyst/page.tsx
'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Download, RefreshCw, TrendingUp, TrendingDown, Droplets, BarChart3, Activity, Building2, Brain, Shield, AlertTriangle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { waterApi } from '@/features/water/api'
import type { AssetWeeklySummary, ModelPerformance } from '@/features/water/types'
import { fmtNumber } from '@/lib/format'

const WEEK_OPTIONS = [4, 8, 12, 16, 24, 52]
const REFRESH_MS = 60_000

function TrendBadge({ current, previous }: { current: number | null; previous: number | null }) {
  if (current == null || previous == null || previous === 0) return <span className="text-xs text-ink-subtle">—</span>
  const pct = ((current - previous) / previous) * 100
  const up = pct > 0
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up ? 'text-warn' : 'text-brand'}`}>
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

function SourceBadges({ sources }: { sources: string[] }) {
  const color: Record<string, string> = {
    IRSA: 'bg-brand-soft text-brand border-brand/25',
    KAGGLE: 'bg-brand-soft text-brand border-brand/25',
    'FFD/PMD': 'bg-warn-soft text-warn border-warn/25',
    SENSOR_API: 'bg-ok-soft text-ok border-ok/25',
  }
  return (
    <div className="flex flex-wrap gap-1">
      {sources.map(s => (
        <span key={s} className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${color[s] || 'bg-surface-sunken text-ink-muted border-line-strong'}`}>
          {s}
        </span>
      ))}
    </div>
  )
}

function MiniSparkline({ data, color = 'sky' }: { data: (number | null)[]; color?: string }) {
  const vals = data.filter((v): v is number => v != null)
  if (vals.length < 2) return <div className="h-8 text-[10px] text-ink-subtle flex items-center">Insufficient data</div>
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

function MetricBar({ label, value, max = 1, color = 'sky' }: { label: string; value: number | null | string; max?: number; color?: string }) {
  if (value == null || value === '') return null
  const numVal = Number(value)
  if (isNaN(numVal)) return null
  const pct = Math.min(Math.abs(numVal) / max * 100, 100)
  const colors: Record<string, string> = {
    sky: 'bg-brand', emerald: 'bg-ok', amber: 'bg-warn',
    violet: 'bg-brand', red: 'bg-crit',
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-ink-subtle w-16 text-right">{label}</span>
      <div className="flex-1 h-1.5 bg-surface-alt rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${colors[color] || colors.sky}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-ink-muted w-12 text-right font-medium">
        {numVal < 1 ? numVal.toFixed(4) : numVal.toFixed(2)}
      </span>
    </div>
  )
}

function FeatureImportance({ features }: { features: Record<string, any> }) {
  const entries = Object.entries(features)
    .filter(([, v]) => v != null && v !== '')
    .slice(0, 8)
    .map(([k, v]) => [k, Number(v)] as [string, number])
  if (entries.length === 0) return <span className="text-[10px] text-ink-subtle">No features</span>
  const maxVal = Math.max(...entries.map(([, v]) => Math.abs(v))) || 1
  return (
    <div className="space-y-1">
      {entries.map(([name, val]) => (
        <div key={name} className="flex items-center gap-1.5">
          <span className="text-[9px] text-ink-subtle w-28 truncate" title={name}>{name}</span>
          <div className="flex-1 h-1 bg-surface-alt rounded-full overflow-hidden">
            <div className="h-full bg-brand rounded-full" style={{ width: `${(Math.abs(val) / maxVal) * 100}%` }} />
          </div>
          <span className="text-[9px] text-ink-muted w-10 text-right">{val.toFixed(3)}</span>
        </div>
      ))}
    </div>
  )
}

function ModelPerformanceCard({ model }: { model: ModelPerformance }) {
  const isClassifier = model.model_type === 'flood_classifier'
  const isPredictor = model.model_type === 'flood_predictor'
  const isAnomaly = model.model_type === 'anomaly_detector'

  const typeLabel = isPredictor ? 'Flood Predictor' : isClassifier ? 'Flood Classifier' : 'Anomaly Detector'
  const typeColor = isPredictor ? 'sky' : isClassifier ? 'amber' : 'violet'
  const typeIcon = isPredictor ? Droplets : isClassifier ? Shield : AlertTriangle

  return (
    <div className="rounded-xl border border-line bg-surface p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center bg-${typeColor}-500/10`}>
            {(() => { const Icon = typeIcon; return <Icon className={`w-3.5 h-3.5 text-${typeColor}-400`} /> })()}
          </div>
          <div>
            <h4 className="text-xs font-semibold text-ink">{model.asset_name}</h4>
            <p className="text-[10px] text-ink-subtle">{typeLabel} {model.horizon_days ? `(${model.horizon_days}d)` : ''}</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${
          model.model_status === 'APPROVED' ? 'bg-ok-soft text-ok border-ok/25' :
          model.model_status === 'SHADOW' ? 'bg-warn-soft text-warn border-warn/25' :
          'bg-surface-sunken text-ink-muted border-line-strong'
        }`}>
          {model.model_status}
        </span>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {isPredictor && (
          <>
            <MetricBar label="R²" value={model.r2} max={1} color="emerald" />
            <MetricBar label="MAE" value={model.mae} max={500} color="sky" />
            <MetricBar label="RMSE" value={model.rmse} max={500} color="sky" />
            <MetricBar label="MAPE" value={model.mape} max={100} color="violet" />
          </>
        )}
        {isClassifier && (
          <>
            <MetricBar label="Accuracy" value={model.accuracy} max={1} color="emerald" />
            <MetricBar label="AUC" value={model.auc} max={1} color="amber" />
            <MetricBar label="F1" value={model.f1} max={1} color="sky" />
            <MetricBar label="Precision" value={model.precision} max={1} color="violet" />
          </>
        )}
        {isAnomaly && (
          <div className="col-span-2 text-[10px] text-ink-subtle">
            Samples: {model.samples?.toLocaleString() || '—'} · Version: {model.model_version || '—'}
          </div>
        )}
      </div>

      {/* Sample counts */}
      {(model.train_samples || model.test_samples) && (
        <div className="flex items-center gap-3 text-[10px] text-ink-subtle">
          <span>Train: {model.train_samples?.toLocaleString()}</span>
          <span>Test: {model.test_samples?.toLocaleString()}</span>
        </div>
      )}

      {/* Feature importance */}
      {Object.keys(model.feature_importance).length > 0 && (
        <div>
          <div className="text-[10px] text-ink-subtle uppercase tracking-wider mb-1.5">Top Features</div>
          <FeatureImportance features={model.feature_importance} />
        </div>
      )}

      {/* Footer */}
      <div className="pt-2 border-t border-line flex items-center justify-between text-[9px] text-ink-subtle">
        <span>{model.model_file}</span>
        {model.trained_at && <span>Trained: {model.trained_at.slice(0, 10)}</span>}
      </div>
    </div>
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

  const { data: models, isLoading: modelsLoading } = useQuery<ModelPerformance[]>({
    queryKey: ['model-performance'],
    queryFn: () => waterApi.getModelPerformance(),
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

  // Model stats
  const modelStats = useMemo(() => {
    if (!models?.length) return null
    const predictors = models.filter(m => m.model_type === 'flood_predictor')
    const classifiers = models.filter(m => m.model_type === 'flood_classifier')
    const avgR2 = predictors.length ? predictors.reduce((s, m) => s + (m.r2 || 0), 0) / predictors.length : null
    const avgAUC = classifiers.length ? classifiers.reduce((s, m) => s + (m.auc || 0), 0) / classifiers.length : null
    return { totalModels: models.length, predictors: predictors.length, classifiers: classifiers.length, avgR2, avgAUC }
  }, [models])

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
    <div className="min-h-screen bg-canvas text-ink">
      {/* Ambient gradient */}
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(56,189,248,0.04),_transparent_40%),radial-gradient(ellipse_at_bottom_right,_rgba(139,92,246,0.03),_transparent_35%)]" />

      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-line bg-canvas backdrop-blur">
        <div className="mx-auto max-w-screen-2xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/water" className="p-1.5 rounded-lg hover:bg-surface-alt transition-colors">
              <ArrowLeft className="w-4 h-4 text-ink-muted" />
            </Link>
            <div>
              <h1 className="text-sm font-semibold text-ink">Analyst Workspace</h1>
              <p className="text-[11px] text-ink-subtle">Real observation data and model performance metrics</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="p-1.5 rounded-lg hover:bg-surface-alt transition-colors disabled:opacity-40"
            >
              <RefreshCw className={`w-4 h-4 text-ink-muted ${isFetching ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={handleExportCSV} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-alt hover:bg-surface-sunken border border-line-strong text-xs text-ink-muted transition-colors">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-screen-2xl px-6 py-6 space-y-6">
        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[
            { label: 'Assets Tracked', value: stats?.totalAssets ?? '—', icon: Building2, color: 'sky' },
            { label: 'Total Observations', value: stats?.totalObs?.toLocaleString() ?? '—', icon: BarChart3, color: 'emerald' },
            { label: 'Avg Inflow', value: stats?.avgInflow ? fmtNumber(stats.avgInflow) : '—', icon: Droplets, color: 'violet' },
            { label: 'Data Sources', value: stats?.sources?.length ?? '—', icon: Activity, color: 'amber' },
            { label: 'Avg R²', value: modelStats?.avgR2 != null ? modelStats.avgR2.toFixed(3) : '—', icon: Brain, color: 'emerald' },
            { label: 'Avg AUC', value: modelStats?.avgAUC != null ? modelStats.avgAUC.toFixed(3) : '—', icon: Shield, color: 'amber' },
          ].map((kpi) => (
            <div key={kpi.label} className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center bg-${kpi.color}-500/10`}>
                  <kpi.icon className={`w-3.5 h-3.5 text-${kpi.color}-400`} />
                </div>
                <span className="text-[11px] font-medium uppercase tracking-wider text-ink-subtle">{kpi.label}</span>
              </div>
              <div className="text-xl font-semibold text-ink">{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* Section: Model Performance */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Brain className="w-4 h-4 text-brand" />
            <h2 className="text-sm font-semibold text-ink">Model Performance</h2>
            {modelStats && (
              <span className="text-[11px] text-ink-subtle">({modelStats.totalModels} models · {modelStats.predictors} predictors · {modelStats.classifiers} classifiers)</span>
            )}
          </div>

          {modelsLoading ? (
            <div className="rounded-xl border border-line bg-surface p-8 text-center">
              <RefreshCw className="w-5 h-5 text-ink-subtle animate-spin mx-auto mb-2" />
              <p className="text-sm text-ink-subtle">Loading model metadata...</p>
            </div>
          ) : !models?.length ? (
            <div className="rounded-xl border border-line bg-surface p-8 text-center">
              <Brain className="w-8 h-8 text-ink-muted mx-auto mb-2" />
              <p className="text-sm text-ink-muted">No trained models found</p>
              <p className="text-xs text-ink-subtle mt-1">Run model training from the Predictions page</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {models.filter(m => m.model_type !== 'anomaly_detector').map((m, i) => (
                <ModelPerformanceCard key={`${m.asset_id}-${m.model_type}-${m.horizon_days}`} model={m} />
              ))}
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-ink-subtle">Weeks:</span>
            {WEEK_OPTIONS.map(w => (
              <button
                key={w}
                onClick={() => setWeeks(w)}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${weeks === w ? 'bg-brand-soft text-brand border border-brand/25' : 'text-ink-subtle hover:text-ink-muted border border-transparent'}`}
              >
                {w}
              </button>
            ))}
          </div>
          <div className="h-4 w-px bg-surface-alt" />
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-ink-subtle">Asset:</span>
            <button
              onClick={() => setSelectedAsset(null)}
              className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${selectedAsset === null ? 'bg-brand-soft text-brand border border-brand/25' : 'text-ink-subtle hover:text-ink-muted border border-transparent'}`}
            >
              All
            </button>
            {summaries?.map(a => (
              <button
                key={a.asset_id}
                onClick={() => setSelectedAsset(a.asset_id)}
                className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${selectedAsset === a.asset_id ? 'bg-brand-soft text-brand border border-brand/25' : 'text-ink-subtle hover:text-ink-muted border border-transparent'}`}
              >
                {a.asset_name.split(' ')[0]}
              </button>
            ))}
          </div>
        </div>

        {/* Section: Observations */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 className="w-4 h-4 text-brand" />
            <h2 className="text-sm font-semibold text-ink">Observation Data</h2>
          </div>

          {isLoading && (
            <div className="rounded-xl border border-line bg-surface p-12 text-center">
              <RefreshCw className="w-5 h-5 text-ink-subtle animate-spin mx-auto mb-2" />
              <p className="text-sm text-ink-subtle">Loading observations...</p>
            </div>
          )}

          {!isLoading && (!summaries || summaries.length === 0) && (
            <div className="rounded-xl border border-line bg-surface p-12 text-center">
              <BarChart3 className="w-8 h-8 text-ink-muted mx-auto mb-2" />
              <p className="text-sm text-ink-muted">No observation data available</p>
              <p className="text-xs text-ink-subtle mt-1">Run IRSA/FFD ingestion or load Kaggle data</p>
            </div>
          )}

          {summaries?.map(asset => (
            <AssetCard key={asset.asset_id} asset={asset} />
          ))}
        </div>
      </main>
    </div>
  )
}


function AssetCard({ asset }: { asset: AssetWeeklySummary }) {
  const latest = asset.weeks[asset.weeks.length - 1]
  const previous = asset.weeks.length > 1 ? asset.weeks[asset.weeks.length - 2] : null
  const inflowTrend = latest?.avg_inflow != null && previous?.avg_inflow != null
    ? latest.avg_inflow - previous.avg_inflow : null

  const inflowSeries = asset.weeks.map(w => w.avg_inflow)

  return (
    <div className="rounded-xl border border-line bg-surface overflow-hidden mb-3">
      <div className="px-5 py-4 border-b border-line flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-ink">{asset.asset_name}</h3>
          <p className="text-[11px] text-ink-subtle">{asset.river} · {asset.province} · {asset.total_observations.toLocaleString()} obs · {asset.date_range}</p>
        </div>
        <div className="flex items-center gap-3">
          {latest?.avg_inflow != null && (
            <div className="text-right">
              <div className="text-[10px] text-ink-subtle uppercase tracking-wider">Latest Inflow</div>
              <div className="text-sm font-semibold text-ink">{fmtNumber(latest.avg_inflow)} <span className="text-[10px] text-ink-subtle">cusecs</span></div>
              {inflowTrend != null && (
                <div className={`text-[11px] font-medium ${inflowTrend > 0 ? 'text-warn' : 'text-brand'}`}>
                  {inflowTrend > 0 ? '▲' : '▼'} {Math.abs(inflowTrend).toFixed(0)} cusecs/wk
                </div>
              )}
            </div>
          )}
          <MiniSparkline data={inflowSeries} color="sky" />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line">
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Week</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Obs</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Inflow</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Min/Max</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Level</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Outflow</th>
              <th className="px-4 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Avg Discharge</th>
              <th className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">Sources</th>
            </tr>
          </thead>
          <tbody>
            {[...asset.weeks].reverse().map((w, i) => (
              <tr key={w.week_start} className={`border-b border-line ${i === 0 ? 'bg-brand-soft' : 'hover:bg-surface-alt'} transition-colors`}>
                <td className="px-4 py-2 font-medium text-ink-muted">
                  {w.week_start}
                  {i === 0 && <span className="ml-1.5 text-[9px] text-brand font-semibold">LATEST</span>}
                </td>
                <td className="px-4 py-2 text-right text-ink-muted">{w.observations}</td>
                <td className="px-4 py-2 text-right font-medium text-ink">{w.avg_inflow != null ? fmtNumber(w.avg_inflow) : '—'}</td>
                <td className="px-4 py-2 text-right text-ink-subtle">
                  {w.min_inflow != null && w.max_inflow != null ? `${fmtNumber(w.min_inflow)} – ${fmtNumber(w.max_inflow)}` : '—'}
                </td>
                <td className="px-4 py-2 text-right text-ink-muted">{w.avg_level_ft != null ? `${w.avg_level_ft.toFixed(1)} ft` : '—'}</td>
                <td className="px-4 py-2 text-right text-ink-muted">{w.avg_outflow != null ? fmtNumber(w.avg_outflow) : '—'}</td>
                <td className="px-4 py-2 text-right text-ink-muted">{w.avg_discharge != null ? fmtNumber(w.avg_discharge) : '—'}</td>
                <td className="px-4 py-2"><SourceBadges sources={w.data_sources} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
