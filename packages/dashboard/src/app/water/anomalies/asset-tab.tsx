// packages/dashboard/src/app/water/anomalies/asset-tab.tsx
// Asset-level anomaly tab: real IsolationForest scores over a window.
'use client'

import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ReferenceLine,
} from 'recharts'
import { Activity, Gauge, Cpu, ListFilter, AlertTriangle } from 'lucide-react'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import type { MLAnomalyPoint, MLAnomalyHistory } from '@/features/water/types'
import { fmtNumber, fmtDateTime, timeAgo } from '@/lib/format'

const GRID = '#e2e8f0'
const AXIS = '#64748b'
const TOOLTIP_STYLE = {
  contentStyle: { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 },
  labelStyle: { color: '#94a3b8' },
}

const SEV_TONE: Record<string, string> = {
  HIGH: 'bg-crit-soft text-crit border-crit/25',
  MODERATE: 'bg-warn-soft text-warn border-warn/25',
  LOW: 'bg-brand-soft text-brand border-brand/25',
}

const SEV_FILL: Record<string, string> = {
  HIGH: '#A81E1E',
  MODERATE: '#A8470E',
  LOW: '#38bdf8',
}

const RAIL_SEVERITY: Record<string, string> = {
  HIGH: 'Critical',
  MODERATE: 'Severe',
  LOW: 'Stressed',
}

const WINDOWS: Array<[number, string]> = [[7, '7d'], [30, '30d'], [90, '90d']]
const SEV_FILTERS = ['ALL', 'HIGH', 'MODERATE', 'LOW'] as const
type SevFilter = (typeof SEV_FILTERS)[number]

