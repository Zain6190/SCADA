'use client'

// packages/dashboard/src/app/water/regions/[id]/client.tsx
import { useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { MapPin, TrendingUp, Bell, Activity, CloudRain, Sun, Waves } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import Link from 'next/link'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  ComposedChart,
  BarChart,
  Bar,
  Cell,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ReferenceLine,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { ProgressBar } from '@/components/ui/progress'
import {
  useWaterIndicators,
  useWaterPredictions,
  useWaterRegions,
  useWaterMapData,
  useStressAlerts,
} from '@/features/water/hooks'
import { regionNameById } from '@/features/water/mappers'
import { SEVERITY_STYLES } from '@/lib/severity'
import { fmtNumber, fmtDate, fmtPct, titleCase } from '@/lib/format'

const GRID = '#e2e8f0'
const AXIS = '#64748b'
const TOOLTIP_STYLE = {
  contentStyle: { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 },
  labelStyle: { color: '#94a3b8' },
}

const ALERT_LABELS: Record<string, string> = {
  WAI_CRITICAL: 'WAI Critical',
  WAI_SEVERE: 'WAI Severe',
  RAINFALL_DEFICIT: 'Rainfall Deficit',
  HIGH_ET: 'High Evapotranspiration',
}

const fmtMonth = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })

const isOpenStatus = (status: string | null | undefined) =>
  (status ?? '').toUpperCase() !== 'RESOLVED'

type RangeKey = '12' | '24' | 'all'

