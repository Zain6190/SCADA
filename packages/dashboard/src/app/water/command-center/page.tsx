'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import {
  Waves, AlertTriangle, Map as MapIcon, Radio, LineChart, Bell, TrendingUp, ShieldCheck,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { ReliabilityBadge } from '@/features/water/reliability-badge'
import type {
  OperationalAlert, OperationalAsset, V2AssetPrediction, V2LeadTimeForecast, V2NationalOverview,
} from '@/features/water/types'
import { fmtNumber } from '@/lib/format'

const QUICK_LINKS = [
  { label: 'Flood Map', href: '/water/flood-map', icon: MapIcon },
  { label: 'Alerts', href: '/water/operator/alerts', icon: Bell },
  { label: 'Predictions', href: '/water/predictions', icon: TrendingUp },
  { label: 'Sensors', href: '/water/sensors', icon: Radio },
  { label: 'Operations', href: '/water/operator', icon: ShieldCheck },
  { label: 'Analyst', href: '/water/analyst', icon: LineChart },
]

type Tone = 'slate' | 'sky' | 'emerald' | 'amber' | 'red'

function severityTone(sev?: string | null): Tone {
  if (sev === 'Critical' || sev === 'CRITICAL') return 'red'
  if (sev === 'Danger' || sev === 'Warning' || sev === 'HIGH' || sev === 'WARNING') return 'amber'
  if (sev === 'Watch') return 'sky'
  return 'emerald'
}

function freshness(hours?: number | null): { tone: Tone; label: string } {
  if (hours == null) return { tone: 'slate', label: 'No official reading' }
  const rounded = `${Math.round(hours)}h ago`
  if (hours < 6) return { tone: 'emerald', label: rounded }
  if (hours < 24) return { tone: 'sky', label: rounded }
  if (hours < 72) return { tone: 'amber', label: rounded }
  return { tone: 'red', label: rounded }
}

function hasOfficialReading(asset: OperationalAsset): boolean {
  return (
    asset.current_level_ft != null
    || asset.current_inflow != null
    || asset.current_outflow != null
    || asset.current_discharge != null
    || asset.last_observed_at != null
  )
}

function levelBar(asset: OperationalAsset): { pct: number; tone: Tone } | null {
  const level = asset.current_level_ft
  const warning = asset.warning_level_ft
  if (level == null || warning == null) return null
  const critical = asset.critical_level_ft
  if (critical != null && level >= critical) return { pct: 100, tone: 'red' }
  if (level >= warning) return { pct: 75, tone: 'amber' }
  const normal = asset.normal_level_ft
  if (normal == null || warning <= normal) return null
  const pct = Math.min(100, Math.max(0, ((level - normal) / (warning - normal)) * 75))
  return { pct, tone: 'sky' }
}

function methodLabel(method?: string): string {
  if (!method) return 'Model'
  if (method === 'physics_routing') return 'Physics routing'
  if (method.startsWith('ml_xgboost_')) return `XGBoost ${method.slice('ml_xgboost_'.length)}`
  if (method === 'ml_xgboost') return 'XGBoost'
  return method
}

function realForecasts(overview?: V2NationalOverview): Map<number, V2AssetPrediction> {
  const byId = new Map<number, V2AssetPrediction>()
  for (const province of overview?.provinces ?? []) {
    for (const asset of province.assets) {
      if (asset.model_metadata?.status === 'NO_DATA') continue
      if (!asset.predictions?.['7_day']) continue
      byId.set(asset.asset_id, asset)
    }
  }
  return byId
}

function ReadingValue({ label, value, unit }: { label: string; value: number | null | undefined; unit: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-ink-subtle">{label}</span>
      <span className="font-medium text-ink">
        {value != null ? `${fmtNumber(value)} ${unit}` : '—'}
      </span>
    </div>
  )
}

