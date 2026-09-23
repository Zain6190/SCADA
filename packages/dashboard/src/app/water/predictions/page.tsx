// packages/dashboard/src/app/water/predictions/page.tsx
// AquaVision Predictions - Flood (XGBoost per-asset) + Water Stress (WAI per-region).
'use client'

import { useState, useEffect, Suspense } from 'react'
import { Cpu, RefreshCw, AlertTriangle, FlaskConical, TrendingUp, Activity, Zap } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import type { MLPrediction } from '@/features/water/types'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime } from '@/lib/format'
import V2PredictionsTab from './v2-tab'

const RISK_COLORS: Record<string, string> = {
  NORMAL: 'bg-ok-soft text-ok border-ok/25',
  WATCH: 'bg-brand-soft text-brand border-brand/25',
  WARNING: 'bg-warn-soft text-warn border-warn/25',
  CRITICAL: 'bg-crit-soft text-crit border-crit/25',
}

const RISK_DOT: Record<string, string> = {
  NORMAL: 'bg-ok',
  WATCH: 'bg-brand',
  WARNING: 'bg-warn',
  CRITICAL: 'bg-crit',
}

const SEVERITY_TONE: Record<string, 'red' | 'amber' | 'sky' | 'emerald' | 'slate'> = {
  Critical: 'red',
  Severe: 'amber',
  Stressed: 'sky',
  Moderate: 'emerald',
  Normal: 'emerald',
}

const ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]

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
  const [tab, setTab] = useState<'v2' | 'flood' | 'wai'>('v2')

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Predictions"
          description="ML-powered forecasts for flood risk and water stress"
          icon={<TrendingUp className="h-6 w-6" />}
        />

        {/* Tabs */}
        <div className="flex gap-1 rounded-xl border border-line-strong bg-surface-alt p-1 w-fit">
          <button
            onClick={() => setTab('v2')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'v2'
                ? 'bg-brand-soft text-brand'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <Zap className="mr-1.5 inline h-4 w-4" />
            AquaVision v2
          </button>
          <button
            onClick={() => setTab('flood')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'flood'
                ? 'bg-brand-soft text-brand'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <Cpu className="mr-1.5 inline h-4 w-4" />
            Flood Predictions
          </button>
          <button
            onClick={() => setTab('wai')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === 'wai'
                ? 'bg-brand-soft text-brand'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <TrendingUp className="mr-1.5 inline h-4 w-4" />
            Water Stress Predictions
          </button>
        </div>

        {tab === 'v2' && <V2PredictionsTab />}
        {tab === 'flood' && <FloodPredictionsTab />}
        {tab === 'wai' && <WAIPredictionsTab />}
      </div>
    </AppShell>
  )
}

// ─── Flood Predictions Tab ──────────────────────────────────────────────────

function FloodPredictionsTab() {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<number | null>(null)

  const trainMutation = useMutation({
    mutationFn: () => waterApi.triggerMLTrain([7]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ml-predictions'] }),
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

  return (
    <>
      {trainMutation.isSuccess && (
        <div className="rounded-xl border border-ok/25 bg-ok-soft px-4 py-3 text-sm text-ok">
          Training complete: {trainMutation.data.models_trained} models trained.
        </div>
      )}

      {/* Model Health Summary */}
      {metadata && (
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">Model Version</div>
            <div className="mt-1 font-mono text-sm font-bold text-ink">{metadata.model_version}</div>
          </div>
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">Total Model Files</div>
            <div className="mt-1 text-sm font-bold text-ink">{modelStatus?.total_files ?? '—'}</div>
          </div>
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">Weather Features</div>
            <div className="mt-1">
              <Badge tone={metadata.weather_features ? 'emerald' : 'slate'}>
                {metadata.weather_features ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
          </div>
          <div className="rounded-xl border border-line-strong bg-surface-alt p-3">
            <div className="text-[10px] font-semibold uppercase text-ink-subtle">Log Transform</div>
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
          onClick={() => trainMutation.mutate()}
          disabled={trainMutation.isPending}
          className="flex items-center gap-1.5 rounded-lg bg-brand-soft px-3 py-1.5 text-xs font-medium text-brand border border-brand/25 hover:bg-brand-soft transition disabled:opacity-50"
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
  isExpanded,
  onToggle,
  metadata,
}: {
  assetId: number
  isExpanded: boolean
  onToggle: () => void
  metadata?: any
}) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['ml-predictions', assetId],
    queryFn: () => waterApi.getMLPredictions(assetId, '7'),
    staleTime: 5 * 60_000,
  })

  const pred = data?.[0]
  const assetMeta = metadata?.assets?.[String(assetId)]
  const targetField = pred?.target_field ?? 'level'
  const dotColor = targetField === 'level'
    ? (RISK_DOT[pred?.risk_level] ?? 'bg-surface-sunken')
    : 'bg-ok'

  return (
    <Card>
      <button onClick={onToggle} className="w-full text-left">
        <CardHeader
          title={pred?.asset_name ?? `Asset ${assetId}`}
          subtitle={
            isPending ? 'Loading...' : isError ? 'Failed to load' : pred ? `${pred.horizon_days}-day forecast` : 'No model trained'
          }
          icon={
            pred ? (
              <div className={`h-3 w-3 rounded-full ${dotColor}`} />
            ) : (
              <Cpu className="h-5 w-5 text-ink-subtle" />
            )
          }
          accent={pred ? RISK_COLORS[pred.risk_level] ?? 'bg-surface-sunken text-ink-muted' : 'bg-surface-sunken text-ink-subtle'}
        />
      </button>

      {isExpanded && (
        <CardBody className="border-t border-line pt-4">
          {isPending ? (
            <Spinner />
          ) : isError ? (
            <ErrorState onRetry={() => refetch()} />
          ) : !pred ? (
            <EmptyState title="No model" message="Train models first." />
          ) : (
            <>
              <PredictionDetails pred={pred} />
              {assetMeta && <ModelHealthBar assetMeta={assetMeta} />}
            </>
          )}
        </CardBody>
      )}
    </Card>
  )
}

function PredictionDetails({ pred }: { pred: MLPrediction }) {
  const topFeatures = Object.entries(pred.feature_importance)
    .map(([k, v]) => [k, Number(v)] as const)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5)

  const targetField = pred.target_field ?? 'level'
  const predictedValue = targetField === 'inflow'
    ? pred.predicted_inflow
    : targetField === 'discharge'
    ? pred.predicted_discharge
    : pred.predicted_level_ft
  const valueLabel = targetField === 'inflow'
    ? 'Predicted Inflow (cusecs)'
    : targetField === 'discharge'
    ? 'Predicted Discharge (cusecs)'
    : 'Predicted Level (ft)'
  const unit = targetField === 'level' ? 'ft' : 'cusecs'

  return (
    <div className="space-y-3 text-xs">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-ink-subtle">{valueLabel}</div>
          <div className="text-lg font-bold text-ink">
            {predictedValue != null ? predictedValue.toLocaleString() : '—'}
          </div>
        </div>
        <div>
          <div className="text-ink-subtle">Prediction Interval</div>
          <div className="font-medium text-ink-muted">
            {pred.lower_bound != null ? pred.lower_bound.toLocaleString() : '—'}
            {' — '}
            {pred.upper_bound != null ? pred.upper_bound.toLocaleString() : '—'}
          </div>
        </div>
        {targetField === 'level' ? (
          <>
            <div>
              <div className="text-ink-subtle">Risk Score</div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-ink">{pred.risk_score}/100</span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${RISK_COLORS[pred.risk_level] ?? ''}`}>
                  {pred.risk_level}
                </span>
              </div>
            </div>
            <div>
              <div className="text-ink-subtle">Status</div>
              <Badge tone="amber">
                <FlaskConical className="mr-1 inline h-3 w-3" />
                {pred.model_status}
              </Badge>
            </div>
          </>
        ) : (
          <>
            <div>
              <div className="text-ink-subtle">Model Type</div>
              <div className="font-medium text-ink-muted capitalize">{targetField} Prediction</div>
            </div>
            <div>
              <div className="text-ink-subtle">Status</div>
              <Badge tone="amber">
                <FlaskConical className="mr-1 inline h-3 w-3" />
                {pred.model_status}
              </Badge>
            </div>
          </>
        )}
      </div>

      <div className="flex gap-2">
        {targetField === 'level' && pred.exceeds_warning && (
          <Badge tone="amber">
            <AlertTriangle className="mr-1 inline h-3 w-3" />
            Exceeds Warning
          </Badge>
        )}
        {targetField === 'level' && pred.exceeds_danger && (
          <Badge tone="red">
            <AlertTriangle className="mr-1 inline h-3 w-3" />
            Exceeds Danger
          </Badge>
        )}
        {targetField !== 'level' && (
          <Badge tone="emerald">
            <Activity className="mr-1 inline h-3 w-3" />
            {targetField === 'inflow' ? 'Inflow Forecast' : 'Discharge Forecast'}
          </Badge>
        )}
      </div>

      {/* Weather Context Indicator */}
      <div className="rounded-lg border border-brand/25 bg-brand-soft p-2">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-brand">
          <TrendingUp className="h-3 w-3" />
          Weather Context
        </div>
        <div className="mt-1 grid grid-cols-3 gap-2 text-[10px]">
          <div>
            <div className="text-ink-subtle">7-Day Precip</div>
            <div className="font-mono text-ink-muted">{pred.feature_importance?.forecast_precip_7d ? 'Included' : 'N/A'}</div>
          </div>
          <div>
            <div className="text-ink-subtle">Max Temp</div>
            <div className="font-mono text-ink-muted">{pred.feature_importance?.forecast_temp_max ? 'Included' : 'N/A'}</div>
          </div>
          <div>
            <div className="text-ink-subtle">Humidity</div>
            <div className="font-mono text-ink-muted">{pred.feature_importance?.forecast_humidity_mean ? 'Included' : 'N/A'}</div>
          </div>
        </div>
      </div>

      {topFeatures.length > 0 && (
        <div>
          <div className="mb-1 text-ink-subtle">Top Features</div>
          <div className="space-y-1">
            {topFeatures.map(([name, importance]) => (
              <div key={name} className="flex items-center gap-2">
                <div className="h-1.5 rounded-full bg-brand-soft" style={{ width: `${importance * 100}%`, minWidth: 4 }} />
                <span className="text-ink-muted">{name}</span>
                <span className="ml-auto text-ink-subtle">{(importance * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-ink-subtle">
        Model: {pred.model_version} | {pred.model_status} | {pred.prediction_date}
      </div>
    </div>
  )
}

function ModelHealthBar({ assetMeta }: { assetMeta: any }) {
  const models = assetMeta.models || {}
  const entries = Object.entries(models).filter(([, v]: [string, any]) => v.status === 'SUCCESS')

  if (entries.length === 0) return null

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-2 text-[10px] font-semibold uppercase text-ink-subtle">Trained Models</div>
      <div className="space-y-1">
        {entries.map(([key, m]: [string, any]) => (
          <div key={key} className="flex items-center justify-between rounded bg-surface-alt px-2 py-1 text-[10px]">
            <span className="text-ink-muted">{m.model_type} ({m.horizon}d)</span>
            <div className="flex items-center gap-2">
              <span className="text-ink-subtle">R²={m.r2?.toFixed(3) ?? '—'}</span>
              <span className="text-ink-subtle">MAE={m.mae?.toFixed(2) ?? '—'}</span>
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
          <h3 className="mb-3 text-sm font-semibold text-ink-muted">XGBoost Next-Month Forecasts</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {xgbPreds.map(pred => (
              <WAIPredictionCard key={pred.id} pred={pred} />
            ))}
          </div>
        </div>
      )}

      {otherPreds.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-ink-muted">Historical Predictions</h3>
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
          <span className="font-bold text-ink">Region {pred.region_id}</span>
          <Badge tone={tone}>{pred.predicted_severity}</Badge>
        </div>
        <div className="space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-ink-subtle">WAI Score</span>
            <span className="font-mono font-bold text-ink">{pred.predicted_wai_score.toFixed(1)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-subtle">Confidence</span>
            <span className="font-mono text-ink-muted">{(pred.confidence * 100).toFixed(0)}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-subtle">Target</span>
            <span className="text-ink-muted">{pred.target_week_start_date}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-subtle">Model</span>
            <span className="text-ink-muted">{pred.model_version}</span>
          </div>
        </div>
      </div>
    </Card>
  )
}