export function RegionDetailClient() {
  const params = useParams<{ id: string }>()
  const id = Number(params.id)

  const indicatorsQuery = useWaterIndicators({ region_id: id, limit: 200 })
  const predictionsQuery = useWaterPredictions()
  const regionsQuery = useWaterRegions()
  const mapQuery = useWaterMapData()
  const alertsQuery = useStressAlerts({ region_id: id, limit: 50 })

  const [range, setRange] = useState<RangeKey>('24')

  const name = regionNameById(regionsQuery.data ?? [], id)
  const region = (regionsQuery.data ?? []).find((r) => r.id === id)
  const sorted = useMemo(
    () =>
      [...(indicatorsQuery.data ?? [])].sort((a, b) => a.weekStart.localeCompare(b.weekStart)),
    [indicatorsQuery.data],
  )
  const latest = sorted.length ? sorted[sorted.length - 1] : null
  const previous = sorted.length > 1 ? sorted[sorted.length - 2] : null

  const partialWeeks = useMemo(
    () => new Set(sorted.filter((i) => i.qualityStatus === 'PARTIAL').map((i) => i.weekStart)),
    [sorted],
  )

  const chart = useMemo(() => {
    const slice = range === 'all' ? sorted : sorted.slice(-Number(range))
    return slice.map((i) => ({
      key: i.weekStart,
      month: fmtMonth(i.weekStart),
      wai: i.waiScore,
      quality: i.qualityStatus,
    }))
  }, [sorted, range])

  const rank = useMemo(() => {
    const withWai = (mapQuery.data ?? [])
      .filter((f) => f.waiScore != null)
      .sort((a, b) => (a.waiScore ?? 0) - (b.waiScore ?? 0))
    const idx = withWai.findIndex((f) => f.regionId === id)
    return idx >= 0 ? { pos: idx + 1, of: withWai.length } : null
  }, [mapQuery.data, id])

  const openAlerts = (alertsQuery.data ?? []).filter((a) => isOpenStatus(a.status))
  const regionPred = useMemo(() => {
    const rows = (predictionsQuery.data ?? [])
      .filter((p) => p.regionId === id)
      .sort((a, b) => b.targetWeekStart.localeCompare(a.targetWeekStart))
    return rows[0] ?? null
  }, [predictionsQuery.data, id])

  const delta =
    latest?.waiScore != null && previous?.waiScore != null
      ? Math.round((latest.waiScore - previous.waiScore) * 10) / 10
      : null

  const shortHistory = sorted.length > 0 && sorted.length < 12
  const pending = indicatorsQuery.isPending || regionsQuery.isPending
  const failed = indicatorsQuery.isError || regionsQuery.isError

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title={name}
          description={
            <>
              {region ? `${titleCase(region.type)}${region.code ? ` · ${region.code}` : ''} · ` : ''}
              Satellite indicators from Google Earth Engine — CHIRPS rainfall, ERA5-Land
              evapotranspiration, JRC water extent, Sentinel-2 NDVI.
            </>
          }
          icon={<MapPin className="h-6 w-6" />}
          updatedAt={latest?.sourceObservedAt ?? latest?.weekStart ?? null}
          badge={
            <span className="flex flex-wrap items-center gap-2">
              {shortHistory && <Badge tone="slate">Since {fmtMonth(sorted[0].weekStart)}</Badge>}
              <Link href="/water/regions">
                <Badge tone="slate">← All regions</Badge>
              </Link>
            </span>
          }
        />

        {pending ? (
          <Spinner />
        ) : failed ? (
          <ErrorState
            onRetry={() => {
              indicatorsQuery.refetch()
              regionsQuery.refetch()
            }}
          />
        ) : !latest ? (
          <EmptyState
            title="No indicators yet"
            message="This region has no real (GEE) indicator rows. Run the WAI pipeline to populate them."
          />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label="Current WAI"
                value={latest.waiScore != null ? fmtNumber(latest.waiScore) : '—'}
                detail={
                  <span className="flex items-center gap-2">
                    {fmtMonth(latest.weekStart)}
                    {latest.qualityStatus === 'VALID' ? (
                      <Badge tone="ok">VALID</Badge>
                    ) : latest.qualityStatus === 'PARTIAL' ? (
                      <Badge tone="amber">PARTIAL</Badge>
                    ) : latest.qualityStatus === 'STALE' ? (
                      <Badge tone="slate">STALE</Badge>
                    ) : null}
                  </span>
                }
                icon={Activity}
                severity={latest.severity}
              />
              <KpiCard
                label="Month-over-month"
                value={delta != null ? `${delta > 0 ? '+' : ''}${fmtNumber(delta)}` : '—'}
                detail={
                  delta == null || !previous
                    ? 'No prior month'
                    : `vs ${fmtMonth(previous.weekStart)} (${previous.waiScore != null ? fmtNumber(previous.waiScore) : '—'})`
                }
                icon={TrendingUp}
                trend={
                  delta != null && delta !== 0
                    ? { value: delta > 0 ? 'improving' : 'declining', positive: delta > 0 }
                    : undefined
                }
              />
              <KpiCard
                label="National rank"
                value={rank ? `${rank.pos} / ${rank.of}` : '—'}
                detail="Ranked lowest WAI first (1 = most stressed)"
                icon={MapPin}
              />
              <KpiCard
                label="Open alerts"
                value={openAlerts.length}
                detail="Region-scoped WAI stress alerts"
                icon={Bell}
                accent={openAlerts.length > 0 ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'}
              />
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader
                  title="WAI History"
                  subtitle="Monthly water availability index with severity thresholds"
                  icon={<Activity className="h-5 w-5" />}
                  accent="bg-brand-soft text-brand"
                  action={
                    <div className="flex rounded-lg border border-line bg-canvas p-0.5">
                      {(
                        [
                          ['12', '12m'],
                          ['24', '24m'],
                          ['all', 'All'],
                        ] as Array<[RangeKey, string]>
                      ).map(([key, label]) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setRange(key)}
                          className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                            range === key
                              ? 'bg-brand-soft text-brand'
                              : 'text-ink-muted hover:text-ink'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  }
                />
                <CardBody>
                  {chart.length === 0 ? (
                    <EmptyState title="No history" message="No indicator rows for this region." />
                  ) : (
                    <>
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chart} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <defs>
                              <linearGradient id="rg" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4} />
                                <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                            <XAxis
                              dataKey="month"
                              tick={{ fontSize: 10, fill: AXIS }}
                              interval="preserveStartEnd"
                            />
                            <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: AXIS }} width={28} />
                            <RTooltip
                              {...TOOLTIP_STYLE}
                              formatter={(v: number) => [`${fmtNumber(v)} / 100`, 'WAI']}
                              labelFormatter={() => ''}
                              content={({ payload, label }) => {
                                if (!payload?.length) return null
                                const row = payload[0].payload as { quality: string | null }
                                return (
                                  <div className="rounded-lg border border-slate-700 bg-[#0f172a] px-3 py-2 text-[11px] text-slate-300">
                                    <p className="font-medium text-white">{label}</p>
                                    <p className="mt-1 font-mono">WAI {fmtNumber(Number(payload[0].value))} / 100</p>
                                    {row.quality && <p className="mt-0.5">{row.quality}</p>}
                                  </div>
                                )
                              }}
                            />
                            <ReferenceLine
                              y={55}
                              stroke={SEVERITY_STYLES.Stressed.fill}
                              strokeDasharray="4 4"
                              label={{ value: 'Stressed 55', fontSize: 9, fill: AXIS, position: 'insideRight' }}
                            />
                            <ReferenceLine
                              y={40}
                              stroke={SEVERITY_STYLES.Severe.fill}
                              strokeDasharray="4 4"
                              label={{ value: 'Severe 40', fontSize: 9, fill: AXIS, position: 'insideRight' }}
                            />
                            <ReferenceLine
                              y={25}
                              stroke={SEVERITY_STYLES.Critical.fill}
                              strokeDasharray="4 4"
                              label={{ value: 'Critical 25', fontSize: 9, fill: AXIS, position: 'insideRight' }}
                            />
                            <Area
                              type="monotone"
                              dataKey="wai"
                              stroke="#38bdf8"
                              strokeWidth={2}
                              fill="url(#rg)"
                              name="WAI"
                              dot={(props: { cx?: number; cy?: number; payload?: { key: string } }) =>
                                partialWeeks.has(props.payload?.key ?? '') ? (
                                  <circle cx={props.cx} cy={props.cy} r="3.5" fill="#f59e0b" stroke="#fff" strokeWidth="1" />
                                ) : (
                                  <circle cx={props.cx} cy={props.cy} r="2" fill="#38bdf8" />
                                )
                              }
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-ink-subtle">
                        <span>
                          <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#f59e0b] align-middle" />
                          PARTIAL month (inside data-lag window)
                        </span>
                        <span>* PARTIAL rows: {partialWeeks.size}</span>
                        <span>Thresholds: Critical &lt;25 · Severe &lt;40 · Stressed &lt;55</span>
                      </div>
                    </>
                  )}
                </CardBody>
              </Card>

              <div className="space-y-6">
                {regionPred && (
                  <Card>
                    <CardHeader
                      title="Next-month Forecast"
                      subtitle={`Target ${fmtDate(regionPred.targetWeekStart)}`}
                      icon={<TrendingUp className="h-5 w-5" />}
                      accent="bg-brand-soft text-brand"
                      action={<Badge tone="info">{regionPred.modelVersion}</Badge>}
                    />
                    <CardBody>
                      <div className="flex items-center justify-between">
                        <span className="text-lg font-semibold text-ink">
                          WAI {fmtNumber(regionPred.predictedWaiScore)}
                        </span>
                        <SeverityBadge severity={regionPred.predictedSeverity} />
                      </div>
                      {regionPred.lowerBound != null && regionPred.upperBound != null && (
                        <p className="mt-1 font-mono text-xs text-ink-muted">
                          {fmtNumber(regionPred.lowerBound)} – {fmtNumber(regionPred.upperBound)}{' '}
                          <span className="text-ink-subtle">(prediction band)</span>
                        </p>
                      )}
                      <div className="mt-3">
                        <ProgressBar
                          value={regionPred.predictedWaiScore ?? 0}
                          severity={regionPred.predictedSeverity}
                        />
                      </div>
                      {regionPred.confidence != null && (
                        <p className="mt-2 text-xs text-ink-subtle">
                          Confidence {(regionPred.confidence * 100).toFixed(0)}%
                        </p>
                      )}
                    </CardBody>
                  </Card>
                )}

                <Card>
                  <CardHeader
                    title="Alerts"
                    subtitle="WAI stress alerts for this region"
                    icon={<Bell className="h-5 w-5" />}
                    accent={openAlerts.length > 0 ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'}
                    action={
                      <Link href={`/water/stress-alerts?region_id=${id}`}>
                        <Badge tone="slate">Open list →</Badge>
                      </Link>
                    }
                  />
                  <CardBody>
                    {alertsQuery.isPending ? (
                      <Spinner />
                    ) : openAlerts.length === 0 ? (
                      <p className="text-sm text-ink-subtle">
                        No open alerts. All region stress alerts are resolved.
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {openAlerts.slice(0, 5).map((a) => (
                          <Link
                            href={`/water/stress-alerts?region_id=${id}`}
                            key={a.id}
                            className="flex items-center justify-between rounded-xl border border-line bg-canvas p-3 hover:border-brand/40"
                          >
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-ink">
                                {ALERT_LABELS[a.alert_type] ?? a.alert_type}
                              </p>
                              <p className="text-[11px] text-ink-subtle">
                                {fmtMonth(a.week_start_date)} · {a.status}
                                {a.wai_score != null && ` · WAI ${fmtNumber(a.wai_score)}`}
                              </p>
                            </div>
                            <SeverityBadge severity={a.severity} />
                          </Link>
                        ))}
                      </div>
                    )}
                  </CardBody>
                </Card>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <MetricChartCard
                title="Rainfall"
                subtitle="Last 30 days + anomaly vs normal"
                icon={CloudRain}
                rows={sorted}
                barKey="mm"
                lineKey="anom"
                barName="Rainfall (mm, 30d)"
                lineName="Anomaly (%)"
              />
              <MetricChartCard
                title="Evapotranspiration"
                subtitle="8-day ET + anomaly vs normal"
                icon={Sun}
                rows={sorted}
                barKey="et"
                lineKey="etAnom"
                barName="ET (mm, 8d)"
                lineName="Anomaly (%)"
              />
              <Card>
                <CardHeader
                  title="Surface Water"
                  subtitle="Monthly change in open-water area"
                  icon={<Waves className="h-5 w-5" />}
                  accent="bg-brand-soft text-brand"
                  action={
                    latest?.surfaceWaterChangePct != null ? (
                      <Badge tone={latest.surfaceWaterChangePct >= 0 ? 'ok' : 'crit'}>
                        {fmtPct(latest.surfaceWaterChangePct, 1)}
                      </Badge>
                    ) : undefined
                  }
                />
                <CardBody>
                  <SurfaceWaterChart rows={sorted} />
                </CardBody>
              </Card>
            </div>

            <p className="text-[11px] text-ink-subtle">
              Data status: {latest.dataStatus ?? 'Actual'} · provider {latest.dataProvider ?? 'GEE'} ·
              model {latest.waiModelVersion ?? '—'} · quality{' '}
              {latest.qualityStatus ?? '—'}
              {shortHistory && ` · coverage since ${fmtMonth(sorted[0].weekStart)}`}
            </p>
          </>
        )}
      </div>
    </AppShell>
  )
}

