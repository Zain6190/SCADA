// packages/dashboard/src/app/water/analyst/page.tsx
'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle, BarChart3, ChevronRight, CloudRain, Download, Droplets,
  RefreshCw, TrendingDown, TrendingUp, Waves,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Button } from '@/components/ui/button'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useQuery } from '@tanstack/react-query'
import { waterApi } from '@/features/water/api'
import type {
  AssetWeeklySummary, ModelPerformance, OperationalAsset, V2LeadTimeForecast,
} from '@/features/water/types'
import { fmtNumber } from '@/lib/format'

const HORIZONS = [3, 7, 14] as const
const WEEK_OPTIONS = [4, 8, 16, 24]
const REFRESH_MS = 60_000

const CI_METHOD_LABELS: Record<string, { label: string; tone: BadgeTone }> = {
  quantile_q10_q90: { label: 'Quantile 80% CI', tone: 'ok' },
  residual_p90: { label: 'Residual ±p90', tone: 'info' },
  physics_band: { label: 'Physics band', tone: 'info' },
  r2_band: { label: 'Quality band', tone: 'warn' },
  pct_heuristic: { label: '±15% heuristic', tone: 'neutral' },
}

const SELECT_CLASS =
  'rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-brand focus:outline-none'

function stressTone(category: string): BadgeTone {
  if (category === 'Abundant') return 'ok'
  if (category === 'Moderate') return 'info'
  if (category === 'Stressed') return 'warn'
  return 'crit'
}

function floodTone(category: string): BadgeTone {
  if (category === 'No Risk') return 'ok'
  if (category === 'Moderate') return 'warn'
  return 'crit'
}

function statusTone(status: string): BadgeTone {
  if (status === 'APPROVED' || status === 'PRODUCTION') return 'ok'
  if (status === 'SHADOW') return 'warn'
  if (status === 'REJECTED') return 'crit'
  return 'neutral'
}

function labelize(key: string) {
  return key.replace(/_/g, ' ')
}

function FeatureBars({ features }: { features: Record<string, number> }) {
  const entries = Object.entries(features)
    .filter(([, value]) => value != null && Number.isFinite(value))
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 6)
  if (entries.length === 0) return null
  const maxVal = Math.max(...entries.map(([, value]) => Math.abs(value))) || 1
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">Top features</div>
      {entries.map(([name, value]) => (
        <div key={name} className="flex items-center gap-2">
          <span className="w-28 truncate text-[11px] text-ink-subtle" title={name}>{labelize(name)}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-alt">
            <div className="h-full rounded-full bg-brand" style={{ width: `${(Math.abs(value) / maxVal) * 100}%` }} />
          </div>
          <span className="w-12 text-right text-[11px] tabular-nums text-ink-muted">{value.toFixed(3)}</span>
        </div>
      ))}
    </div>
  )
}

function MetricLine({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11px] text-ink-subtle">{label}</span>
      <span className="text-xs font-medium tabular-nums text-ink">
        {value == null || Number.isNaN(value) ? '—' : value < 1 ? value.toFixed(3) : fmtNumber(value, 2)}
      </span>
    </div>
  )
}

function hasTrainingMetrics(model: ModelPerformance) {
  return [model.r2, model.mae, model.rmse, model.mape, model.accuracy, model.auc, model.f1, model.precision, model.recall]
    .some((value) => value != null)
}

