'use client'

// packages/dashboard/src/features/water/overview-charts.tsx
// Overview analytics cards: national WAI trend, per-asset daily observations,
// and the forecast severity distribution. Recharts only, no new deps.
import { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ReferenceLine,
} from 'recharts'
import { Activity, Gauge, TrendingUp, TrendingDown } from 'lucide-react'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import {
  useWaterIndicators,
  useOperationalAssets,
  useAssetObservations,
} from '@/features/water/hooks'
import {
  SEVERITY_STYLES,
  SEVERITY_ORDER,
  type SeverityLevel,
} from '@/lib/severity'
import type { PredictionVM } from '@/features/water/types'
import { fmtDate, fmtNumber } from '@/lib/format'

const AQUA = 'bg-brand-soft text-brand'
const GRID = '#e2e8f0'
const AXIS = '#64748b'
const TOOLTIP_STYLE = {
  contentStyle: { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 },
  labelStyle: { color: '#94a3b8' },
}

export function WaiTrendCard() {
  const indicators = useWaterIndicators({ limit: 1000 })

  const data = useMemo(() => {
    const byWeek = new Map<string, { sum: number; n: number }>()
    for (const r of indicators.data ?? []) {
      if (r.waiScore == null) continue
      const cur = byWeek.get(r.weekStart) ?? { sum: 0, n: 0 }
      cur.sum += Number(r.waiScore)
      cur.n += 1
      byWeek.set(r.weekStart, cur)
    }
    return Array.from(byWeek.entries())
      .map(([week, { sum, n }]) => ({ week, wai: Math.round((sum / n) * 10) / 10 }))
      .sort((a, b) => a.week.localeCompare(b.week))
      .slice(-12)
  }, [indicators.data])

  const latest = data.length ? data[data.length - 1] : null
  const prev = data.length > 1 ? data[data.length - 2] : null
  const delta = latest && prev ? Math.round((latest.wai - prev.wai) * 10) / 10 : null

  return (
    <Card>
      <CardHeader
        title="WAI Trend"
        subtitle="National mean water availability — last 12 periods"
        icon={<Activity className="h-5 w-5" />}
        accent={AQUA}
        action={
          latest ? (
            <div className="flex items-center gap-2">
              <Badge tone="brand">
                {fmtNumber(latest.wai)} / 100
              </Badge>
              {delta != null && delta !== 0 && (
                <span
                  className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${
                    delta > 0 ? 'text-ok' : 'text-crit'
                  }`}
                >
                  {delta > 0 ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : (
                    <TrendingDown className="h-3 w-3" />
                  )}
                  {delta > 0 ? '+' : ''}
                  {delta}
                </span>
              )}
            </div>
          ) : undefined
        }
      />
      <CardBody>
        {indicators.isPending ? (
          <Spinner />
        ) : indicators.isError ? (
          <ErrorState onRetry={() => indicators.refetch()} />
        ) : data.length ? (
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="wai-trend-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="week" tickFormatter={(v: string) => v.slice(2)} tick={{ fontSize: 9, fill: AXIS }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: AXIS }} width={28} />
                <RTooltip {...TOOLTIP_STYLE} formatter={(v: any) => [`${v} / 100`, 'Mean WAI']} />
                <Area
                  type="monotone"
                  dataKey="wai"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  fill="url(#wai-trend-fill)"
                  name="Mean WAI"
                  dot={{ r: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyState title="No WAI history" message="Run the WAI pipeline to populate indicators." />
        )}
      </CardBody>
    </Card>
  )
}

export function DailyObservationsCard() {
  const assets = useOperationalAssets()
  const [assetId, setAssetId] = useState<number | null>(null)

  useEffect(() => {
    if (assetId != null || !assets.data?.length) return
    const withLevel = assets.data.find((a) => a.current_level_ft != null)
    setAssetId((withLevel ?? assets.data[0]).id)
  }, [assets.data, assetId])

  const obs = useAssetObservations(assetId, 30)
  const asset = assets.data?.find((a) => a.id === assetId) ?? null

  const points = useMemo(() => {
    const rows = (obs.data ?? [])
      .slice()
      .sort((a, b) => a.observed_at.localeCompare(b.observed_at))
    return rows.map((r) => ({
      day: r.observed_at.slice(5, 10),
      level: r.water_level_ft ?? null,
      inflow: r.inflow_cusecs ?? null,
      outflow: r.outflow_cusecs ?? null,
    }))
  }, [obs.data])

  const hasLevel = points.some((p) => p.level != null)
  const hasFlow = points.some((p) => p.inflow != null || p.outflow != null)

  return (
    <Card>
      <CardHeader
        title="Daily Observations"
        subtitle="Last 30 days from IRSA / FFD bulletins"
        icon={<Gauge className="h-5 w-5" />}
        accent={AQUA}
        action={
          assets.data?.length ? (
            <select
              value={assetId ?? ''}
              onChange={(e) => setAssetId(Number(e.target.value))}
              className="rounded-lg border border-line bg-canvas px-2 py-1 text-xs text-ink"
              aria-label="Select asset"
            >
              {assets.data.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.canonical_name || `Asset ${a.id}`}
                </option>
              ))}
            </select>
          ) : undefined
        }
      />
      <CardBody>
        {assets.isPending || obs.isPending ? (
          <Spinner />
        ) : assets.isError ? (
          <ErrorState onRetry={() => assets.refetch()} />
        ) : obs.isError ? (
          <ErrorState onRetry={() => obs.refetch()} />
        ) : !points.length ? (
          <EmptyState title="No readings" message="No observations for this asset in the last 30 days." />
        ) : (
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              {hasLevel ? (
                <LineChart data={points} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: AXIS }} />
                  <YAxis tick={{ fontSize: 9, fill: AXIS }} width={36} />
                  <RTooltip {...TOOLTIP_STYLE} formatter={(v: any, name: any) => [fmtNumber(v), name]} />
                  {asset?.warning_level_ft != null && (
                    <ReferenceLine
                      y={asset.warning_level_ft}
                      stroke="#d97706"
                      strokeDasharray="4 4"
                      label={{ value: 'Warning', fontSize: 9, fill: '#d97706', position: 'insideRight' }}
                    />
                  )}
                  {asset?.danger_level_ft != null && (
                    <ReferenceLine
                      y={asset.danger_level_ft}
                      stroke="#dc2626"
                      strokeDasharray="4 4"
                      label={{ value: 'Danger', fontSize: 9, fill: '#dc2626', position: 'insideRight' }}
                    />
                  )}
                  <Line type="monotone" dataKey="level" stroke="#38bdf8" strokeWidth={2} dot={false} name="Level (ft)" />
                </LineChart>
              ) : hasFlow ? (
                <LineChart data={points} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: AXIS }} />
                  <YAxis tick={{ fontSize: 9, fill: AXIS }} width={44} />
                  <RTooltip {...TOOLTIP_STYLE} formatter={(v: any, name: any) => [fmtNumber(v), name]} />
                  <Line type="monotone" dataKey="inflow" stroke="#38bdf8" strokeWidth={2} dot={false} name="Inflow (cusecs)" />
                  <Line type="monotone" dataKey="outflow" stroke="#34d399" strokeWidth={2} dot={false} name="Outflow (cusecs)" />
                </LineChart>
              ) : (
                <LineChart data={points} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: AXIS }} />
                  <YAxis tick={{ fontSize: 9, fill: AXIS }} width={44} />
                  <RTooltip {...TOOLTIP_STYLE} formatter={(v: any, name: any) => [fmtNumber(v), name]} />
                  <Line type="monotone" dataKey="discharge" stroke="#38bdf8" strokeWidth={2} dot={false} name="Discharge (cusecs)" />
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

export function ForecastSeverityBars({ predictions }: { predictions: PredictionVM[] }) {
  const data = useMemo(() => {
    const counts = new Map<SeverityLevel, number>()
    for (const p of predictions) {
      const sev: SeverityLevel = p.predictedSeverity ?? 'Normal'
      counts.set(sev, (counts.get(sev) ?? 0) + 1)
    }
    return SEVERITY_ORDER.filter((s) => counts.has(s)).map((s) => ({
      severity: s,
      count: counts.get(s) ?? 0,
    }))
  }, [predictions])

  if (!data.length) return null

  return (
    <div className="h-24">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <XAxis dataKey="severity" tick={{ fontSize: 9, fill: AXIS }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 9, fill: AXIS }} width={24} />
          <RTooltip {...TOOLTIP_STYLE} cursor={{ fill: 'rgba(148,163,184,0.08)' }} />
          <Bar dataKey="count" name="Regions" radius={[4, 4, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.severity} fill={SEVERITY_STYLES[d.severity].fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
