'use client'

import { useState } from 'react'
import { Droplets, CloudRain, TrendingUp, AlertTriangle, Waves, BarChart3 } from 'lucide-react'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useQuery } from '@tanstack/react-query'
import type { V2AssetPrediction, V2LeadTimeForecast } from '@/features/water/types'

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

const ASSETS = [
  { id: 1, name: 'Tarbela', type: 'reservoir' },
  { id: 2, name: 'Mangla', type: 'reservoir' },
  { id: 9, name: 'Kabul', type: 'river_station' },
  { id: 10, name: 'Chenab', type: 'river_station' },
  { id: 5, name: 'Taunsa', type: 'barrage' },
  { id: 6, name: 'Guddu', type: 'barrage' },
  { id: 7, name: 'Sukkur', type: 'barrage' },
  { id: 8, name: 'Kotri', type: 'barrage' },
]

export default function V2PredictionsTab() {
  const [selectedAsset, setSelectedAsset] = useState<number>(9)

  return (
    <div className="space-y-4">
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

function AssetPredictionDetail({ assetId }: { assetId: number }) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['v2-prediction', assetId],
    queryFn: () => waterApi.getV2Prediction(assetId),
    staleTime: 5 * 60_000,
  })

  if (isPending) return <Spinner />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!data) return <EmptyState title="No prediction" message="No data available." />

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-ink">{data.asset_name}</h3>
          <p className="text-xs text-ink-subtle">
            Method: {data.model_metadata.prediction_method} | Features: {data.model_metadata.features_used}
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
          <LeadTimeCard key={key} label={LEAD_TIME_LABELS[key] ?? key} forecast={forecast} />
        ))}
      </div>

      {/* Model Accuracy */}
      <div className="grid gap-3 sm:grid-cols-3">
        <AccuracyCard label="3-Day" accuracy={data.model_metadata.accuracy_3day} />
        <AccuracyCard label="7-Day" accuracy={data.model_metadata.accuracy_7day} />
        <AccuracyCard label="14-Day" accuracy={data.model_metadata.accuracy_14day} />
      </div>
    </div>
  )
}

function LeadTimeCard({ label, forecast }: { label: string; forecast: V2LeadTimeForecast }) {
  const discharge = forecast.discharge
  const stress = forecast.water_stress
  const flood = forecast.flood_risk
  const rain = forecast.rainfall

  return (
    <Card>
      <CardHeader
        title={label}
        subtitle={`Confidence: ${(forecast.confidence * 100).toFixed(0)}%`}
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

function AccuracyCard({ label, accuracy }: { label: string; accuracy: number }) {
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
