// packages/dashboard/src/app/water/anomalies/page.tsx
// AquaVision Anomaly Detection - Isolation Forest unsupervised anomalies per asset.
// Phase 2B: Added EXPERIMENTAL labels.
'use client'

import { useState } from 'react'
import { ShieldAlert, RefreshCw, FlaskConical, ChevronDown, ChevronUp } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import type { MLAnomaly } from '@/features/water/types'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const SEVERITY_COLORS: Record<string, string> = {
  HIGH: 'bg-red-500/15 text-red-300 border border-red-500/30',
  MODERATE: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
  LOW: 'bg-sky-500/15 text-sky-300 border border-sky-500/30',
  NORMAL: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
}

const SEVERITY_DOT: Record<string, string> = {
  HIGH: 'bg-red-400',
  MODERATE: 'bg-amber-400',
  LOW: 'bg-sky-400',
  NORMAL: 'bg-emerald-400',
}

const ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]

export default function AnomaliesPage() {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<number | null>(null)

  const trainMutation = useMutation({
    mutationFn: () => waterApi.trainAnomalyDetectors(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ml-anomalies'] }),
  })

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Anomaly Detection"
          description="Isolation Forest unsupervised anomaly detection per asset. Detects unusual level/inflow/outflow patterns."
          icon={<ShieldAlert className="h-6 w-6" />}
          badge={
            <div className="flex items-center gap-2">
              <Badge tone="amber">
                <FlaskConical className="mr-1 inline h-3 w-3" />
                EXPERIMENTAL
              </Badge>
              <button
                onClick={() => trainMutation.mutate()}
                disabled={trainMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-medium text-red-300 border border-red-500/30 hover:bg-red-500/25 transition disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${trainMutation.isPending ? 'animate-spin' : ''}`} />
                {trainMutation.isPending ? 'Training...' : 'Retrain Detectors'}
              </button>
            </div>
          }
        />

        {trainMutation.isSuccess && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            Training complete: {trainMutation.data.models_trained} detectors trained.
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ASSET_IDS.map((id) => (
            <AnomalyCard
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

function AnomalyCard({
  assetId,
  isExpanded,
  onToggle,
}: {
  assetId: number
  isExpanded: boolean
  onToggle: () => void
}) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['ml-anomalies', assetId],
    queryFn: () => waterApi.getMLAnomalies(assetId, 5),
    staleTime: 5 * 60_000,
  })

  const anomalies = data ?? []
  const hasAnomalies = anomalies.length > 0
  const worstSeverity = anomalies[0]?.severity ?? 'NORMAL'

  return (
    <Card>
      <button onClick={onToggle} className="w-full text-left">
        <CardHeader
          title={anomalies[0]?.asset_name ?? `Asset ${assetId}`}
          subtitle={
            isPending
              ? 'Loading...'
              : isError
                ? 'Failed to load'
                : hasAnomalies
                  ? `${anomalies.length} anomalies detected`
                  : 'No anomalies found'
          }
          icon={
            hasAnomalies ? (
              <div className={`h-3 w-3 rounded-full ${SEVERITY_DOT[worstSeverity]}`} />
            ) : (
              <ShieldAlert className="h-5 w-5 text-slate-500" />
            )
          }
          accent={SEVERITY_COLORS[worstSeverity] ?? 'bg-slate-500/15 text-slate-500'}
        />
      </button>

      {isExpanded && (
        <CardBody className="border-t border-slate-800/70 pt-4">
          {isPending ? (
            <Spinner />
          ) : isError ? (
            <ErrorState onRetry={() => refetch()} />
          ) : anomalies.length === 0 ? (
            <EmptyState title="No anomalies" message="No unusual patterns detected." />
          ) : (
            <div className="space-y-3">
              {anomalies.map((a, i) => (
                <AnomalyRow key={i} anomaly={a} />
              ))}
            </div>
          )}
        </CardBody>
      )}
    </Card>
  )
}

function AnomalyRow({ anomaly }: { anomaly: MLAnomaly }) {
  const [open, setOpen] = useState(false)
  const dateStr = anomaly.observed_at.split('T')[0]

  return (
    <div className="rounded-xl border border-slate-800/70 bg-slate-900/50 p-3">
      <button onClick={() => setOpen(!open)} className="w-full text-left">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${SEVERITY_COLORS[anomaly.severity]}`}>
              {anomaly.severity}
            </span>
            <span className="text-xs text-slate-300">{dateStr}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">score: {anomaly.anomaly_score.toFixed(3)}</span>
            {open ? <ChevronUp className="h-3.5 w-3.5 text-slate-500" /> : <ChevronDown className="h-3.5 w-3.5 text-slate-500" />}
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-3 space-y-2 text-xs">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <div className="text-slate-500">Level</div>
              <div className="font-medium text-slate-200">{anomaly.details.level_ft.toLocaleString()} ft</div>
            </div>
            <div>
              <div className="text-slate-500">Inflow</div>
              <div className="font-medium text-slate-200">{anomaly.details.inflow_cusecs.toLocaleString()} cusecs</div>
            </div>
            <div>
              <div className="text-slate-500">Outflow</div>
              <div className="font-medium text-slate-200">{anomaly.details.outflow_cusecs.toLocaleString()} cusecs</div>
            </div>
          </div>

          {anomaly.anomaly_features.length > 0 && (
            <div>
              <div className="text-slate-500 mb-1">Triggering Features</div>
              <div className="flex flex-wrap gap-1">
                {anomaly.anomaly_features.map((f) => (
                  <span key={f} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300 border border-amber-500/20">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="text-slate-600">
            Model: {anomaly.model_version} | {anomaly.model_status}
          </div>
        </div>
      )}
    </div>
  )
}