function ForecastBlock({ forecast, method }: { forecast: V2LeadTimeForecast; method?: string }) {
  const stressMissing = forecast.water_stress.category === 'No Data'
  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">7-day model</p>
        <span className="text-[10px] text-ink-muted">{methodLabel(method)}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
        <div className="flex justify-between gap-2">
          <span className="text-ink-subtle">Stress</span>
          <span className="font-medium text-ink">
            {stressMissing ? '—' : `${forecast.water_stress.value} ${forecast.water_stress.category}`}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-ink-subtle">Flood risk</span>
          <span className="font-medium text-ink">
            {forecast.flood_risk.value} {forecast.flood_risk.category}
          </span>
        </div>
        <ReadingValue label="Discharge" value={forecast.discharge.value_cusecs} unit="cusecs" />
        <ReadingValue label="Rainfall" value={forecast.rainfall.value_mm} unit="mm" />
      </div>
      {forecast.confidence != null && (
        <p className="mt-2 text-[10px] text-ink-subtle">
          Confidence {Math.round(forecast.confidence * 100)}%
        </p>
      )}
    </div>
  )
}

function AssetCard({
  asset,
  forecast,
  reliability,
}: {
  asset?: OperationalAsset
  forecast?: V2AssetPrediction
  reliability?: Parameters<typeof ReliabilityBadge>[0]['r']
}) {
  const name = asset?.canonical_name ?? forecast?.asset_name ?? 'Asset'
  const assetType = asset?.asset_type ?? forecast?.asset_type
  const river = asset?.river
  const fresh = freshness(asset?.data_age_hours)
  const bar = asset ? levelBar(asset) : null
  const lead = forecast?.predictions?.['7_day']
  const id = asset?.id ?? forecast?.asset_id

  return (
    <Link href={id != null ? `/water/operator/assets?highlight=${id}` : '/water/predictions'}>
      <Card className="group h-full cursor-pointer transition-all hover:border-brand/25 hover:bg-surface">
        <CardBody className="p-4">
          <div className="mb-3 flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{name}</p>
              <p className="text-[11px] text-ink-subtle">
                {assetType === 'barrage' ? 'Barrage' : assetType === 'dam' ? 'Dam' : assetType}
                {river ? ` · ${river}` : ''}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
              <ReliabilityBadge r={reliability} />
              {asset && asset.active_alert_count > 0 && (
                <Badge tone={severityTone(asset.highest_severity)}>
                  <AlertTriangle className="h-3 w-3" />{asset.active_alert_count}
                </Badge>
              )}
              {asset && hasOfficialReading(asset) && (
                <Badge tone={fresh.tone}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />{fresh.label}
                </Badge>
              )}
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-[10px]">
              <span className="font-semibold uppercase tracking-wider text-ink-subtle">Official</span>
              <span className="text-ink-muted">
                {asset && hasOfficialReading(asset)
                  ? (asset.latest_source || 'IRSA / FFD')
                  : 'No official reading'}
              </span>
            </div>
            {asset && hasOfficialReading(asset) ? (
              <>
                {bar && asset.current_level_ft != null && (
                  <div className="mb-2">
                    <div className="mb-1 flex items-center justify-between text-[10px]">
                      <span className="text-ink-subtle">Level</span>
                      <span className="font-medium text-ink-muted">{fmtNumber(asset.current_level_ft)} ft</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface-alt">
                      <div
                        className={`h-full rounded-full ${
                          bar.tone === 'red' ? 'bg-crit' : bar.tone === 'amber' ? 'bg-warn' : 'bg-brand'
                        }`}
                        style={{ width: `${Math.max(2, bar.pct)}%` }}
                      />
                    </div>
                  </div>
                )}
                {asset.current_level_ft != null && !bar && (
                  <ReadingValue label="Level" value={asset.current_level_ft} unit="ft" />
                )}
                <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                  <ReadingValue label="Inflow" value={asset.current_inflow} unit="cusecs" />
                  <ReadingValue label="Outflow" value={asset.current_outflow} unit="cusecs" />
                  <ReadingValue label="Discharge" value={asset.current_discharge} unit="cusecs" />
                  <ReadingValue label="Capacity" value={asset.capacity_maf} unit="MAF" />
                </div>
              </>
            ) : (
              <p className="text-[11px] text-ink-subtle">No official reading</p>
            )}
          </div>

          {lead ? (
            <ForecastBlock forecast={lead} method={forecast?.model_metadata.prediction_method} />
          ) : (
            <p className="mt-3 border-t border-line pt-3 text-[11px] text-ink-subtle">Forecast unavailable</p>
          )}
        </CardBody>
      </Card>
    </Link>
  )
}