function TrainingMetrics({ models, loading }: { models: ModelPerformance[]; loading: boolean }) {
  if (loading) return <p className="text-xs text-ink-subtle">Loading training metrics…</p>
  const usable = models.filter(hasTrainingMetrics)
  if (usable.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-surface-alt px-3 py-2 text-xs text-ink-muted">
        Not validated
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">Training metrics</div>
      {usable.map((model) => {
        const predictor = model.model_type === 'flood_predictor'
        const classifier = model.model_type === 'flood_classifier'
        const title = predictor ? 'Flood predictor' : classifier ? 'Flood classifier' : labelize(model.model_type)
        return (
          <div key={`${model.model_type}-${model.horizon_days}-${model.model_file}`} className="rounded-lg border border-line bg-surface-alt p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-ink">{title}</span>
              <Badge tone={statusTone(model.model_status)}>{model.model_status}</Badge>
            </div>
            <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
              {predictor && (
                <>
                  <MetricLine label="R²" value={model.r2} />
                  <MetricLine label="MAE" value={model.mae} />
                  <MetricLine label="RMSE" value={model.rmse} />
                  <MetricLine label="MAPE" value={model.mape} />
                </>
              )}
              {classifier && (
                <>
                  <MetricLine label="Accuracy" value={model.accuracy} />
                  <MetricLine label="AUC" value={model.auc} />
                  <MetricLine label="F1" value={model.f1} />
                  <MetricLine label="Precision" value={model.precision} />
                  <MetricLine label="Recall" value={model.recall} />
                </>
              )}
              {!predictor && !classifier && (
                <>
                  <MetricLine label="R²" value={model.r2} />
                  <MetricLine label="MAE" value={model.mae} />
                  <MetricLine label="Accuracy" value={model.accuracy} />
                  <MetricLine label="F1" value={model.f1} />
                </>
              )}
            </div>
            {(model.train_samples || model.test_samples) && (
              <p className="text-[11px] text-ink-subtle">
                Train {model.train_samples?.toLocaleString() ?? '—'} · Test {model.test_samples?.toLocaleString() ?? '—'}
                {model.trained_at ? ` · Trained ${model.trained_at.slice(0, 10)}` : ''}
              </p>
            )}
            {!model.train_samples && !model.test_samples && model.trained_at && (
              <p className="text-[11px] text-ink-subtle">Trained {model.trained_at.slice(0, 10)}</p>
            )}
            <FeatureBars features={model.feature_importance ?? {}} />
          </div>
        )
      })}
    </div>
  )
}

