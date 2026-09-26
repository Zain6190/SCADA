'use client'

import { useState } from 'react'
import {
  Droplets, CloudRain, TrendingUp, AlertTriangle, Waves, BarChart3, Gauge, MapPin,
} from 'lucide-react'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useQuery } from '@tanstack/react-query'
import type {
  V2LeadTimeForecast, V2NationalOverview, V2ForecastChart,
} from '@/features/water/types'
import {
  ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis,
  Tooltip as RTooltip, CartesianGrid, Legend, ReferenceLine,
} from 'recharts'

const STRESS_COLORS: Record<string, string> = {
  Abundant: 'bg-ok-soft text-ok border-ok/25',
  Moderate: 'bg-brand-soft text-brand border-brand/25',
  Stressed: 'bg-warn-soft text-warn border-warn/25',
  Critical: 'bg-sev-severe-soft text-sev-severe border-sev-severe/25',
  Severe: 'bg-crit-soft text-crit border-crit/25',
}

const FLOOD_COLORS: Record<string, string> = {
  'No Risk': 'bg-ok-soft text-ok border-ok/25',
  Moderate: 'bg-warn-soft text-warn border-warn/25',
  High: 'bg-sev-severe-soft text-sev-severe border-sev-severe/25',
  Critical: 'bg-crit-soft text-crit border-crit/25',
}

const LEAD_TIME_LABELS: Record<string, string> = {
  '3_day': '3-Day',
  '7_day': '7-Day',
  '14_day': '14-Day',
}

// Interval provenance labels (honest — no implied precision beyond method)
const CI_METHOD_LABELS: Record<string, { label: string; tone: 'emerald' | 'sky' | 'amber' | 'neutral' }> = {
  quantile_q10_q90: { label: 'Quantile 80% CI', tone: 'emerald' },
  residual_p90: { label: 'Residual ±p90', tone: 'sky' },
  physics_band: { label: 'Physics band', tone: 'sky' },
  r2_band: { label: 'Quality band', tone: 'amber' },
  pct_heuristic: { label: '±15% heuristic', tone: 'neutral' },
}

function statusTone(status: string): 'emerald' | 'sky' | 'amber' | 'red' | 'neutral' {
  const s = (status || '').toLowerCase()
  if (s.includes('critical') || s.includes('severe')) return 'red'
  if (s.includes('stressed') || s.includes('moderate') || s.includes('high')) return 'amber'
  if (s.includes('abundant') || s.includes('normal') || s.includes('low')) return 'emerald'
  return 'neutral'
}

const ASSETS = [
  { id: 1, name: 'Tarbela', type: 'reservoir' },
  { id: 2, name: 'Mangla', type: 'reservoir' },
  { id: 3, name: 'Chashma', type: 'barrage' },
  { id: 4, name: 'Kalabagh', type: 'river_station' },
  { id: 5, name: 'Taunsa', type: 'barrage' },
  { id: 6, name: 'Guddu', type: 'barrage' },
  { id: 7, name: 'Sukkur', type: 'barrage' },
  { id: 8, name: 'Kotri', type: 'barrage' },
  { id: 9, name: 'Kabul', type: 'river_station' },
  { id: 10, name: 'Chenab', type: 'river_station' },
  { id: 11, name: 'Panjnad', type: 'river_station' },
]