function MetricChartCard({
  title,
  subtitle,
  icon: Icon,
  rows,
  barKey,
  lineKey,
  barName,
  lineName,
}: {
  title: string
  subtitle: string
  icon: LucideIcon
  rows: Array<{
    weekStart: string
    rainfallMm30day?: number | null
    rainfallAnomaly?: number | null
    etMm8day?: number | null
    etAnomaly?: number | null
  }>
  barKey: 'mm' | 'et'
  lineKey: 'anom' | 'etAnom'
  barName: string
  lineName: string
}) {
  const data = useMemo(
    () =>
      rows.map((r) => ({
        month: fmtMonth(r.weekStart),
        mm: r.rainfallMm30day ?? null,
        anom: r.rainfallAnomaly ?? null,
        et: r.etMm8day ?? null,
        etAnom: r.etAnomaly ?? null,
      })),
    [rows],
  )

  const hasAny = data.some((d) => d[barKey] != null)

  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} icon={<Icon className="h-5 w-5" />} accent="bg-brand-soft text-brand" />
      <CardBody>
        {!hasAny ? (
          <EmptyState title="No data" message="No values recorded for this metric." />
        ) : (
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                <XAxis dataKey="month" tick={{ fontSize: 9, fill: AXIS }} interval="preserveStartEnd" />
                <YAxis yAxisId="left" tick={{ fontSize: 9, fill: AXIS }} width={36} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 9, fill: AXIS }} width={36} />
                <RTooltip {...TOOLTIP_STYLE} formatter={(v: number, name: string) => [fmtNumber(v), name]} />
                <Bar yAxisId="left" dataKey={barKey} fill="#38bdf8" name={barName} radius={[3, 3, 0, 0]} />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey={lineKey}
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  dot={false}
                  name={lineName}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function SurfaceWaterChart({ rows }: { rows: Array<{ weekStart: string; surfaceWaterChangePct?: number | null }> }) {
  const data = useMemo(
    () =>
      rows.map((r) => ({
        month: fmtMonth(r.weekStart),
        pct: r.surfaceWaterChangePct ?? null,
      })),
    [rows],
  )
  const hasAny = data.some((d) => d.pct != null)

  if (!hasAny) {
    return <EmptyState title="No data" message="No open-water change recorded." />
  }

  return (
    <div className="h-44">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
          <XAxis dataKey="month" tick={{ fontSize: 9, fill: AXIS }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9, fill: AXIS }} width={36} />
          <RTooltip {...TOOLTIP_STYLE} formatter={(v: number) => [`${fmtNumber(v, 1)}%`, 'Change']} />
          <ReferenceLine y={0} stroke={AXIS} />
          <Bar dataKey="pct" name="Change (%)" radius={[3, 3, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={(d.pct ?? 0) >= 0 ? '#15693C' : '#A81E1E'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
