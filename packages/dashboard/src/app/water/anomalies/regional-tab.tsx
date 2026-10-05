// packages/dashboard/src/app/water/anomalies/regional-tab.tsx
// Regional anomaly tab: real rainfall / ET deviations + anomaly-driven alerts.
'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ReferenceLine,
} from 'recharts'
import { CloudRain, Sun, AlertTriangle, Droplets } from 'lucide-react'
import Link from 'next/link'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useWaterIndicators, useWaterRegions, useStressAlerts } from '@/features/water/hooks'
import { fmtNumber, fmtPct, titleCase } from '@/lib/format'

const GRID = '#e2e8f0'
const AXIS = '#64748b'
const TOOLTIP_STYLE = {
  contentStyle: { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 },
  labelStyle: { color: '#94a3b8' },
}

const RAINFALL_DEFICIT_THRESHOLD = -30
const ET_HIGH_THRESHOLD = 25

const ANOMALY_TYPES = new Set(['RAINFALL_DEFICIT', 'HIGH_ET'])

const ALERT_LABELS: Record<string, string> = {
  RAINFALL_DEFICIT: 'Rainfall Deficit',
  HIGH_ET: 'High Evapotranspiration',
}

const fmtMonth = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })

const isOpenStatus = (status: string | null | undefined) =>
  (status ?? '').toUpperCase() !== 'RESOLVED'

interface LatestRow {
  regionId: number
  name: string
  rainfallAnomaly: number | null
  etAnomaly: number | null
  waiScore: number | null
}