export default function V2PredictionsTab() {
  const [selectedAsset, setSelectedAsset] = useState<number>(9)

  const { data: overview } = useQuery({
    queryKey: ['v2-national-overview'],
    queryFn: () => waterApi.getV2NationalOverview(),
    staleTime: 5 * 60_000,
    retry: 1,
  })

  return (
    <div className="space-y-4">
      {/* National Overview */}
      {overview && <NationalOverviewPanel data={overview} />}

      {/* Asset Selector */}
      <div className="flex flex-wrap gap-2">
        {ASSETS.map((a) => (
          <button
            key={a.id}
            onClick={() => setSelectedAsset(a.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              selectedAsset === a.id
                ? 'bg-brand-soft text-brand border border-brand/25'
                : 'bg-surface-alt text-ink-muted border border-line-strong hover:text-ink'
            }`}
          >
            {a.name}
          </button>
        ))}
      </div>

      {/* Prediction Detail */}
      <AssetPredictionDetail assetId={selectedAsset} />
    </div>
  )
}

function NationalOverviewPanel({ data }: { data: V2NationalOverview }) {
  return (
    <Card>
      <CardHeader
        title="National Overview"
        subtitle={`Updated ${data.timestamp.slice(0, 16).replace('T', ' ')} UTC`}
        icon={<Gauge className="h-5 w-5 text-brand" />}
      />
      <CardBody className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">National WAI</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-2xl font-bold text-ink">{data.national_wai.toFixed(1)}</span>
              <Badge tone={statusTone(data.national_status)}>{data.national_status}</Badge>
            </div>
          </div>
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">Assets Monitored</div>
            <div className="mt-1 text-2xl font-bold text-ink">{data.assets_monitored}</div>
          </div>
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">Critical Alerts</div>
            <div className="mt-1 text-2xl font-bold text-ink">{data.critical_alerts.length}</div>
          </div>
        </div>

        {/* Province WAI chips */}
        <div className="flex flex-wrap gap-2">
          {data.provinces.map((p) => (
            <span
              key={p.province}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-surface-alt px-2.5 py-1 text-[11px]"
            >
              <MapPin className="h-3 w-3 text-ink-subtle" />
              <span className="text-ink-muted">{p.province}</span>
              <span className="font-semibold text-ink">{p.wai_score}</span>
              <Badge tone={statusTone(p.category)}>{p.category}</Badge>
            </span>
          ))}
        </div>

        {/* Critical alerts */}
        {data.critical_alerts.length > 0 && (
          <div className="space-y-2">
            {data.critical_alerts.map((alert, i) => (
              <div
                key={i}
                className={`rounded-lg border px-3 py-2 text-xs ${
                  alert.level === 'CRITICAL'
                    ? 'border-crit/25 bg-crit-soft text-crit'
                    : 'border-warn/25 bg-warn-soft text-warn'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="h-3 w-3" />
                  <span className="font-semibold">{alert.level}</span>
                  <span className="text-ink-muted">|</span>
                  <span>{alert.type}</span>
                  <span className="text-ink-muted">|</span>
                  <span>{alert.lead_time}</span>
                </div>
                <p className="mt-1 text-ink-muted">{alert.message}</p>
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function AssetPredictionDetail({ assetId }: { assetId: number }) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['v2-prediction', assetId],
    queryFn: () => waterApi.getV2Prediction(assetId),
    staleTime: 5 * 60_000,
  })

  const { data: chart, isPending: chartPending, isError: chartError } = useQuery({
    queryKey: ['v2-forecast-chart', assetId],
    queryFn: () => waterApi.getV2ForecastChart(assetId),
    staleTime: 5 * 60_000,
    retry: 1,
  })

  if (isPending) return <Spinner />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!data) return <EmptyState title="No prediction" message="No data available." />

  const coverage = data.model_metadata.ci_coverage_80

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-ink">{data.asset_name}</h3>
          <p className="text-xs text-ink-subtle">
            Method: {data.model_metadata.prediction_method}
            {data.model_metadata.features_used != null && (
              <> | Features: {data.model_metadata.features_used}</>
            )}
          </p>
        </div>
        <Badge tone="amber">EXPERIMENTAL</Badge>
      </div>

      {/* Alerts */}
      {data.alerts.length > 0 && (
        <div className="space-y-2">
          {data.alerts.map((alert, i) => (
            <div
              key={i}
              className={`rounded-lg border px-3 py-2 text-xs ${
                alert.level === 'CRITICAL'
                  ? 'border-crit/25 bg-crit-soft text-crit'
                  : 'border-warn/25 bg-warn-soft text-warn'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <AlertTriangle className="h-3 w-3" />
                <span className="font-semibold">{alert.level}</span>
                <span className="text-ink-muted">|</span>
                <span>{alert.type}</span>
              </div>
              <p className="mt-1 text-ink-muted">{alert.message}</p>
            </div>
          ))}
        </div>
      )}

      {/* Lead Time Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(data.predictions).map(([key, forecast]) => (
          <LeadTimeCard
            key={key}
            label={LEAD_TIME_LABELS[key] ?? key}
            forecast={forecast}
            coverage={coverage?.[key.replace('_day', '')] ?? null}
          />
        ))}
      </div>

      {/* Forecast Chart */}
      {chartPending ? (
        <Spinner />
      ) : chartError ? (
        <div className="rounded-xl border border-line-strong bg-surface-alt p-4 text-center text-xs text-ink-subtle">
          Forecast chart unavailable for this asset.
        </div>
      ) : chart ? (
        <ForecastChartCard chart={chart} />
      ) : null}

      {/* Model Accuracy */}
      <div className="grid gap-3 sm:grid-cols-3">
        <AccuracyCard label="3-Day" accuracy={data.model_metadata.accuracy_3day} />
        <AccuracyCard label="7-Day" accuracy={data.model_metadata.accuracy_7day} />
        <AccuracyCard label="14-Day" accuracy={data.model_metadata.accuracy_14day} />
      </div>
    </div>
  )
}

function ForecastChartCard({ chart }: { chart: V2ForecastChart }) {
  const rows = chart.dates.map((d, i) => {
    const lo = chart.confidence_lower[i]
    const hi = chart.confidence_upper[i]
    const forecast = chart.forecast_3d[i] ?? chart.forecast_7d[i] ?? chart.forecast_14d[i]
    return {
      date: d,
      actual: chart.actual[i],
      forecast,
      band: lo != null && hi != null ? [lo, hi] : null,
    }
  })

  const hasForecast = rows.some((r) => r.forecast != null)
  const hasThreshold = chart.warning_level != null || chart.danger_level != null

  return (
    <Card>
      <CardHeader
        title="Discharge — 30-Day Actual + Forecast"
        subtitle="cusecs | dashed = lead-time forecast | band = 80% interval"
        icon={<BarChart3 className="h-5 w-5 text-brand" />}
      />
      <CardBody>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-line-strong" opacity={0.5} />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis tick={{ fontSize: 10 }} width={56} />
              <RTooltip
                formatter={(value: unknown, name: string) => {
                  if (Array.isArray(value)) {
                    return [
                      `${Number(value[0]).toLocaleString()} – ${Number(value[1]).toLocaleString()}`,
                      '80% interval',
                    ]
                  }
                  return [Number(value).toLocaleString(), name]
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {chart.danger_level != null && (
                <ReferenceLine
                  y={chart.danger_level}
                  stroke="#ef4444"
                  strokeDasharray="4 4"
                  label={{ value: 'Danger', fontSize: 10, fill: '#ef4444', position: 'insideTopRight' }}
                />
              )}
              {chart.warning_level != null && (
                <ReferenceLine
                  y={chart.warning_level}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  label={{ value: 'Warning', fontSize: 10, fill: '#f59e0b', position: 'insideTopRight' }}
                />
              )}
              <Area
                type="monotone"
                dataKey="band"
                stroke="none"
                fill="#38bdf8"
                fillOpacity={0.15}
                name="80% interval"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#0ea5e9"
                strokeWidth={2}
                dot={false}
                name="Actual"
                connectNulls
                isAnimationActive={false}
              />
              {hasForecast && (
                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={{ r: 3 }}
                  name="Forecast"
                  connectNulls
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        {!hasForecast && !hasThreshold && (
          <p className="mt-1 text-center text-[10px] text-ink-subtle">
            No forecast points or thresholds available for this asset.
          </p>
        )}
      </CardBody>
    </Card>
  )
}

function LeadTimeCard({
  label, forecast, coverage,
}: { label: string; forecast: V2LeadTimeForecast; coverage?: number | null }) {
  const discharge = forecast.discharge
  const stress = forecast.water_stress
  const flood = forecast.flood_risk
  const rain = forecast.rainfall
  const ci = discharge.ci_method ? CI_METHOD_LABELS[discharge.ci_method] : undefined

  return (
    <Card>
      <CardHeader
        title={label}
        subtitle={
          forecast.confidence != null
            ? `Confidence: ${(forecast.confidence * 100).toFixed(0)}%`
            : 'Confidence: not validated'
        }
        icon={<BarChart3 className="h-5 w-5 text-brand" />}
      />
      <CardBody className="space-y-3">
        {/* Discharge */}
        <div className="rounded-lg border border-line-strong bg-surface-alt p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-brand">
            <Waves className="h-3 w-3" />
            Discharge
          </div>
          <div className="mt-1 text-xl font-bold text-ink">
            {discharge.value_m3s.toFixed(0)} <span className="text-xs font-normal text-ink-muted">m³/s</span>
          </div>
          <div className="text-[10px] text-ink-subtle">
            {discharge.value_cusecs.toLocaleString()} cusecs
          </div>
          <div className="mt-1 text-[10px] text-ink-subtle">
            CI: [{discharge.confidence_lower_m3s.toFixed(0)}, {discharge.confidence_upper_m3s.toFixed(0)}] m³/s
          </div>
          {ci && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <Badge tone={ci.tone}>{ci.label}</Badge>
              {coverage != null && (
                <span className="text-[10px] text-ink-subtle">
                  holdout cov {(coverage * 100).toFixed(0)}%
                </span>
              )}
            </div>
          )}
        </div>

        {/* Water Stress */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Droplets className="h-3.5 w-3.5 text-brand" />
            <span className="text-xs text-ink-muted">Water Stress</span>
          </div>
          <Badge tone={stress.category === 'Abundant' ? 'emerald' : stress.category === 'Moderate' ? 'sky' : stress.category === 'Stressed' ? 'amber' : 'red'}>
            {stress.value}/100 {stress.category}
          </Badge>
        </div>

        {/* Flood Risk */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-warn" />
            <span className="text-xs text-ink-muted">Flood Risk</span>
          </div>
          <Badge tone={flood.category === 'No Risk' ? 'emerald' : flood.category === 'Moderate' ? 'amber' : 'red'}>
            {flood.value}/100 {flood.category}
          </Badge>
        </div>

        {/* Rainfall */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <CloudRain className="h-3.5 w-3.5 text-brand" />
            <span className="text-xs text-ink-muted">Rainfall</span>
          </div>
          <span className="text-xs font-medium text-ink-muted">
            {rain.value_mm.toFixed(0)}mm ({(rain.probability * 100).toFixed(0)}%)
          </span>
        </div>

        {/* Trend */}
        {stress.trend !== 0 && (
          <div className="flex items-center gap-1.5 text-[10px]">
            <TrendingUp className={`h-3 w-3 ${stress.trend > 0 ? 'text-ok' : 'text-crit'}`} />
            <span className={stress.trend > 0 ? 'text-ok' : 'text-crit'}>
              {stress.trend > 0 ? '+' : ''}{stress.trend}% trend
            </span>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function AccuracyCard({ label, accuracy }: { label: string; accuracy: number | null | undefined }) {
  if (accuracy == null) {
    return (
      <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
        <div className="text-[10px] font-semibold uppercase text-ink-subtle">{label} Accuracy</div>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-lg font-bold text-ink-muted">—</span>
          <Badge tone="neutral">Not validated</Badge>
        </div>
      </div>
    )
  }

  const pct = (accuracy * 100).toFixed(0)
  const tone = accuracy >= 0.7 ? 'emerald' : accuracy >= 0.5 ? 'sky' : accuracy >= 0.3 ? 'amber' : 'red'

  return (
    <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
      <div className="text-[10px] font-semibold uppercase text-ink-subtle">{label} Accuracy</div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-lg font-bold text-ink">{pct}%</span>
        <Badge tone={tone}>{accuracy >= 0.7 ? 'Good' : accuracy >= 0.5 ? 'Fair' : 'Low'}</Badge>
      </div>
    </div>
  )
}