function AlertTicker({ alerts }: { alerts: OperationalAlert[] }) {
  if (alerts.length === 0) return null
  return (
    <div className="overflow-hidden rounded-xl border border-warn/25 bg-warn-soft">
      <div className="flex items-center gap-3 px-4 py-2.5">
        <div className="flex shrink-0 items-center gap-2">
          <Bell className="h-4 w-4 text-warn" />
          <span className="text-xs font-semibold text-warn">{alerts.length} active</span>
        </div>
        <div className="flex-1 overflow-hidden">
          <div className="flex gap-6 overflow-x-auto whitespace-nowrap">
            {alerts.map((alert) => (
              <Link
                key={alert.id}
                href="/water/operator/alerts"
                className="flex shrink-0 items-center gap-2 text-xs text-ink-muted hover:text-warn"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${alert.severity === 'Critical' ? 'bg-crit' : 'bg-warn'}`} />
                <span className="font-medium text-ink-muted">{alert.asset_name ?? `Asset ${alert.asset_id}`}</span>
                <span>·</span>
                <span>{alert.alert_type}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function WaterCommandCenterPage() {
  const assetsQuery = useQuery({
    queryKey: ['command-center', 'operational-assets'],
    queryFn: () => waterApi.getOperationalAssets(),
    refetchInterval: 30_000,
  })
  const alertsQuery = useQuery({
    queryKey: ['command-center', 'operational-alerts'],
    queryFn: () => waterApi.getOperationalAlerts({ limit: 50 }),
    refetchInterval: 30_000,
  })
  const overviewQuery = useQuery({
    queryKey: ['v2-national-overview'],
    queryFn: () => waterApi.getV2NationalOverview(),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
    retry: 1,
  })
  const reliabilityQuery = useQuery({
    queryKey: ['v2-reliability'],
    queryFn: () => waterApi.getV2Reliability(),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
    retry: 1,
  })

  const assets = assetsQuery.data ?? []
  const forecasts = realForecasts(overviewQuery.data)
  const openAlerts = (alertsQuery.data ?? []).filter((alert) => alert.status !== 'RESOLVED')
  const observed = assets.filter(hasOfficialReading)
  const ages = observed
    .map((asset) => asset.data_age_hours)
    .filter((hours): hours is number => hours != null)
  const avgAge = ages.length > 0 ? ages.reduce((sum, hours) => sum + hours, 0) / ages.length : null
  const forecastCount = overviewQuery.data?.assets_monitored ?? forecasts.size
  const modelAlerts = overviewQuery.data?.critical_alerts ?? []

  const cards = new Map<number, { asset?: OperationalAsset; forecast?: V2AssetPrediction }>()
  for (const asset of observed) {
    cards.set(asset.id, { asset, forecast: forecasts.get(asset.id) })
  }
  forecasts.forEach((forecast, id) => {
    const existing = cards.get(id)
    if (existing) existing.forecast = forecast
    else cards.set(id, { forecast, asset: assets.find((asset) => asset.id === id) })
  })
  const cardList = Array.from(cards.entries()).sort((a, b) => {
    const nameA = a[1].asset?.canonical_name ?? a[1].forecast?.asset_name ?? ''
    const nameB = b[1].asset?.canonical_name ?? b[1].forecast?.asset_name ?? ''
    return nameA.localeCompare(nameB)
  })

  const loading = assetsQuery.isPending && overviewQuery.isPending && !assetsQuery.data && !overviewQuery.data
  const bothFailed = assetsQuery.isError && overviewQuery.isError
  const description = observed.length + forecastCount > 0
    ? `${observed.length} official reading${observed.length === 1 ? '' : 's'} and ${forecastCount} model forecast${forecastCount === 1 ? '' : 's'}.`
    : 'Official IRSA and FFD readings, plus AquaVision model forecasts. Values appear only when that data exists.'

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="AquaVision Command Center"
          description={description}
          icon={<Waves className="h-6 w-6" />}
          updatedAt={overviewQuery.data?.timestamp}
          badge={
            <Badge tone={modelAlerts.length > 0 || openAlerts.length > 0 ? 'amber' : 'emerald'}>
              {modelAlerts.length + openAlerts.length > 0
                ? `${modelAlerts.length + openAlerts.length} active alert${modelAlerts.length + openAlerts.length === 1 ? '' : 's'}`
                : 'All clear'}
            </Badge>
          }
        />

        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Spinner label="Loading official readings and forecasts" />
          </div>
        ) : bothFailed ? (
          <ErrorState
            title="Failed to load"
            message="Official readings and model forecasts are both unavailable."
            onRetry={() => {
              assetsQuery.refetch()
              overviewQuery.refetch()
            }}
          />
        ) : (
          <>
            <AlertTicker alerts={openAlerts} />

            {modelAlerts.length > 0 && (
              <div className="space-y-2">
                <h2 className="text-sm font-semibold text-ink">Forecast alerts</h2>
                {modelAlerts.map((alert, index) => (
                  <div
                    key={`${alert.timestamp}-${alert.type}-${index}`}
                    className={`rounded-lg border px-3 py-2 text-xs ${
                      alert.level === 'CRITICAL'
                        ? 'border-crit/25 bg-crit-soft text-crit'
                        : 'border-warn/25 bg-warn-soft text-warn'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <AlertTriangle className="h-3 w-3" />
                      <span className="font-semibold">{alert.level}</span>
                      <span className="text-ink-muted">·</span>
                      <span>{alert.type}</span>
                      <span className="text-ink-muted">·</span>
                      <span>{alert.lead_time}</span>
                      <Badge tone="sky">Forecast</Badge>
                    </div>
                    <p className="mt-1 text-ink-muted">{alert.message}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">National WAI</p>
                <p className="text-xl font-bold text-white">
                  {overviewQuery.data?.national_wai != null ? fmtNumber(overviewQuery.data.national_wai) : '—'}
                </p>
                <p className="text-[11px] text-ink-subtle">
                  {overviewQuery.data?.national_status ?? 'No model WAI'}
                </p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Model forecasts</p>
                <p className="text-xl font-bold text-white">{overviewQuery.isSuccess ? forecastCount : '—'}</p>
                <p className="text-[11px] text-ink-subtle">Assets with a real 7-day forecast</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Forecast alerts</p>
                <p className={`text-xl font-bold ${modelAlerts.length > 0 ? 'text-warn' : 'text-ok'}`}>
                  {overviewQuery.isSuccess ? modelAlerts.length : '—'}
                </p>
                <p className="text-[11px] text-ink-subtle">Critical and high, from the model</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Avg official age</p>
                <p className="text-xl font-bold text-white">{avgAge != null ? `${Math.round(avgAge)}h` : '—'}</p>
                <p className="text-[11px] text-ink-subtle">IRSA and FFD readings only</p>
              </Card>
            </div>

            {overviewQuery.isError && (
              <ErrorState
                title="Forecasts unavailable"
                message="Official readings are still shown. The model overview did not load."
                onRetry={() => overviewQuery.refetch()}
              />
            )}

            <div className="flex flex-wrap gap-1">
              {QUICK_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-[10px] font-medium text-ink-muted transition-colors hover:border-brand/25 hover:text-brand"
                >
                  <link.icon className="h-3 w-3" />{link.label}
                </Link>
              ))}
            </div>

            {cardList.length === 0 ? (
              <EmptyState
                title="No official readings or forecasts"
                message="Assets appear here when an IRSA or FFD reading exists, or when the model can forecast from that data."
              />
            ) : (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-ink">Infrastructure status</h2>
                  <Badge tone="sky">{cardList.length} assets</Badge>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {cardList.map(([id, card]) => (
                    <AssetCard
                      key={id}
                      asset={card.asset}
                      forecast={card.forecast}
                      reliability={reliabilityQuery.data?.assets?.[String(id)]}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
