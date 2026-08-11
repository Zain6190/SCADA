// packages/dashboard/src/app/water/analyst/page.tsx
// AquaVision Analyst Workspace - full-field analysis, anomaly diagnosis,
// data ingest (MANAGE_DATA) and CSV export (EXPORT). Analyst-specific home.
'use client'

import { useMemo, useState } from 'react'
import { Download, Upload, LineChart, CloudRain, Wind, AlertTriangle, BarChart3, ShieldCheck, FlaskConical } from 'lucide-react'
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RTooltip,
  CartesianGrid,
  Legend,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { ProgressBar } from '@/components/ui/progress'
import { useWaterIndicators, useWaterRegions, useCreateIndicator } from '@/features/water/hooks'
import { regionNameById } from '@/features/water/mappers'
import { fmtNumber, fmtPct, fmtDate } from '@/lib/format'
import { normalizeSeverity } from '@/lib/severity'
import { useAuth } from '@/context/AuthContext'
import { PERMISSIONS } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import type { IndicatorIngestPayload } from '@/features/water/api'
import type { IndicatorVM } from '@/features/water/types'

const AQUA = 'bg-sky-500/10 text-sky-300'

export default function AnalystWorkspacePage() {
  const { user } = useAuth()
  const regionsQuery = useWaterRegions()
  const indicatorsQuery = useWaterIndicators({ limit: 500 })
  const createIndicator = useCreateIndicator()

  const [regionId, setRegionId] = useState<string>('all')
  const [ingest, setIngest] = useState({
    region_id: '',
    week_start: new Date().toISOString().slice(0, 10),
    wai_score: '',
    rainfall_mm_30day: '',
    rainfall_anomaly: '',
    et_mm_8day: '',
    et_anomaly: '',
    surface_water_change_pct: '',
    data_quality: 'Good',
  })
  const [ingestError, setIngestError] = useState<string | null>(null)
  const [ingestOk, setIngestOk] = useState(false)

  const regions = regionsQuery.data ?? []
  const indicators = indicatorsQuery.data ?? []

  const regionName = regionId === 'all' ? 'All regions' : regionNameById(regions, Number(regionId))
  const scoped = regionId === 'all'
    ? indicators
    : indicators.filter((i) => i.regionId === Number(regionId))

  // Latest week per region for the diagnosis matrix.
  const latestByRegion = useMemo(() => {
    const map = new Map<number, IndicatorVM>()
    for (const i of indicators) {
      const prev = map.get(i.regionId)
      if (!prev || i.weekStart > prev.weekStart) map.set(i.regionId, i)
    }
    return Array.from(map.entries()).sort((a, b) => b[1].weekStart.localeCompare(a[1].weekStart))
  }, [indicators])

  // Time-series for the comparison chart (WAI vs rain vs ET).
  const chartData = useMemo(() => {
    return [...scoped]
      .sort((a, b) => a.weekStart.localeCompare(b.weekStart))
      .slice(-16)
      .map((i) => ({
        week: i.weekStart.slice(5),
        wai: i.waiScore,
        rain: i.rainfallMm30day,
        et: i.etMm8day,
      }))
  }, [scoped])

  const avgWai = scoped.length
    ? scoped.reduce((s, i) => s + (i.waiScore ?? 0), 0) / scoped.length
    : 0
  const avgRain = scoped.length
    ? scoped.reduce((s, i) => s + (i.rainfallMm30day ?? 0), 0) / scoped.length
    : 0
  const avgEt = scoped.length
    ? scoped.reduce((s, i) => s + (i.etMm8day ?? 0), 0) / scoped.length
    : 0
  const anomalyRows = scoped.filter(
    (i) =>
      (i.rainfallAnomaly != null && i.rainfallAnomaly < 0) ||
      (i.etAnomaly != null && i.etAnomaly > 0)
  )

  const canExport = !!user?.permissions?.includes(PERMISSIONS.AQUAVISION_EXPORT)
  const canIngest = !!user?.permissions?.includes(PERMISSIONS.AQUAVISION_MANAGE_DATA)

  const submitIngest = async (e: React.FormEvent) => {
    e.preventDefault()
    setIngestOk(false)
    setIngestError(null)
    if (!ingest.region_id || !ingest.week_start) {
      setIngestError('Select a region and week start date.')
      return
    }
    const payload: IndicatorIngestPayload = {
      region_id: Number(ingest.region_id),
      week_start_date: ingest.week_start,
      wai_score: Number(ingest.wai_score),
      surface_water_change_pct: ingest.surface_water_change_pct ? Number(ingest.surface_water_change_pct) : null,
      rainfall_mm_30day: ingest.rainfall_mm_30day ? Number(ingest.rainfall_mm_30day) : null,
      rainfall_anomaly: ingest.rainfall_anomaly ? Number(ingest.rainfall_anomaly) : null,
      et_mm_8day: ingest.et_mm_8day ? Number(ingest.et_mm_8day) : null,
      et_anomaly: ingest.et_anomaly ? Number(ingest.et_anomaly) : null,
      data_quality: ingest.data_quality,
      data_status: 'Calibrated',
      data_provider: 'manual',
    }
    try {
      await createIndicator.mutateAsync(payload)
      setIngestOk(true)
      setIngest((prev) => ({ ...prev, region_id: '', wai_score: '' }))
    } catch (err: any) {
      setIngestError(err?.response?.data?.detail ?? 'Failed to ingest indicator.')
    }
  }

  const exportCsv = () => {
    const header = [
      'region_id', 'week_start_date', 'wai_score', 'severity',
      'rainfall_mm_30day', 'rainfall_anomaly', 'et_mm_8day', 'et_anomaly',
      'surface_water_change_pct', 'data_status', 'data_quality',
    ]
    const rows = scoped.map((i) => [
      i.regionId,
      i.weekStart,
      i.waiScore ?? '',
      i.severity ?? '',
      i.rainfallMm30day ?? '',
      i.rainfallAnomaly ?? '',
      i.etMm8day ?? '',
      i.etAnomaly ?? '',
      i.surfaceWaterChangePct ?? '',
      i.dataStatus ?? '',
      i.dataQuality ?? '',
    ])
    const csv = [header.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aquavision-analyst-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const scopeCount = user?.region_ids?.length
  const scopeBadge = scopeCount ? `${scopeCount} regions` : 'National scope'

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Analyst Workspace"
          description="Full-field water analysis: rainfall, ET, anomalies, data quality, ingest and export."
          icon={<FlaskConical className="h-6 w-6" />}
          updatedAt={indicators.at(-1)?.weekStart ?? null}
          action={
            <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-[11px] font-medium text-sky-300">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
              Scope: {scopeBadge}
            </span>
          }
        />

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard label="Avg WAI" value={fmtNumber(avgWai)} icon={BarChart3} accent={AQUA} detail={`${regionName} · ${fmtNumber(scoped.length)} rows`} />
          <KpiCard label="Avg Rainfall / 30d" value={`${fmtNumber(avgRain)} mm`} icon={CloudRain} accent="bg-sky-600/10 text-sky-300" detail="CHIRPS-derived" />
          <KpiCard label="Avg ET / 8d" value={`${fmtNumber(avgEt)} mm`} icon={Wind} accent="bg-teal-500/10 text-teal-300" detail="MODIS-derived" />
          <KpiCard
            label="Anomaly hits"
            value={anomalyRows.length}
            icon={FlaskConical}
            accent="bg-amber-500/10 text-amber-300"
            detail={anomalyRows.length ? 'Rainfall deficit or elevated ET deviation' : 'No rainfall or ET deviation detected'}
          />
        </div>

        <Card>
          <CardHeader
            title="Per-Region Weekly Diagnosis"
            subtitle={`Latest week per region · ${regionName}`}
            icon={<FlaskConical className="h-5 w-5" />}
            accent={AQUA}
            action={
              <div className="flex items-center gap-2">
                <Badge tone="sky"><span className="h-1.5 w-1.5 rounded-full bg-sky-400" />Full-field analyst access</Badge>
                <Badge tone={anomalyRows.length ? 'amber' : 'emerald'}>
                  {anomalyRows.length ? `${anomalyRows.length} anomaly` : 'No anomalies'}
                </Badge>
              </div>
            }
          />
          <CardBody className="p-0">
            {indicatorsQuery.isPending ? (
              <div className="p-8"><Spinner /></div>
            ) : indicatorsQuery.isError ? (
              <div className="p-8"><ErrorState onRetry={() => indicatorsQuery.refetch()} /></div>
            ) : latestByRegion.length === 0 ? (
              <div className="p-8"><EmptyState title="No indicator rows" message="Run the GEE fetch + ingest pipeline." /></div>
            ) : (
              <div className="max-h-[520px] overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
                    <tr>
                      <Th>Region</Th><Th>Week</Th><Th>WAI</Th><Th>Severity</Th><Th>Rain 30d</Th><Th>Rain Δ</Th><Th>ET 8d</Th><Th>ET Δ</Th><Th>Surface Δ</Th><Th>Quality</Th><Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {latestByRegion.map(([rid, i]) => (
                      <tr key={rid} className="text-slate-300 hover:bg-slate-800/30">
                        <Td><span className="font-medium text-slate-100">{regionNameById(regions, rid)}</span></Td>
                        <Td className="whitespace-nowrap">{fmtDate(i.weekStart)}</Td>
                        <Td>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-100">{fmtNumber(i.waiScore)}</span>
                            <ProgressBar value={i.waiScore ?? 0} severity={i.severity} className="w-16" />
                          </div>
                        </Td>
                        <Td><SeverityBadge severity={i.severity} /></Td>
                        <Td>{fmtNumber(i.rainfallMm30day)} mm</Td>
                        <Td className={i.rainfallAnomaly != null && i.rainfallAnomaly < 0 ? 'text-amber-300' : 'text-slate-300'}>{fmtPct(i.rainfallAnomaly)}</Td>
                        <Td>{fmtNumber(i.etMm8day)} mm</Td>
                        <Td className={i.etAnomaly != null && i.etAnomaly > 0 ? 'text-amber-300' : 'text-slate-300'}>{fmtPct(i.etAnomaly)}</Td>
                        <Td>{fmtNumber(i.surfaceWaterChangePct)}%</Td>
                        <Td><Badge tone={qualityTone(i.dataQuality)}>{i.dataQuality ?? '—'}</Badge></Td>
                        <Td><Badge tone={statusTone(i.dataStatus)}>{i.dataStatus ?? '—'}</Badge></Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="WAI vs Rainfall vs ET"
            subtitle={`${regionName} · last 16 weeks`}
            icon={<BarChart3 className="h-5 w-5" />}
            accent={AQUA}
            action={
              <select
                value={regionId}
                onChange={(e) => setRegionId(e.target.value)}
                className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
              >
                <option value="all">All regions</option>
                {regions.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            }
          />
          <CardBody>
            {indicatorsQuery.isPending ? (
              <Spinner />
            ) : chartData.length === 0 ? (
              <EmptyState title="No rows for this region" />
            ) : (
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis yAxisId="left" domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#64748b' }} />
                    <RTooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }}
                      labelStyle={{ color: '#94a3b8' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                    <Bar yAxisId="right" dataKey="rain" fill="#0ea5e9" opacity={0.35} name="Rain 30d (mm)" barSize={10} />
                    <Bar yAxisId="right" dataKey="et" fill="#2dd4bf" opacity={0.35} name="ET 8d (mm)" barSize={10} />
                    <Line yAxisId="left" type="monotone" dataKey="wai" stroke="#38bdf8" strokeWidth={2} dot={false} name="WAI" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardBody>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Data Ingest"
              subtitle={canIngest ? 'Add a new weekly indicator (persists via AQUAVISION_MANAGE_DATA)' : 'AQUAVISION_MANAGE_DATA required'}
              icon={<Upload className="h-5 w-5" />}
              accent={canIngest ? AQUA : 'bg-slate-500/10 text-slate-400'}
            />
            <CardBody>
              {!canIngest ? (
                <div className="flex items-center gap-3 text-sm text-slate-500">
                  <ShieldCheck className="h-5 w-5 text-slate-600" />
                  Your role does not include data ingest privileges.
                </div>
              ) : (
                <form onSubmit={submitIngest} className="space-y-4">
                  {ingestError && <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{ingestError}</div>}
                  {ingestOk && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">Indicator upserted successfully.</div>}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Region">
                      <select
                        value={ingest.region_id}
                        onChange={(e) => setIngest({ ...ingest, region_id: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      >
                        <option value="" disabled>Select region…</option>
                        {regions.map((r) => (
                          <option key={r.id} value={r.id}>{r.name}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Week start date">
                      <input
                        type="date"
                        value={ingest.week_start}
                        onChange={(e) => setIngest({ ...ingest, week_start: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="WAI score *">
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        required
                        value={ingest.wai_score}
                        onChange={(e) => setIngest({ ...ingest, wai_score: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="Surface water Δ %">
                      <input
                        type="number"
                        step="0.1"
                        value={ingest.surface_water_change_pct}
                        onChange={(e) => setIngest({ ...ingest, surface_water_change_pct: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="Rainfall 30d (mm)">
                      <input
                        type="number"
                        step="0.1"
                        value={ingest.rainfall_mm_30day}
                        onChange={(e) => setIngest({ ...ingest, rainfall_mm_30day: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="Rainfall anomaly %">
                      <input
                        type="number"
                        step="0.1"
                        value={ingest.rainfall_anomaly}
                        onChange={(e) => setIngest({ ...ingest, rainfall_anomaly: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="ET 8d (mm)">
                      <input
                        type="number"
                        step="0.1"
                        value={ingest.et_mm_8day}
                        onChange={(e) => setIngest({ ...ingest, et_mm_8day: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="ET anomaly %">
                      <input
                        type="number"
                        step="0.1"
                        value={ingest.et_anomaly}
                        onChange={(e) => setIngest({ ...ingest, et_anomaly: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      />
                    </Field>
                    <Field label="Data quality">
                      <select
                        value={ingest.data_quality}
                        onChange={(e) => setIngest({ ...ingest, data_quality: e.target.value })}
                        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300 focus:border-sky-500/50 focus:outline-none"
                      >
                        {['Good', 'Ok', 'Stale', 'Missing'].map((q) => (
                          <option key={q} value={q}>{q}</option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <button
                    type="submit"
                    disabled={createIndicator.isPending}
                    className="inline-flex items-center gap-2 rounded-lg bg-sky-500/20 px-4 py-2 text-xs font-medium text-sky-300 transition-colors hover:bg-sky-500/30 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Upload className="h-3.5 w-3.5" />
                    {createIndicator.isPending ? 'Persisting…' : 'Upsert weekly indicator'}
                  </button>
                </form>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Data Export"
              subtitle={canExport ? 'Download the current view as CSV (analysis fields included)' : 'AQUAVISION_EXPORT required'}
              icon={<Download className="h-5 w-5" />}
              accent={canExport ? AQUA : 'bg-slate-500/10 text-slate-400'}
            />
            <CardBody className="space-y-4">
              {!canExport ? (
                <div className="flex items-center gap-3 text-sm text-slate-500">
                  <ShieldCheck className="h-5 w-5 text-slate-600" />
                  Your role does not include export privileges.
                </div>
              ) : (
                <>
                  <p className="text-xs leading-5 text-slate-500">
                    Exports the currently filtered rows ({scoped.length} indicators) with all analyst fields: WAI, rainfall,
                    anomalies, ET, surface-water delta, provenance, data quality.
                  </p>
                  <button
                    onClick={exportCsv}
                    disabled={scoped.length === 0}
                    className="inline-flex items-center gap-2 rounded-lg bg-sky-500/20 px-4 py-2 text-xs font-medium text-sky-300 transition-colors hover:bg-sky-500/30 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Export CSV ({scoped.length} rows)
                  </button>
                </>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}

function qualityTone(q: string | null | undefined): 'emerald' | 'amber' | 'red' | 'slate' {
  if (q === 'Good') return 'emerald'
  if (q === 'Ok') return 'amber'
  if (q === 'Stale' || q === 'Missing') return 'red'
  return 'slate'
}

function statusTone(q: string | null | undefined): 'sky' | 'slate' {
  return q === 'Actual' ? 'sky' : 'slate'
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      {children}
    </label>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-4 py-2.5 font-medium">{children}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn('px-4 py-2.5 text-xs', className)}>{children}</td>
}