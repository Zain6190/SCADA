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
  Abundant: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  Moderate: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  Stressed: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  Critical: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  Severe: 'bg-red-500/15 text-red-300 border-red-500/30',
}

const FLOOD_COLORS: Record<string, string> = {
  'No Risk': 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  Moderate: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  High: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
  Critical: 'bg-red-500/15 text-red-300 border-red-500/30',
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
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'bg-slate-800/40 text-slate-400 border border-slate-700 hover:text-slate-200'
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
          <h3 className="text-lg font-bold text-slate-100">{data.asset_name}</h3>
          <p className="text-xs text-slate-500">
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
                  ? 'border-red-500/30 bg-red-500/10 text-red-300'
                  : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <AlertTriangle className="h-3 w-3" />
                <span className="font-semibold">{alert.level}</span>
                <span className="text-slate-400">|</span>
                <span>{alert.type}</span>
              </div>
              <p className="mt-1 text-slate-300">{alert.message}</p>
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
        icon={<BarChart3 className="h-5 w-5 text-sky-400" />}
      />
      <CardBody className="space-y-3">
        {/* Discharge */}
        <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-sky-400">
            <Waves className="h-3 w-3" />
            Discharge
          </div>
          <div className="mt-1 text-xl font-bold text-slate-100">
            {discharge.value_m3s.toFixed(0)} <span className="text-xs font-normal text-slate-400">m³/s</span>
          </div>
          <div className="text-[10px] text-slate-500">
            {discharge.value_cusecs.toLocaleString()} cusecs
          </div>
          <div className="mt-1 text-[10px] text-slate-500">
            CI: [{discharge.confidence_lower_m3s.toFixed(0)}, {discharge.confidence_upper_m3s.toFixed(0)}] m³/s
          </div>
        </div>

        {/* Water Stress */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Droplets className="h-3.5 w-3.5 text-sky-400" />
            <span className="text-xs text-slate-400">Water Stress</span>
          </div>
          <Badge tone={stress.category === 'Abundant' ? 'emerald' : stress.category === 'Moderate' ? 'sky' : stress.category === 'Stressed' ? 'amber' : 'red'}>
            {stress.value}/100 {stress.category}
          </Badge>
        </div>

        {/* Flood Risk */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <span className="text-xs text-slate-400">Flood Risk</span>
          </div>
          <Badge tone={flood.category === 'No Risk' ? 'emerald' : flood.category === 'Moderate' ? 'amber' : 'red'}>
            {flood.value}/100 {flood.category}
          </Badge>
        </div>

        {/* Rainfall */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <CloudRain className="h-3.5 w-3.5 text-blue-400" />
            <span className="text-xs text-slate-400">Rainfall</span>
          </div>
          <span className="text-xs font-medium text-slate-300">
            {rain.value_mm.toFixed(0)}mm ({(rain.probability * 100).toFixed(0)}%)
          </span>
        </div>

        {/* Trend */}
        {stress.trend !== 0 && (
          <div className="flex items-center gap-1.5 text-[10px]">
            <TrendingUp className={`h-3 w-3 ${stress.trend > 0 ? 'text-emerald-400' : 'text-red-400'}`} />
            <span className={stress.trend > 0 ? 'text-emerald-400' : 'text-red-400'}>
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
    <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-3">
      <div className="text-[10px] font-semibold uppercase text-slate-500">{label} Accuracy</div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-lg font-bold text-slate-100">{pct}%</span>
        <Badge tone={tone}>{accuracy >= 0.7 ? 'Good' : accuracy >= 0.5 ? 'Fair' : 'Low'}</Badge>
      </div>
    </div>
  )
}
