// packages/dashboard/src/app/water/page.tsx
// AquaVision Overview - module landing.
'use client'

import { Droplets, Activity, MapPin, LineChart, Bell, Gauge, AlertCircle, AlertTriangle, Database, ShieldCheck, CloudRain, Wind, Warehouse } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { DataFreshness } from '@/components/ui/data-freshness'
import {
  useWaterOverview,
  useWaterAlerts,
  useWaterPredictions,
  useWaterMapData,
  useWaterRegions,
  useWaterIndicators,
} from '@/features/water/hooks'
import { sortBySeverity, regionNameById } from '@/features/water/mappers'
import { fmtNumber, fmtDate, fmtPct } from '@/lib/format'
import { WaterMapDynamic } from '@/features/water/water-map-dynamic'
import { useAuth } from '@/context/AuthContext'
import { canSeeAnalysis } from '@/lib/permissions'
import Link from 'next/link'

const AQUA = 'bg-sky-500/10 text-sky-300'

export default function WaterOverviewPage() {
  const { user } = useAuth()
  const overview = useWaterOverview()
  const alertsQuery = useWaterAlerts()
  const predictions = useWaterPredictions()
  const regions = useWaterRegions()
  const mapData = useWaterMapData()
  const indicators = useWaterIndicators({ limit: 20 })

  const alerts = alertsQuery.data ?? []
  const openAlerts = alerts.filter((a) => a.status !== 'RESOLVED')
  const latest = overview.data?.week_start_date
  const latestRows = (indicators.data ?? []).filter((i) => i.weekStart === latest)
  const latestRow = latestRows[0]
  const analyst = canSeeAnalysis(user?.permissions)
  const qualBadgeTone =
    latestRow?.dataQuality === 'Good' ? 'emerald'
    : latestRow?.dataQuality === 'Ok' ? 'amber'
    : latestRow?.dataQuality === 'Stale' || latestRow?.dataQuality === 'Missing' ? 'red'
    : 'slate'

  const scopeIds = user?.region_ids ?? []
  const scopedRegionNames = scopeIds.length
    ? scopeIds
        .map((id) => regionNameById(regions.data ?? [], id))
        .filter(Boolean)
    : null
  const scopeBadge = scopeIds.length
    ? (scopedRegionNames?.length ? scopedRegionNames.join(', ') : `${scopeIds.length} regions`)
    : 'National scope'

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="AquaVision Overview"
          description="Live weekly water availability (WAI) aggregated from GEE MODIS surface-water, CHIRPS rainfall, and MODIS ET."
          badge={
            overview.data?.national_status ? (
              <SeverityBadge severity={overview.data.national_status} />
            ) : undefined
          }
          icon={<Droplets className="h-6 w-6" />}
          updatedAt={overview.data?.week_start_date}
          action={
            <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-[11px] font-medium text-sky-300">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
              Scope: {scopeBadge}
            </span>
          }
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Regions Monitored"
            value={overview.data?.regions_monitored ?? '—'}
            detail={`at ${latest ? fmtDate(latest) : 'latest'} week`}
            icon={Gauge}
            accent={AQUA}
          />
          <KpiCard
            label="Mean WAI"
            value={
              overview.data?.avg_wai_score != null ? (
                <>
                  {fmtNumber(overview.data.avg_wai_score)}
                  <span className="text-sm text-slate-500"> / 100</span>
                </>
              ) : (
                '—'
              )
            }
            detail="National water availability average"
            icon={Activity}
            accent={AQUA}
          />
          <KpiCard
            label="Critical / Severe"
            value={overview.data?.critical_regions ?? '—'}
            detail="Highest-priority regions"
            icon={AlertCircle}
            accent="bg-red-500/10 text-red-300"
          />
          <KpiCard
            label="Open Alert Queue"
            value={openAlerts.length}
            detail={`${openAlerts.filter((a) => a.status === 'New').length} New ready to ack`}
            icon={Bell}
            accent="bg-amber-500/10 text-amber-300"
            onClick={() => (window.location.href = '/water/alerts')}
          />
          <KpiCard
            label="Reservoir / Storage"
            value={
              latestRow?.surfaceWaterAreaKm2 != null ? (
                <>
                  {fmtNumber(latestRow.surfaceWaterAreaKm2)}
                  <span className="text-sm text-slate-500"> km²</span>
                </>
              ) : (
                '—'
              )
            }
            detail={
              latestRow?.surfaceWaterChangePct != null ? (
                <span className={latestRow.surfaceWaterChangePct < 0 ? 'text-red-300' : 'text-emerald-300'}>
                  Δ {fmtPct(latestRow.surfaceWaterChangePct)} vs prior week
                </span>
              ) : (
                'Surface-water extent delta'
              )
            }
            icon={Warehouse}
            accent="bg-cyan-500/10 text-cyan-300"
          />
          <KpiCard
            label="Rainfall (30d)"
            value={analyst && latestRow?.rainfallMm30day != null ? `${fmtNumber(latestRow.rainfallMm30day)} mm` : '—'}
            detail={
              analyst
                ? latestRow?.rainfallAnomaly != null ? `${fmtPct(latestRow.rainfallAnomaly)} anomaly` : 'Rainfall anomaly'
                : (
                  <span className="inline-flex items-center gap-1 text-amber-300/90">
                    <ShieldCheck className="h-3 w-3" /> Analyst access required
                  </span>
                )
            }
            icon={CloudRain}
            accent="bg-sky-500/10 text-sky-300"
          />
          <KpiCard
            label="ET (8-day)"
            value={analyst && latestRow?.etMm8day != null ? `${fmtNumber(latestRow.etMm8day)} mm` : '—'}
            detail={
              analyst
                ? latestRow?.etAnomaly != null ? `Δ ${fmtPct(latestRow.etAnomaly)} anomaly` : 'Evapotranspiration'
                : (
                  <span className="inline-flex items-center gap-1 text-amber-300/90">
                    <ShieldCheck className="h-3 w-3" /> Analyst access required
                  </span>
                )
            }
            icon={Wind}
            accent="bg-violet-500/10 text-violet-300"
          />
        </div>

        {/* Data freshness + source / quality strip */}
        <Card>
          <CardBody className="flex flex-wrap items-center gap-x-6 gap-y-3 py-3">
            <DataFreshness
              updatedAt={overview.data?.week_start_date}
              source={latestRow?.dataSourceVersion}
            />
            {latestRow?.dataProvider && (
              <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
                <Database className="h-3 w-3 text-slate-600" /> Provider: {latestRow.dataProvider}
              </span>
            )}
            {latestRow?.dataStatus && (
              <Badge tone="slate">Status: {latestRow.dataStatus}</Badge>
            )}
            {latestRow?.dataQuality && (
              <Badge tone={qualBadgeTone}>Quality: {latestRow.dataQuality}</Badge>
            )}
            {latestRow?.waiModelVersion && (
              <Badge tone="violet">WAI {latestRow.waiModelVersion}</Badge>
            )}
          </CardBody>
        </Card>

        {/* Map */}
        <Card className="overflow-hidden">
          <CardHeader
            title="Water Stress Map"
            subtitle="Latest-week WAI severity by district"
            icon={<MapPin className="h-5 w-5" />}
            accent={AQUA}
            action={
              mapData.data?.length ? <Badge tone="sky">{mapData.data.length} regions</Badge> : undefined
            }
          />
          <CardBody className="p-3">
            {mapData.isPending ? (
              <div className="flex h-[400px] items-center justify-center"><Spinner label="Loading map" /></div>
            ) : mapData.isError ? (
              <ErrorState onRetry={() => mapData.refetch()} message="Could not reach AquaVision service." />
            ) : mapData.data?.length ? (
              <WaterMapDynamic features={mapData.data} height={400} />
            ) : (
              <EmptyState title="No map regions" message="No geometry data for the latest week." />
            )}
          </CardBody>
        </Card>

        {/* Forecast + alerts */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="2-Week Forecast"
              subtitle="Predicted WAI and severity by region"
              icon={<LineChart className="h-5 w-5" />}
              accent={AQUA}
              action={<Link href="/water/predictions"><Badge tone="sky">View all →</Badge></Link>}
            />
            <CardBody>
              {predictions.isPending ? (
                <Spinner />
              ) : predictions.isError ? (
                <ErrorState onRetry={() => predictions.refetch()} />
              ) : predictions.data?.length ? (
                <div className="space-y-3">
                  {sortBySeverity(predictions.data.slice(), (p) => p.predictedSeverity)
                    .slice(0, 5)
                    .map((p) => (
                      <div key={p.id} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                        <div>
                          <p className="text-sm font-medium text-slate-200">
                            {regionNameById(regions.data ?? [], p.regionId)}
                          </p>
                          <p className="text-[11px] text-slate-500">
                            {fmtDate(p.targetWeekStart)} · {p.modelVersion}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-slate-100">
                            WAI {p.predictedWaiScore ?? '—'}
                          </p>
                          <SeverityBadge severity={p.predictedSeverity} className="mt-1" />
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <EmptyState title="No forecast yet" message="Run the prediction pipeline to populate." />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Latest Alerts"
              subtitle="Auto-generated early-warning events"
              icon={<AlertTriangle size={18} />}
              accent="bg-amber-500/10 text-amber-300"
              action={<Link href="/water/operator/alerts"><Badge tone="amber">Manage →</Badge></Link>}
            />
            <CardBody>
              {alertsQuery.isPending ? (
                <Spinner />
              ) : alertsQuery.isError ? (
                <ErrorState onRetry={() => alertsQuery.refetch()} />
              ) : openAlerts.length ? (
                <div className="space-y-3">
                  {openAlerts.slice(0, 5).map((a) => (
                    <div key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-200">{a.asset_name ? `${a.asset_name} · ` : ''}{a.alert_type}</p>
                        <p className="text-[11px] text-slate-500">
                          {a.created_at ? fmtDate(a.created_at) : '—'}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={a.severity} />
                        <Badge tone="slate">{a.status}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No open alerts" message="Good news — everything is nominal." />
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}