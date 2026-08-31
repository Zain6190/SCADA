// packages/dashboard/src/app/water/predictions/page.tsx
// AquaVision Predictions - Flood (XGBoost per-asset) + Water Stress (WAI per-region).
'use client'

import { useState, useEffect } from 'react'
import { Cpu, RefreshCw, AlertTriangle, FlaskConical, TrendingUp } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const RISK_COLORS: Record<string, string> = {
  NORMAL: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  WATCH: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  WARNING: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  CRITICAL: 'bg-red-500/15 text-red-300 border-red-500/30',
}

const RISK_DOT: Record<string, string> = {
  NORMAL: 'bg-emerald-400',
  WATCH: 'bg-sky-400',
  WARNING: 'bg-amber-400',
  CRITICAL: 'bg-red-400',
}

const SEVERITY_TONE: Record<string, 'red' | 'amber' | 'sky' | 'emerald' | 'slate'> = {
  Critical: 'red',
  Severe: 'amber',
  Stressed: 'sky',
  Moderate: 'emerald',
  Normal: 'emerald',
}

const ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

interface WAIPrediction {
  id: number
  region_id: number
  target_week_start_date: string
  model_type: string
  model_version: string
  predicted_severity: string
  predicted_wai_score: number
  confidence: number
}

export default function PredictionsPage() {
  const [tab, setTab] = useState<'flood' | 'wai'>('flood')

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Predictions"
          description="ML-powered forecasts for flood risk and water stress"
          icon={<TrendingUp className="h-6 w-6" />}
        />

        {/* Tabs */}
        <div className="flex gap-1 rounded-xl border border-slate-700 bg-slate-800/40 p-1 w-fit">
          <button
            onClick={() => setTab('flood')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'flood'
                ? 'bg-sky-500/15 text-sky-300'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Cpu className="mr-1.5 inline h-4 w-4" />
            Flood Predictions
          </button>
          <button
            onClick={() => setTab('wai')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'wai'
                ? 'bg-sky-500/15 text-sky-300'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="mr-1.5 inline h-4 w-4" />
            Water Stress Predictions
          </button>
        </div>

        {tab === 'flood' ? <FloodPredictionsTab /> : <WAIPredictionsTab />}
      </div>
    </AppShell>
  )
}

// ─── Flood Predictions Tab ──────────────────────────────────────────────────

function FloodPredictionsTab() {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<number | null>(null)

  const trainMutation = useMutation({
    mutationFn: () => waterApi.trainAllModels(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['prediction-summary'] }),
  })

  const runPredMutation = useMutation({
    mutationFn: () => waterApi.runPredictions(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['prediction-summary'] }),
  })

  const { data: metadata } = useQuery({
    queryKey: ['ml-model-metadata'],
    queryFn: () => waterApi.getModelMetadata(),
    staleTime: 30 * 60_000,
  })

  const { data: modelStatus } = useQuery({
    queryKey: ['ml-model-status'],
    queryFn: () => waterApi.getModelStatus(),
    staleTime: 5 * 60_000,
  })

  const { data: dbPredictions, isLoading: predsLoading } = useQuery({
    queryKey: ['prediction-summary'],
    queryFn: () => waterApi.getPredictionSummary(),
    staleTime: 5 * 60_000,
  })

  // Index predictions by asset_id for quick lookup
  const predsByAsset: Record<number, any[]> = {}
  for (const p of dbPredictions?.predictions || []) {
    if (!predsByAsset[p.asset_id]) predsByAsset[p.asset_id] = []
    predsByAsset[p.asset_id].push(p)
  }

  return (
    <>
      {trainMutation.isSuccess && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
          Training complete: {trainMutation.data.models_trained} models trained.
        </div>
      )}

      {/* Model Health Summary */}
      {metadata && (
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-3">
            <div className="text-[10px] font-semibold uppercase text-slate-500">Model Version</div>
            <div className="mt-1 font-mono text-sm font-bold text-slate-200">{metadata.model_version}</div>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-3">
            <div className="text-[10px] font-semibold uppercase text-slate-500">Total Model Files</div>
            <div className="mt-1 text-sm font-bold text-slate-200">{modelStatus?.total_files ?? '—'}</div>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-3">
            <div className="text-[10px] font-semibold uppercase text-slate-500">Weather Features</div>
            <div className="mt-1">
              <Badge tone={metadata.weather_features ? 'emerald' : 'slate'}>
                {metadata.weather_features ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-3">
            <div className="text-[10px] font-semibold uppercase text-slate-500">Log Transform</div>
            <div className="mt-1">
              <Badge tone={metadata.log_transform ? 'emerald' : 'slate'}>
                {metadata.log_transform ? 'Active' : 'Off'}
              </Badge>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Badge tone="amber">
          <FlaskConical className="mr-1 inline h-3 w-3" />
          EXPERIMENTAL
        </Badge>
        <button
          onClick={() => runPredMutation.mutate()}
          disabled={runPredMutation.isPending}
          className="flex items-center gap-1.5 rounded-lg bg-sky-500/15 px-3 py-1.5 text-xs font-medium text-sky-300 border border-sky-500/30 hover:bg-sky-500/25 transition disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${runPredMutation.isPending ? 'animate-spin' : ''}`} />
          {runPredMutation.isPending ? 'Running...' : 'Run Predictions'}
        </button>
        <button
          onClick={() => trainMutation.mutate()}
          disabled={trainMutation.isPending}
          className="flex items-center gap-1.5 rounded-lg bg-violet-500/15 px-3 py-1.5 text-xs font-medium text-violet-300 border border-violet-500/30 hover:bg-violet-500/25 transition disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${trainMutation.isPending ? 'animate-spin' : ''}`} />
          {trainMutation.isPending ? 'Training...' : 'Retrain Models'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ASSET_IDS.map((id) => (
          <PredictionCard
            key={id}
            assetId={id}
            dbPredictions={predsByAsset[id] || []}
            isLoading={predsLoading}
            isExpanded={expanded === id}
            onToggle={() => setExpanded(expanded === id ? null : id)}
            metadata={metadata}
          />
        ))}
      </div>
    </>
  )
}

function PredictionCard({
  assetId,
  dbPredictions,
  isLoading,
  isExpanded,
  onToggle,
  metadata,
}: {
  assetId: number
  dbPredictions: any[]
  isLoading: boolean
  isExpanded: boolean
  onToggle: () => void
  metadata?: any
}) {
  // Use 7d prediction as primary, fallback to first available
  const pred = dbPredictions.find(p => p.horizon === 7) || dbPredictions[0]
  const assetMeta = metadata?.assets?.[String(assetId)]

  return (
    <Card>
      <button onClick={onToggle} className="w-full text-left">
        <CardHeader
          title={pred?.asset_name ?? `Asset ${assetId}`}
          subtitle={
            isLoading ? 'Loading...' : pred ? `${pred.horizon}-day forecast` : 'No predictions yet'
          }
          icon={
            pred ? (
              <div className={`h-3 w-3 rounded-full ${RISK_DOT[pred.risk_category] ?? 'bg-slate-500'}`} />
            ) : (
              <Cpu className="h-5 w-5 text-slate-500" />
            )
          }
          accent={pred ? RISK_COLORS[pred.risk_category] ?? 'bg-slate-500/15 text-slate-300' : 'bg-slate-500/15 text-slate-500'}
        />
      </button>

      {isExpanded && (
        <CardBody className="border-t border-slate-800/70 pt-4">
          {isLoading ? (
            <Spinner />
          ) : !pred ? (
            <EmptyState title="No predictions" message="Run predictions to generate forecasts." />
          ) : (
            <>
              <DBPredictionDetails pred={pred} />
              {assetMeta && <ModelHealthBar assetMeta={assetMeta} />}
            </>
          )}
        </CardBody>
      )}
    </Card>
  )
}

function DBPredictionDetails({ pred }: { pred: any }) {
  const features = pred.features_used || []
  const fi = pred.feature_importance || {}
  const topFeatures = Object.entries(fi)
    .map(([k, v]) => [k, Number(v)] as const)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5)

  return (
    <div className="space-y-3 text-xs">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-slate-500">Predicted Value</div>
          <div className="text-lg font-bold text-slate-100">
            {pred.predicted_value != null ? Number(pred.predicted_value).toLocaleString() : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Prediction Interval</div>
          <div className="font-medium text-slate-300">
            {pred.predicted_lower != null ? Number(pred.predicted_lower).toLocaleString() : '—'}
            {' — '}
            {pred.predicted_upper != null ? Number(pred.predicted_upper).toLocaleString() : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Risk Score</div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-100">{pred.risk_score}/100</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${RISK_COLORS[pred.risk_category] ?? ''}`}>
              {pred.risk_category}
            </span>
          </div>
        </div>
        <div>
          <div className="text-slate-500">Confidence</div>
          <div className="font-medium text-slate-300">
            {pred.confidence != null ? `${(pred.confidence * 100).toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        {pred.exceeds_warning && (
          <Badge tone="amber">
            <AlertTriangle className="mr-1 inline h-3 w-3" />
            Exceeds Warning
          </Badge>
        )}
        {pred.exceeds_danger && (
          <Badge tone="red">
            <AlertTriangle className="mr-1 inline h-3 w-3" />
            Exceeds Danger
          </Badge>
        )}
      </div>

      {/* Weather Context — always shown */}
      <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-2">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-sky-400">
          <TrendingUp className="h-3 w-3" />
          Weather Context
        </div>
        <div className="mt-1 grid grid-cols-3 gap-2 text-[10px]">
          <div>
            <div className="text-slate-500">7-Day Precip</div>
            <div className="font-mono text-slate-300">
              {fi.forecast_precip_7d != null ? `${fi.forecast_precip_7d}` : 'Included in model'}
            </div>
          </div>
          <div>
            <div className="text-slate-500">Max Temp</div>
            <div className="font-mono text-slate-300">
              {fi.forecast_temp_max != null ? `${fi.forecast_temp_max}` : 'Included in model'}
            </div>
          </div>
          <div>
            <div className="text-slate-500">Humidity</div>
            <div className="font-mono text-slate-300">
              {fi.forecast_humidity_mean != null ? `${fi.forecast_humidity_mean}` : 'Included in model'}
            </div>
          </div>
        </div>
      </div>

      {topFeatures.length > 0 && (
        <div>
          <div className="mb-1 text-slate-500">Top Features</div>
          <div className="space-y-1">
            {topFeatures.map(([name, importance]) => (
              <div key={name} className="flex items-center gap-2">
                <div className="h-1.5 rounded-full bg-violet-500/30" style={{ width: `${importance * 100}%`, minWidth: 4 }} />
                <span className="text-slate-400">{name}</span>
                <span className="ml-auto text-slate-600">{(importance * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-slate-600">
        Model: {pred.model_version} | {pred.horizon}d | Generated: {pred.generated_at}
      </div>
    </div>
  )
}

function ModelHealthBar({ assetMeta }: { assetMeta: any }) {
  const models = assetMeta.models || {}
  const entries = Object.entries(models).filter(([, v]: [string, any]) => v.status === 'SUCCESS')

  if (entries.length === 0) return null

  return (
    <div className="mt-3 border-t border-slate-800/50 pt-3">
      <div className="mb-2 text-[10px] font-semibold uppercase text-slate-500">Trained Models</div>
      <div className="space-y-1">
        {entries.map(([key, m]: [string, any]) => (
          <div key={key} className="flex items-center justify-between rounded bg-slate-800/30 px-2 py-1 text-[10px]">
            <span className="text-slate-400">{m.model_type} ({m.horizon}d)</span>
            <div className="flex items-center gap-2">
              <span className="text-slate-500">R²={m.r2?.toFixed(3) ?? '—'}</span>
              <span className="text-slate-500">MAE={m.mae?.toFixed(2) ?? '—'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── WAI Predictions Tab ────────────────────────────────────────────────────

function WAIPredictionsTab() {
  const [predictions, setPredictions] = useState<WAIPrediction[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    waterApi.getPredictions({ limit: 50 }).then(setPredictions).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner label="Loading WAI predictions" />
  if (predictions.length === 0) return <EmptyState title="No WAI predictions" message="Run the prediction pipeline to generate forecasts." />

  const xgbPreds = predictions.filter(p => p.model_version === 'xgb-v1.0')
  const otherPreds = predictions.filter(p => p.model_version !== 'xgb-v1.0')

  return (
    <div className="space-y-4">
      {xgbPreds.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-slate-300">XGBoost Next-Month Forecasts</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {xgbPreds.map(pred => (
              <WAIPredictionCard key={pred.id} pred={pred} />
            ))}
          </div>
        </div>
      )}

      {otherPreds.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-slate-400">Historical Predictions</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {otherPreds.slice(0, 14).map(pred => (
              <WAIPredictionCard key={pred.id} pred={pred} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function WAIPredictionCard({ pred }: { pred: WAIPrediction }) {
  const tone = SEVERITY_TONE[pred.predicted_severity] || 'slate'
  return (
    <Card>
      <div className="p-4">
        <div className="flex items-start justify-between mb-2">
          <span className="font-bold text-slate-100">Region {pred.region_id}</span>
          <Badge tone={tone}>{pred.predicted_severity}</Badge>
        </div>
        <div className="space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-slate-500">WAI Score</span>
            <span className="font-mono font-bold text-slate-200">{pred.predicted_wai_score.toFixed(1)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Confidence</span>
            <span className="font-mono text-slate-300">{(pred.confidence * 100).toFixed(0)}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Target</span>
            <span className="text-slate-400">{pred.target_week_start_date}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Model</span>
            <span className="text-slate-400">{pred.model_version}</span>
          </div>
        </div>
      </div>
    </Card>
  )
}