export function RegionalAnomalyTab() {
  const indicatorsQuery = useWaterIndicators({ limit: 500 })
  const regionsQuery = useWaterRegions()
  const stressQuery = useStressAlerts({ limit: 200 })

  const latestMonth = useMemo(() => {
    let max = ''
    for (const i of indicatorsQuery.data ?? []) {
      if (i.weekStart > max) max = i.weekStart
    }
    return max
  }, [indicatorsQuery.data])

  const latestRows = useMemo<LatestRow[]>(() => {
    const names = new Map((regionsQuery.data ?? []).map((r) => [r.id, r.name]))
    const rows: LatestRow[] = []
    for (const i of indicatorsQuery.data ?? []) {
      if (i.weekStart !== latestMonth) continue
      rows.push({
        regionId: i.regionId,
        name: names.get(i.regionId) ?? `Region ${i.regionId}`,
        rainfallAnomaly: i.rainfallAnomaly ?? null,
        etAnomaly: i.etAnomaly ?? null,
        waiScore: i.waiScore ?? null,
      })
    }
    return rows
  }, [indicatorsQuery.data, latestMonth, regionsQuery.data])

  const rainfallBars = useMemo(
    () =>
      latestRows
        .filter((r) => r.rainfallAnomaly != null)
        .map((r) => ({ name: r.name, value: r.rainfallAnomaly as number }))
        .sort((a, b) => b.value - a.value),
    [latestRows],
  )
  const etBars = useMemo(
    () =>
      latestRows
        .filter((r) => r.etAnomaly != null)
        .map((r) => ({ name: r.name, value: r.etAnomaly as number }))
        .sort((a, b) => a.value - b.value),
    [latestRows],
  )

  const deficitCount = latestRows.filter(
    (r) => r.rainfallAnomaly != null && r.rainfallAnomaly <= RAINFALL_DEFICIT_THRESHOLD,
  ).length
  const highEtCount = latestRows.filter(
    (r) => r.etAnomaly != null && r.etAnomaly >= ET_HIGH_THRESHOLD,
  ).length
  const withData = latestRows.filter((r) => r.rainfallAnomaly != null || r.etAnomaly != null).length

  const anomalyAlerts = (stressQuery.data ?? [])
    .filter((a) => ANOMALY_TYPES.has(a.alert_type))
    .sort((a, b) => {
      const openA = isOpenStatus(a.status) ? 1 : 0
      const openB = isOpenStatus(b.status) ? 1 : 0
      if (openA !== openB) return openB - openA
      return b.week_start_date.localeCompare(a.week_start_date)
    })
  const openAnomalyAlerts = anomalyAlerts.filter((a) => isOpenStatus(a.status)).length

  const pending = indicatorsQuery.isPending || regionsQuery.isPending
  const failed = indicatorsQuery.isError || regionsQuery.isError

  if (pending) return <Spinner label="Loading regional anomalies" />
  if (failed) {
    return (
      <ErrorState
        onRetry={() => {
          indicatorsQuery.refetch()
          regionsQuery.refetch()
        }}
      />
    )
  }
  if (!latestRows.length) {
    return (
      <EmptyState
        title="No indicator data"
        message="No GEE indicator rows available yet. Run the WAI pipeline to populate regional anomalies."
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Regions with data"
          value={withData}
          detail={latestMonth ? `Rainfall + ET anomaly · ${fmtMonth(latestMonth)}` : undefined}
          icon={Droplets}
        />
        <KpiCard
          label="Rainfall deficit"
          value={deficitCount}
          detail={`Rainfall ≤ ${RAINFALL_DEFICIT_THRESHOLD}% vs normal`}
          icon={CloudRain}
          severity={deficitCount > 0 ? 'Severe' : undefined}
        />
        <KpiCard
          label="High evapotranspiration"
          value={highEtCount}
          detail={`ET ≥ +${ET_HIGH_THRESHOLD}% vs normal`}
          icon={Sun}
          severity={highEtCount > 0 ? 'Severe' : undefined}
        />
        <KpiCard
          label="Open anomaly alerts"
          value={openAnomalyAlerts}
          detail="Rainfall-deficit / high-ET stress alerts"
          icon={AlertTriangle}
          accent={openAnomalyAlerts > 0 ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Rainfall Anomaly by Region"
            subtitle={`Deviation from normal · ${latestMonth ? fmtMonth(latestMonth) : ''} · worst at top`}
            icon={<CloudRain className="h-5 w-5" />}
            accent="bg-brand-soft text-brand"
            action={<Badge tone="crit">threshold −{Math.abs(RAINFALL_DEFICIT_THRESHOLD)}%</Badge>}
          />
          <CardBody>
            {!rainfallBars.length ? (
              <EmptyState title="No rainfall anomaly data" message="Rainfall anomalies not computed yet." />
            ) : (
              <div style={{ height: Math.max(320, rainfallBars.length * 24) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rainfallBars} layout="vertical" margin={{ top: 5, right: 16, left: 4, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 9, fill: AXIS }} />
                    <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 9, fill: AXIS }} />
                    <RTooltip {...TOOLTIP_STYLE} formatter={(v: number) => [`${fmtPct(v, 1)}`, 'Rainfall anomaly']} />
                    <ReferenceLine x={RAINFALL_DEFICIT_THRESHOLD} stroke="#A81E1E" strokeDasharray="4 4" />
                    <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                      {rainfallBars.map((d) => (
                        <Cell key={d.name} fill={d.value <= RAINFALL_DEFICIT_THRESHOLD ? '#A81E1E' : '#38bdf8'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Evapotranspiration Anomaly by Region"
            subtitle={`Deviation from normal · ${latestMonth ? fmtMonth(latestMonth) : ''} · highest at top`}
            icon={<Sun className="h-5 w-5" />}
            accent="bg-brand-soft text-brand"
            action={<Badge tone="crit">threshold +{ET_HIGH_THRESHOLD}%</Badge>}
          />
          <CardBody>
            {!etBars.length ? (
              <EmptyState title="No ET anomaly data" message="ET anomalies not computed yet." />
            ) : (
              <div style={{ height: Math.max(320, etBars.length * 24) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={etBars} layout="vertical" margin={{ top: 5, right: 16, left: 4, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 9, fill: AXIS }} />
                    <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 9, fill: AXIS }} />
                    <RTooltip {...TOOLTIP_STYLE} formatter={(v: number) => [`${fmtPct(v, 1)}`, 'ET anomaly']} />
                    <ReferenceLine x={ET_HIGH_THRESHOLD} stroke="#A81E1E" strokeDasharray="4 4" />
                    <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                      {etBars.map((d) => (
                        <Cell key={d.name} fill={d.value >= ET_HIGH_THRESHOLD ? '#A81E1E' : '#15693C'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Anomaly-Driven Stress Alerts"
          subtitle="Rainfall deficit and high-ET alerts from the weekly risk pipeline"
          icon={<AlertTriangle className="h-5 w-5" />}
          accent={openAnomalyAlerts > 0 ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'}
          action={
            <Link href="/water/stress-alerts">
              <Badge tone="slate">Open list →</Badge>
            </Link>
          }
        />
        <CardBody className="p-0">
          {stressQuery.isPending ? (
            <div className="p-4"><Spinner /></div>
          ) : anomalyAlerts.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="No anomaly alerts"
                message="No rainfall-deficit or high-ET alerts have been raised."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-surface text-[11px] uppercase tracking-wider text-ink-subtle">
                  <tr>
                    <Th>Region</Th>
                    <Th>Type</Th>
                    <Th>Severity</Th>
                    <Th>Week</Th>
                    <Th className="text-right">WAI</Th>
                    <Th className="text-right">Rainfall anom.</Th>
                    <Th className="text-right">ET anom.</Th>
                    <Th>Status</Th>
                    <Th></Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {anomalyAlerts.slice(0, 25).map((a) => (
                    <tr key={a.id} className="text-ink-muted hover:bg-surface-alt">
                      <Td className="font-medium text-ink">{a.region_name ?? `Region ${a.region_id}`}</Td>
                      <Td>{ALERT_LABELS[a.alert_type] ?? a.alert_type}</Td>
                      <Td><SeverityBadge severity={a.severity} /></Td>
                      <Td className="whitespace-nowrap">{fmtMonth(a.week_start_date)}</Td>
                      <Td className="text-right font-mono tabular-nums text-ink">
                        {a.wai_score != null ? fmtNumber(a.wai_score) : '—'}
                      </Td>
                      <Td className={`text-right font-mono tabular-nums ${a.rainfall_anomaly != null && a.rainfall_anomaly <= RAINFALL_DEFICIT_THRESHOLD ? 'text-crit' : ''}`}>
                        {a.rainfall_anomaly != null ? fmtPct(a.rainfall_anomaly, 1) : '—'}
                      </Td>
                      <Td className={`text-right font-mono tabular-nums ${a.et_anomaly != null && a.et_anomaly >= ET_HIGH_THRESHOLD ? 'text-crit' : ''}`}>
                        {a.et_anomaly != null ? fmtPct(a.et_anomaly, 1) : '—'}
                      </Td>
                      <Td>
                        <Badge tone={(a.status || '').toUpperCase() === 'RESOLVED' ? 'emerald' : 'red'}>
                          {titleCase(a.status)}
                        </Badge>
                      </Td>
                      <Td className="text-right text-[11px]">
                        <Link href={`/water/stress-alerts?region_id=${a.region_id}`} className="text-ink-subtle hover:text-brand">
                          View →
                        </Link>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <p className="text-[11px] text-ink-subtle">
        Source: Google Earth Engine — CHIRPS rainfall, ERA5-Land evapotranspiration · deviations vs
        the region&apos;s own historical mean · thresholds from the water_thresholds table
        (rainfall_deficit_pct −30, et_anomaly_high +25).
      </p>
    </div>
  )
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={`px-4 py-2.5 font-medium ${className ?? ''}`}>{children}</th>
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-2.5 text-xs ${className ?? ''}`}>{children}</td>
}
