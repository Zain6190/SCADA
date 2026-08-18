// packages/dashboard/src/app/water/predictions/page.tsx
// AquaVision ML Flood Predictions - XGBoost 7-day ahead forecasts per asset.
// Phase 2B: Updated for renamed fields and EXPERIMENTAL labels.
'use client'

import { useState } from 'react'
import { Cpu, RefreshCw, AlertTriangle, FlaskConical } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import type { MLPrediction } from '@/features/water/types'
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

const ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]

export default function PredictionsPage() {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<number | null>(null)

  const trainMutation = useMutation({
    mutationFn: () => waterApi.triggerMLTrain([7]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ml-predictions'] }),
  })

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Flood Predictions"
          description="XGBoost 7-day ahead inflow/level forecasts per asset. Models retrained weekly."
          icon={<Cpu className="h-6 w-6" />}
          badge={
            <div className="flex items-center gap-2">
              <Badge tone="amber">
                <FlaskConical className="mr-1 inline h-3 w-3" />
                EXPERIMENTAL
              </Badge>
              <button
                onClick={() => trainMutation.mutate()}
                disabled={trainMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-500/15 px-3 py-1.5 text-xs font-medium text-violet-300 border border-violet-500/30 hover:bg-violet-500/25 transition disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${trainMutation.isPending ? 'animate-spin' : ''}`} />
                {trainMutation.isPending ? 'Training...' : 'Retrain Models'}
              </button>
            </div>
          }
        />

        {trainMutation.isSuccess && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            Training complete: {trainMutation.data.models_trained} models trained.
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ASSET_IDS.map((id) => (
            <PredictionCard
              key={id}
              assetId={id}
              isExpanded={expanded === id}
              onToggle={() => setExpanded(expanded === id ? null : id)}
            />
          ))}
        </div>
      </div>
    </AppShell>
  )
}

function PredictionCard({
  assetId,
  isExpanded,
  onToggle,
}: {
  assetId: number
  isExpanded: boolean
  onToggle: () => void
}) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['ml-predictions', assetId],
    queryFn: () => waterApi.getMLPredictions(assetId, '7'),
    staleTime: 5 * 60_000,
  })

  const pred = data?.[0]

  return (
    <Card>
      <button
        onClick={onToggle}
        className="w-full text-left"
      >
        <CardHeader
          title={pred?.asset_name ?? `Asset ${assetId}`}
          subtitle={
            isPending
              ? 'Loading...'
              : isError
                ? 'Failed to load'
                : pred
                  ? `${pred.horizon_days}-day forecast`
                  : 'No model trained'
          }
          icon={
            pred ? (
              <div className={`h-3 w-3 rounded-full ${RISK_DOT[pred.risk_level] ?? 'bg-slate-500'}`} />
            ) : (
              <Cpu className="h-5 w-5 text-slate-500" />
            )
          }
          accent={
            pred
              ? RISK_COLORS[pred.risk_level] ?? 'bg-slate-500/15 text-slate-300'
              : 'bg-slate-500/15 text-slate-500'
          }
        />
      </button>

      {isExpanded && (
        <CardBody className="border-t border-slate-800/70 pt-4">
          {isPending ? (
            <Spinner />
          ) : isError ? (
            <ErrorState onRetry={() => refetch()} />
          ) : !pred ? (
            <EmptyState title="No model" message="Train models first." />
          ) : (
            <PredictionDetails pred={pred} />
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

  return (
    <div className="space-y-3 text-xs">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-slate-500">Predicted Value</div>
          <div className="text-lg font-bold text-slate-100">
            {pred.predicted_level_ft != null ? pred.predicted_level_ft.toLocaleString() : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Prediction Interval</div>
          <div className="font-medium text-slate-300">
            {pred.lower_bound != null ? pred.lower_bound.toLocaleString() : '—'}
            {' — '}
            {pred.upper_bound != null ? pred.upper_bound.toLocaleString() : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500">Risk Score</div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-100">{pred.risk_score}/100</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${RISK_COLORS[pred.risk_level] ?? ''}`}>
              {pred.risk_level}
            </span>
          </div>
        </div>
        <div>
          <div className="text-slate-500">Status</div>
          <Badge tone="amber">
            <FlaskConical className="mr-1 inline h-3 w-3" />
            {pred.model_status}
          </Badge>
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
        Model: {pred.model_version} | {pred.model_status} | {pred.prediction_date}
      </div>
    </div>
  )
}