function SevPill({ severity }: { severity: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${SEV_TONE[severity] ?? SEV_TONE.LOW}`}>
      {severity}
    </span>
  )
}

function ScoreDot(props: { cx?: number; cy?: number; payload?: MLAnomalyPoint }) {
  const p = props.payload
  if (!p) return null
  if (!p.is_anomaly) return <circle cx={props.cx} cy={props.cy} r="1.5" fill="#38bdf8" />
  return (
    <circle
      cx={props.cx}
      cy={props.cy}
      r="3.5"
      fill={SEV_FILL[p.severity] ?? '#38bdf8'}
      stroke="#fff"
      strokeWidth="1"
    />
  )
}

export function AssetAnomalyTab() {
  const [windowDays, setWindowDays] = useState(30)
  const [assetId, setAssetId] = useState<number | null>(null)
  const [sevFilter, setSevFilter] = useState<SevFilter>('ALL')

  const summary = useQuery({
    queryKey: ['ml-anomaly-summary', windowDays],
    queryFn: () => waterApi.getMLAnomalySummary(windowDays),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const withModels = useMemo(
    () => (summary.data?.assets ?? []).filter((a) => a.has_model),
    [summary.data],
  )

  useEffect(() => {
    if (assetId != null || !withModels.length) return
    let pick = withModels[0]
    for (const a of withModels) {
      const t = a.latest_anomaly?.observed_at
      if (t && (!pick.latest_anomaly || t > pick.latest_anomaly.observed_at)) pick = a
    }
    setAssetId(pick.asset_id)
  }, [withModels, assetId])

  const history = useQuery({
    queryKey: ['ml-anomaly-history', assetId, windowDays],
    queryFn: () => waterApi.getMLAnomalyHistory(assetId as number, windowDays),
    enabled: assetId != null,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  if (summary.isPending) return <Spinner label="Loading anomaly summary" />
  if (summary.isError) return <ErrorState onRetry={() => summary.refetch()} />
  if (!withModels.length) {
    return (
      <EmptyState
        title="No detectors trained"
        message="Train the Isolation Forest detectors with the Retrain button above to score observations."
      />
    )
  }

  const data = summary.data
  const flaggedHigh = withModels.filter((a) => a.worst_severity === 'HIGH').length
  const latest = withModels
    .filter((a) => a.latest_anomaly)
    .map((a) => ({ asset: a, point: a.latest_anomaly as NonNullable<typeof a.latest_anomaly> }))
    .sort((a, b) => b.point.observed_at.localeCompare(a.point.observed_at))[0]

  const points = history.data?.points ?? []
  const flagged = points.filter((p) => p.is_anomaly)

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Detectors trained"
          value={`${data.assets_with_models} / ${data.assets_total}`}
          detail="Isolation Forest models on registry assets"
          icon={Cpu}
        />
        <KpiCard
          label="Anomalies flagged"
          value={data.total_anomalies}
          detail={`Across all assets · last ${data.window_days} days`}
          icon={AlertTriangle}
          accent={data.total_anomalies > 0 ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'}
        />
        <KpiCard
          label="Assets in HIGH"
          value={flaggedHigh}
          detail="Worst band reached in window"
          icon={Activity}
          severity={flaggedHigh > 0 ? 'Critical' : undefined}
        />
        <KpiCard
          label="Latest anomaly"
          value={latest ? latest.asset.asset_name : '—'}
          detail={
            latest ? (
              <span className="flex items-center gap-2">
                <SevPill severity={latest.point.severity} />
                {fmtDateTime(latest.point.observed_at)}
              </span>
            ) : (
              'No anomalies in window'
            )
          }
          icon={Gauge}
          severity={latest ? RAIL_SEVERITY[latest.point.severity] : undefined}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-line bg-surface p-0.5">
          {WINDOWS.map(([days, label]) => (
            <button
              key={days}
              type="button"
              onClick={() => setWindowDays(days)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                windowDays === days ? 'bg-brand-soft text-brand' : 'text-ink-muted hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={assetId ?? ''}
          onChange={(e) => setAssetId(Number(e.target.value))}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-brand focus:outline-none"
          aria-label="Select asset"
        >
          {withModels.map((a) => (
            <option key={a.asset_id} value={a.asset_id}>
              {a.asset_name} ({a.anomaly_count} flagged)
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1.5">
          <ListFilter className="h-3.5 w-3.5 text-ink-subtle" />
          <span className="text-[11px] uppercase tracking-wider text-ink-subtle">Feed severity</span>
          {SEV_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSevFilter(s)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                sevFilter === s ? 'bg-brand-soft text-brand' : 'text-ink-muted hover:text-ink'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Anomaly Score Trend"
            subtitle={`Decision score per observation · last ${windowDays} days · flagged below 0`}
            icon={<Activity className="h-5 w-5" />}
            accent="bg-brand-soft text-brand"
            action={
              history.data ? (
                <div className="flex items-center gap-2">
                  <Badge tone={history.data.anomaly_count > 0 ? 'crit' : 'ok'}>
                    {history.data.anomaly_count} flagged
                  </Badge>
                  <Badge tone="slate">{history.data.model_version}</Badge>
                </div>
              ) : undefined
            }
          />
          <CardBody>
            {history.isPending ? (
              <Spinner />
            ) : history.isError ? (
              <ErrorState onRetry={() => history.refetch()} />
            ) : points.length === 0 ? (
              <EmptyState title="No observations" message="No readings for this asset in the selected window." />
            ) : (
              <>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={points.map((p) => ({ ...p, t: p.observed_at.slice(5, 10) }))}
                      margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient id="score-fill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                      <XAxis dataKey="t" tick={{ fontSize: 9, fill: AXIS }} interval="preserveStartEnd" />
                      <YAxis domain={['auto', 'auto']} tick={{ fontSize: 9, fill: AXIS }} width={44} />
                      <RTooltip
                        {...TOOLTIP_STYLE}
                        formatter={(v: number) => [v.toFixed(3), 'Score']}
                        labelFormatter={() => ''}
                        content={({ payload, label }) => {
                          if (!payload?.length) return null
                          const row = payload[0].payload as MLAnomalyPoint
                          return (
                            <div className="rounded-lg border border-slate-700 bg-[#0f172a] px-3 py-2 text-[11px] text-slate-300">
                              <p className="font-medium text-white">{fmtDateTime(row.observed_at)}</p>
                              <p className="mt-1 font-mono">Score {row.anomaly_score.toFixed(3)}</p>
                              <p className={row.is_anomaly ? 'text-red-400' : 'text-slate-400'}>
                                {row.is_anomaly ? `Flagged · ${row.severity}` : 'Normal'}
                              </p>
                              <p className="mt-0.5 font-mono">
                                Level {fmtNumber(row.level_ft)} ft · In {fmtNumber(row.inflow_cusecs, 0)}
                              </p>
                            </div>
                          )
                        }}
                      />
                      <ReferenceLine y={0} stroke={AXIS} strokeDasharray="4 4" label={{ value: 'flag boundary', fontSize: 9, fill: AXIS, position: 'insideRight' }} />
                      <ReferenceLine y={-0.15} stroke={SEV_FILL.MODERATE} strokeDasharray="4 4" label={{ value: 'MODERATE', fontSize: 9, fill: AXIS, position: 'insideRight' }} />
                      <ReferenceLine y={-0.3} stroke={SEV_FILL.HIGH} strokeDasharray="4 4" label={{ value: 'HIGH', fontSize: 9, fill: AXIS, position: 'insideRight' }} />
                      <Area
                        type="monotone"
                        dataKey="anomaly_score"
                        stroke="#38bdf8"
                        strokeWidth={1.8}
                        fill="url(#score-fill)"
                        name="Score"
                        dot={(props: { cx?: number; cy?: number; payload?: MLAnomalyPoint }) => <ScoreDot {...props} />}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-ink-subtle">
                  <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#A81E1E] align-middle" /> HIGH (score &lt; −0.30)</span>
                  <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#A8470E] align-middle" /> MODERATE (&lt; −0.15)</span>
                  <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#38bdf8] align-middle" /> Normal (≥ 0)</span>
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <ModelCard
          history={history.data}
          pending={history.isPending}
          error={history.isError}
          onRetry={() => history.refetch()}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Observed Level with Anomaly Markers"
            subtitle="Raw readings — flagged points highlighted in severity colour"
            icon={<Gauge className="h-5 w-5" />}
            accent="bg-brand-soft text-brand"
          />
          <CardBody>
            {history.isPending ? (
              <Spinner />
            ) : history.isError ? (
              <ErrorState onRetry={() => history.refetch()} />
            ) : points.length === 0 ? (
              <EmptyState title="No observations" message="No readings in the selected window." />
            ) : (
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={points.map((p) => ({ ...p, t: p.observed_at.slice(5, 10) }))}
                    margin={{ top: 5, right: 10, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                    <XAxis dataKey="t" tick={{ fontSize: 9, fill: AXIS }} interval="preserveStartEnd" />
                    <YAxis domain={['auto', 'auto']} tick={{ fontSize: 9, fill: AXIS }} width={44} />
                    <RTooltip
                      {...TOOLTIP_STYLE}
                      content={({ payload, label }) => {
                        if (!payload?.length) return null
                        const row = payload[0].payload as MLAnomalyPoint
                        return (
                          <div className="rounded-lg border border-slate-700 bg-[#0f172a] px-3 py-2 text-[11px] text-slate-300">
                            <p className="font-medium text-white">{label}</p>
                            <p className="mt-1 font-mono">Level {fmtNumber(row.level_ft)} ft</p>
                            <p className="font-mono">In {fmtNumber(row.inflow_cusecs, 0)} · Out {fmtNumber(row.outflow_cusecs, 0)}</p>
                            {row.is_anomaly && <p className="mt-0.5 text-red-400">Flagged {row.severity}</p>}
                          </div>
                        )
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="level_ft"
                      stroke="#38bdf8"
                      strokeWidth={1.8}
                      dot={(props: { cx?: number; cy?: number; payload?: MLAnomalyPoint }) => <ScoreDot {...props} />}
                      name="Level (ft)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardBody>
        </Card>

        <FeatureFrequencyCard points={flagged} pending={history.isPending} error={history.isError} />
      </div>

      <Card>
        <CardHeader
          title="Anomaly Feed"
          subtitle={`Flagged observations · ${sevFilter === 'ALL' ? 'all severities' : sevFilter} · newest first (max 50)`}
          icon={<ListFilter className="h-5 w-5" />}
          accent={flagged.length > 0 ? 'bg-crit-soft text-crit' : 'bg-ok-soft text-ok'}
        />
        <CardBody className="p-0">
          {history.isPending ? (
            <div className="p-4"><Spinner /></div>
          ) : history.isError ? (
            <div className="p-4"><ErrorState onRetry={() => history.refetch()} /></div>
          ) : (
            <FeedTable points={points} sevFilter={sevFilter} />
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function ModelCard({
  history,
  pending,
  error,
  onRetry,
}: {
  history?: MLAnomalyHistory
  pending: boolean
  error: boolean
  onRetry: () => void
}) {
  if (pending) return <Card><CardBody><Spinner /></CardBody></Card>
  if (error || !history) {
    return (
      <Card>
        <CardHeader title="Model" icon={<Cpu className="h-5 w-5" />} accent="bg-brand-soft text-brand" />
        <CardBody><ErrorState onRetry={onRetry} /></CardBody>
      </Card>
    )
  }

  const trainedAge = history.trained_at ? Date.now() - new Date(history.trained_at + 'Z').getTime() : null
  const stale = trainedAge != null && trainedAge > 7 * 24 * 3600 * 1000

  return (
    <Card>
      <CardHeader
        title="Model"
        subtitle="Detector for the selected asset"
        icon={<Cpu className="h-5 w-5" />}
        accent="bg-brand-soft text-brand"
        action={<Badge tone="info">{history.model_version}</Badge>}
      />
      <CardBody className="space-y-3 text-xs">
        <Row label="Status">
          <Badge tone="amber">{history.model_status}</Badge>
        </Row>
        <Row label="Trained">
          <span className="text-ink">{history.trained_at ? fmtDateTime(history.trained_at) : '—'}</span>
        </Row>
        <Row label="Training samples">
          <span className="font-mono text-ink">{history.training_samples ?? '—'}</span>
        </Row>
        <Row label="Contamination">
          <span className="font-mono text-ink">{history.contamination != null ? history.contamination.toFixed(2) : '—'}</span>
        </Row>
        <Row label="Scored in window">
          <span className="font-mono text-ink">
            {history.scored_count} obs · {history.anomaly_count} flagged
          </span>
        </Row>
        <div className="rounded-lg border border-line bg-surface-alt p-3 leading-5 text-ink-muted">
          A score below 0 flags the observation. Bands: HIGH &lt; −0.30, MODERATE &lt; −0.15.
          Advisory only — review the raw readings before acting.
        </div>
        {stale && (
          <div className="rounded-lg border border-warn/25 bg-warn-soft p-3 leading-5 text-warn">
            Model last trained {timeAgo(history.trained_at)} — consider retraining from the header.
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-subtle">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  )
}

function FeatureFrequencyCard({
  points,
  pending,
  error,
}: {
  points: MLAnomalyPoint[]
  pending: boolean
  error: boolean
}) {
  const freq = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of points) {
      for (const f of p.anomaly_features) m.set(f, (m.get(f) ?? 0) + 1)
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6)
  }, [points])

  const max = freq.length ? freq[0][1] : 1

  return (
    <Card>
      <CardHeader
        title="Contributing Features"
        subtitle="What deviated most across flagged points"
        icon={<ListFilter className="h-5 w-5" />}
        accent="bg-brand-soft text-brand"
      />
      <CardBody>
        {pending ? (
          <Spinner />
        ) : error ? (
          <p className="text-xs text-ink-subtle">Unavailable.</p>
        ) : !freq.length ? (
          <EmptyState title="No flagged points" message="Nothing triggered in this window." />
        ) : (
          <div className="space-y-3">
            {freq.map(([name, count]) => (
              <div key={name}>
                <div className="mb-1 flex items-center justify-between text-[11px]">
                  <span className="text-ink-muted">{name}</span>
                  <span className="font-mono text-ink">{count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-sunken">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${(count / max) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function FeedTable({ points, sevFilter }: { points: MLAnomalyPoint[]; sevFilter: SevFilter }) {
  const rows = points
    .filter((p) => p.is_anomaly && (sevFilter === 'ALL' || p.severity === sevFilter))
    .sort((a, b) => b.observed_at.localeCompare(a.observed_at))
    .slice(0, 50)

  if (!rows.length) {
    return (
      <div className="p-6">
        <EmptyState
          title="No anomalies"
          message={sevFilter === 'ALL' ? 'No flagged observations in this window.' : `No ${sevFilter} anomalies in this window.`}
        />
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-surface text-[11px] uppercase tracking-wider text-ink-subtle">
          <tr>
            <Th>Observed</Th>
            <Th>Score</Th>
            <Th>Severity</Th>
            <Th>Contributing features</Th>
            <Th className="text-right">Level (ft)</Th>
            <Th className="text-right">Inflow</Th>
            <Th className="text-right">Outflow</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((p) => (
            <tr key={p.observed_at} className="text-ink-muted hover:bg-surface-alt">
              <Td className="whitespace-nowrap">{fmtDateTime(p.observed_at)}</Td>
              <Td className="font-mono tabular-nums text-ink">{p.anomaly_score.toFixed(3)}</Td>
              <Td><SevPill severity={p.severity} /></Td>
              <Td>
                <div className="flex flex-wrap gap-1">
                  {p.anomaly_features.length ? (
                    p.anomaly_features.map((f) => (
                      <span key={f} className="rounded-full border border-warn/25 bg-warn-soft px-2 py-0.5 text-[10px] text-warn">
                        {f}
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] text-ink-subtle">—</span>
                  )}
                </div>
              </Td>
              <Td className="text-right font-mono tabular-nums text-ink">{fmtNumber(p.level_ft)}</Td>
              <Td className="text-right font-mono tabular-nums">{fmtNumber(p.inflow_cusecs, 0)}</Td>
              <Td className="text-right font-mono tabular-nums">{fmtNumber(p.outflow_cusecs, 0)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={`px-4 py-2.5 font-medium ${className ?? ''}`}>{children}</th>
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-2.5 text-xs ${className ?? ''}`}>{children}</td>
}