function HorizonDropdown({
  days,
  forecast,
  coverage,
  models,
  metricsLoading,
  alerts,
}: {
  days: number
  forecast?: V2LeadTimeForecast
  coverage?: number | null
  models: ModelPerformance[]
  metricsLoading: boolean
  alerts: Array<{ level: string; type: string; message: string }>
}) {
  const discharge = forecast?.discharge
  const stress = forecast?.water_stress
  const flood = forecast?.flood_risk
  const rain = forecast?.rainfall
  const ci = discharge?.ci_method ? CI_METHOD_LABELS[discharge.ci_method] : undefined
  const dischargeText = discharge?.value_m3s != null ? `${fmtNumber(discharge.value_m3s, 0)} m³/s` : '—'
  const confidenceText = forecast?.confidence != null ? `${(forecast.confidence * 100).toFixed(0)}% confidence` : '—'

  return (
    <details className="group overflow-hidden rounded-xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 items-center gap-2">
          <ChevronRight className="h-4 w-4 shrink-0 text-ink-subtle transition-transform group-open:rotate-90" aria-hidden />
          <span className="text-sm font-semibold text-ink">{days}-day</span>
          <span className="text-sm tabular-nums text-ink-muted">{dischargeText}</span>
        </span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {stress && <Badge tone={stressTone(stress.category)}>{stress.category}</Badge>}
          {flood && <Badge tone={floodTone(flood.category)}>{flood.category}</Badge>}
          <span className="text-xs text-ink-subtle">{confidenceText}</span>
        </span>
      </summary>

      <div className="space-y-4 border-t border-line px-4 py-4">
        {!forecast ? (
          <p className="text-sm text-ink-muted">No forecast for this lead time.</p>
        ) : (
          <>
            {forecast.model_status === 'REJECTED' && (
              <div className="rounded-lg border border-crit/25 bg-crit-soft px-3 py-2 text-xs font-semibold text-crit">
                Failed walk-forward validation — treat as indicative only
              </div>
            )}
            {alerts.map((alert, index) => (
              <div
                key={`${alert.type}-${index}`}
                className={`rounded-lg border px-3 py-2 text-xs ${
                  alert.level === 'CRITICAL'
                    ? 'border-crit/25 bg-crit-soft text-crit'
                    : 'border-warn/25 bg-warn-soft text-warn'
                }`}
              >
                <span className="font-semibold">{alert.level}</span>
                <span className="text-ink-muted"> · {alert.type}</span>
                <p className="mt-1 text-ink-muted">{alert.message}</p>
              </div>
            ))}

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-line bg-surface-alt p-3">
                <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-brand">
                  <Waves className="h-3 w-3" />
                  Discharge
                </div>
                <div className="mt-1 text-xl font-semibold tabular-nums text-ink">
                  {discharge?.value_m3s != null ? fmtNumber(discharge.value_m3s, 0) : '—'}
                  <span className="ml-1 text-xs font-normal text-ink-muted">m³/s</span>
                </div>
                <p className="text-[11px] text-ink-subtle">
                  {discharge?.value_cusecs != null ? `${fmtNumber(discharge.value_cusecs, 0)} cusecs` : '—'}
                </p>
                <p className="mt-1 text-[11px] text-ink-subtle">
                  CI [{discharge?.confidence_lower_m3s != null ? fmtNumber(discharge.confidence_lower_m3s, 0) : '—'}, {discharge?.confidence_upper_m3s != null ? fmtNumber(discharge.confidence_upper_m3s, 0) : '—'}] m³/s
                </p>
                {(ci || coverage != null) && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {ci && <Badge tone={ci.tone}>{ci.label}</Badge>}
                    {coverage != null && (
                      <span className="text-[11px] text-ink-subtle">holdout cov {(coverage * 100).toFixed(0)}%</span>
                    )}
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-line bg-surface-alt p-3">
                <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-brand">
                  <CloudRain className="h-3 w-3" />
                  Rainfall
                </div>
                <div className="mt-1 text-xl font-semibold tabular-nums text-ink">
                  {rain?.value_mm != null ? fmtNumber(rain.value_mm, 0) : '—'}
                  <span className="ml-1 text-xs font-normal text-ink-muted">mm</span>
                </div>
                <p className="text-[11px] text-ink-subtle">
                  Probability {rain?.probability != null ? `${(rain.probability * 100).toFixed(0)}%` : '—'}
                </p>
              </div>
            </div>

            {stress && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs text-ink-muted">
                    <Droplets className="h-3.5 w-3.5 text-brand" />
                    Water stress
                  </div>
                  <Badge tone={stressTone(stress.category)}>{stress.value}/100 {stress.category}</Badge>
                </div>
                {stress.trend !== 0 && (
                  <div className={`flex items-center gap-1 text-[11px] ${stress.trend > 0 ? 'text-ok' : 'text-crit'}`}>
                    {stress.trend > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                    {stress.trend > 0 ? '+' : ''}{stress.trend}% trend
                  </div>
                )}
                {Object.keys(stress.components).length > 0 && (
                  <div className="grid gap-1 sm:grid-cols-3">
                    {Object.entries(stress.components).map(([name, value]) => (
                      <div key={name} className="flex items-center justify-between rounded-md bg-surface-alt px-2 py-1.5 text-[11px]">
                        <span className="capitalize text-ink-subtle">{labelize(name)}</span>
                        <span className="font-medium tabular-nums text-ink">{value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {flood && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs text-ink-muted">
                    <AlertTriangle className="h-3.5 w-3.5 text-warn" />
                    Flood risk
                  </div>
                  <Badge tone={floodTone(flood.category)}>{flood.value}/100 {flood.category}</Badge>
                </div>
                {flood.drivers.length > 0 && (
                  <ul className="space-y-1">
                    {flood.drivers.map((driver) => (
                      <li key={`${driver.name}-${driver.value}`} className="flex flex-wrap items-baseline justify-between gap-2 text-[11px]">
                        <span className="text-ink-muted">{driver.name}</span>
                        <span className="text-ink">{driver.value}{driver.impact ? ` · ${driver.impact}` : ''}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        )}

        <TrainingMetrics models={models} loading={metricsLoading} />
      </div>
    </details>
  )
}

function SourceBadges({ sources }: { sources: string[] }) {
  if (sources.length === 0) return <span className="text-ink-subtle">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {sources.map((source) => (
        <span key={source} className="rounded border border-line px-1.5 py-0.5 text-[10px] font-medium text-ink-muted">
          {source}
        </span>
      ))}
    </div>
  )
}

function exportObservations(summaries: AssetWeeklySummary[]) {
  const rows = ['Asset,River,Province,Week Start,Observations,Avg Inflow,Avg Level,Avg Discharge,Max Inflow,Min Inflow,Sources']
  for (const asset of summaries) {
    for (const week of asset.weeks) {
      rows.push([
        week.asset_name, week.river || '', week.province || '', week.week_start, week.observations,
        week.avg_inflow ?? '', week.avg_level_ft ?? '', week.avg_discharge ?? '',
        week.max_inflow ?? '', week.min_inflow ?? '', week.data_sources.join('+'),
      ].join(','))
    }
  }
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `analyst-observations-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function ObservationHistory({
  onOpenChange,
  weeks,
  onWeeksChange,
  summaries,
  loading,
  error,
  onRetry,
}: {
  onOpenChange: (open: boolean) => void
  weeks: number
  onWeeksChange: (weeks: number) => void
  summaries?: AssetWeeklySummary[]
  loading: boolean
  error: boolean
  onRetry: () => void
}) {
  const asset = summaries?.[0]
  return (
    <details
      className="group overflow-hidden rounded-xl border border-line bg-surface"
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-4 w-4 shrink-0 text-ink-subtle transition-transform group-open:rotate-90" aria-hidden />
        <span className="text-sm font-semibold text-ink">Observation history</span>
        <span className="text-xs text-ink-subtle">Weekly averages</span>
      </summary>
      <div className="space-y-3 border-t border-line px-4 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-xs text-ink-subtle">
            Weeks
            <select
              value={weeks}
              onChange={(event) => onWeeksChange(Number(event.target.value))}
              className={SELECT_CLASS}
              aria-label="Number of weeks"
            >
              {WEEK_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => summaries && exportObservations(summaries)}
            disabled={!summaries?.length}
          >
            <Download className="h-3.5 w-3.5" /> Export CSV
          </Button>
        </div>

        {error && <ErrorState title="Could not load observations" onRetry={onRetry} />}
        {!error && loading && <Spinner label="Loading observations" />}
        {!error && !loading && asset && asset.weeks.length === 0 && (
          <EmptyState title="No observations" message="No weekly observations for this asset in the selected window." />
        )}
        {!error && !loading && !asset && <Spinner label="Loading observations" />}
        {asset && asset.weeks.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line">
                  {['Week', 'Obs', 'Avg inflow', 'Min/Max', 'Avg level', 'Avg outflow', 'Avg discharge', 'Sources'].map((heading) => (
                    <th key={heading} className="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-subtle">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...asset.weeks].reverse().map((week, index) => (
                  <tr key={week.week_start} className="border-b border-line last:border-0">
                    <td className="px-3 py-2 font-medium text-ink-muted">
                      {week.week_start}
                      {index === 0 && <span className="ml-1.5 text-[9px] font-semibold text-brand">LATEST</span>}
                    </td>
                    <td className="px-3 py-2 text-ink-muted">{week.observations}</td>
                    <td className="px-3 py-2 tabular-nums text-ink">{week.avg_inflow != null ? fmtNumber(week.avg_inflow) : '—'}</td>
                    <td className="px-3 py-2 text-ink-subtle">
                      {week.min_inflow != null && week.max_inflow != null
                        ? `${fmtNumber(week.min_inflow)} – ${fmtNumber(week.max_inflow)}`
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-ink-muted">{week.avg_level_ft != null ? `${week.avg_level_ft.toFixed(1)} ft` : '—'}</td>
                    <td className="px-3 py-2 text-ink-muted">{week.avg_outflow != null ? fmtNumber(week.avg_outflow) : '—'}</td>
                    <td className="px-3 py-2 text-ink-muted">{week.avg_discharge != null ? fmtNumber(week.avg_discharge) : '—'}</td>
                    <td className="px-3 py-2"><SourceBadges sources={week.data_sources} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </details>
  )
}

export default function AnalystWorkspacePage() {
  const [assetId, setAssetId] = useState<number | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [weeks, setWeeks] = useState(16)

  const assetsQuery = useQuery<OperationalAsset[]>({
    queryKey: ['operational-assets'],
    queryFn: () => waterApi.getAssets(),
    staleTime: 5 * 60_000,
  })

  const assets = useMemo(
    () => [...(assetsQuery.data ?? [])].sort((a, b) => a.canonical_name.localeCompare(b.canonical_name)),
    [assetsQuery.data],
  )

  useEffect(() => {
    if (assetId == null && assets.length > 0) setAssetId(assets[0].id)
  }, [assetId, assets])

  const predictionQuery = useQuery({
    queryKey: ['v2-prediction', assetId],
    queryFn: () => waterApi.getV2Prediction(assetId as number),
    enabled: assetId != null,
    refetchInterval: REFRESH_MS,
  })

  const modelsQuery = useQuery<ModelPerformance[]>({
    queryKey: ['model-performance'],
    queryFn: () => waterApi.getModelPerformance(),
    refetchInterval: REFRESH_MS,
  })

  const weeklyQuery = useQuery<AssetWeeklySummary[]>({
    queryKey: ['weekly-summary', weeks, assetId],
    queryFn: () => waterApi.getWeeklySummary(weeks, assetId as number),
    enabled: historyOpen && assetId != null,
  })

  const modelsByHorizon = useMemo(() => {
    const grouped = new Map<number, ModelPerformance[]>()
    for (const days of HORIZONS) grouped.set(days, [])
    for (const model of modelsQuery.data ?? []) {
      if (model.asset_id !== assetId || model.horizon_days == null) continue
      if (model.model_type === 'anomaly_detector') continue
      grouped.get(model.horizon_days)?.push(model)
    }
    return grouped
  }, [modelsQuery.data, assetId])

  const selected = assets.find((asset) => asset.id === assetId)
  const prediction = predictionQuery.data
  const refreshing = predictionQuery.isFetching || modelsQuery.isFetching

  const refresh = () => {
    if (assetId == null) return
    void predictionQuery.refetch()
    void modelsQuery.refetch()
    if (historyOpen) void weeklyQuery.refetch()
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          title="Analyst Workspace"
          description="Live 3-, 7-, and 14-day forecasts from the trained model. Open a horizon for the full reading."
          icon={<BarChart3 className="h-6 w-6" />}
          updatedAt={prediction?.timestamp}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={assetId ?? ''}
                onChange={(event) => setAssetId(Number(event.target.value))}
                className={SELECT_CLASS}
                aria-label="Select asset"
                disabled={assets.length === 0}
              >
                {assets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.canonical_name}{asset.river ? ` · ${asset.river}` : ''}
                  </option>
                ))}
              </select>
              <Button variant="ghost" size="sm" onClick={refresh} loading={refreshing} disabled={assetId == null}>
                {!refreshing && <RefreshCw className="h-3.5 w-3.5" />} Refresh
              </Button>
            </div>
          }
        />

        {assetsQuery.isPending && <Spinner label="Loading assets" />}
        {assetsQuery.isError && (
          <ErrorState title="Could not load assets" onRetry={() => void assetsQuery.refetch()} />
        )}
        {!assetsQuery.isPending && !assetsQuery.isError && assets.length === 0 && (
          <EmptyState title="No assets" message="No operational assets are available to forecast." />
        )}

        {assetId != null && assets.length > 0 && (
          <div className="space-y-3">
            {selected && (
              <p className="text-xs text-ink-subtle">
                {selected.canonical_name}
                {selected.province ? ` · ${selected.province}` : ''}
                {prediction?.model_metadata.prediction_method ? ` · ${prediction.model_metadata.prediction_method}` : ''}
                {prediction?.model_metadata.features_used != null ? ` · ${prediction.model_metadata.features_used} features` : ''}
              </p>
            )}

            {predictionQuery.isPending && <Spinner label="Running trained model" />}
            {predictionQuery.isError && (
              <ErrorState
                title="Forecast unavailable"
                message="The trained model did not return a forecast for this asset."
                onRetry={() => void predictionQuery.refetch()}
              />
            )}
            {!predictionQuery.isPending && !predictionQuery.isError && !prediction && (
              <EmptyState title="No forecast" message="The trained model returned no data for this asset." />
            )}
            {prediction && (
              <div className="space-y-2">
                {HORIZONS.map((days) => (
                  <HorizonDropdown
                    key={days}
                    days={days}
                    forecast={prediction.predictions[`${days}_day`]}
                    coverage={prediction.model_metadata.ci_coverage_80?.[String(days)] ?? null}
                    models={modelsByHorizon.get(days) ?? []}
                    metricsLoading={modelsQuery.isPending}
                    alerts={prediction.alerts.filter((alert) => alert.lead_time === `${days}_day`)}
                  />
                ))}
              </div>
            )}

            <ObservationHistory
              onOpenChange={setHistoryOpen}
              weeks={weeks}
              onWeeksChange={setWeeks}
              summaries={weeklyQuery.data}
              loading={historyOpen && weeklyQuery.isPending}
              error={historyOpen && weeklyQuery.isError}
              onRetry={() => void weeklyQuery.refetch()}
            />
          </div>
        )}
      </div>
    </AppShell>
  )
}
