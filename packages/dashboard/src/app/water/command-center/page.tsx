'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Waves, AlertTriangle, Map, Radio, LineChart, Bell, TrendingUp,
  ShieldCheck, Activity,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { fmtNumber } from '@/lib/format'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8100'

interface OperationalAsset {
  id: number
  canonical_name: string
  asset_type: string
  river?: string | null
  capacity_maf?: number | null
  normal_level_ft?: number | null
  warning_level_ft?: number | null
  critical_level_ft?: number | null
  is_active: boolean
  current_level_ft?: number | null
  current_inflow?: number | null
  current_outflow?: number | null
  current_discharge?: number | null
  last_observed_at?: string | null
  data_age_hours?: number | null
  active_alert_count: number
  highest_severity?: string | null
}

interface OperationalAlert {
  id: number
  asset_id: number
  asset_name?: string | null
  alert_type: string
  severity: string
  status: string
  message: string
  created_at: string
  downstream_population_exposed?: number | null
}

type Tone = 'slate' | 'sky' | 'emerald' | 'amber' | 'red'

function severityTone(sev?: string | null): Tone {
  if (sev === 'Critical') return 'red'
  if (sev === 'Danger' || sev === 'Warning') return 'amber'
  if (sev === 'Watch') return 'sky'
  return 'emerald'
}

function freshnessTone(h?: number | null): { tone: Tone; label: string } {
  if (h == null) return { tone: 'slate', label: 'No data' }
  if (h < 6) return { tone: 'emerald', label: `${Math.round(h)}h ago` }
  if (h < 24) return { tone: 'sky', label: `${Math.round(h)}h ago` }
  if (h < 72) return { tone: 'amber', label: `${Math.round(h)}h ago` }
  return { tone: 'red', label: `${Math.round(h)}h ago` }
}

function levelInfo(a: OperationalAsset) {
  const lv = a.current_level_ft
  if (lv == null || !a.warning_level_ft) return { pct: 0, tone: 'slate' as Tone, label: 'No reading' }
  const crit = a.critical_level_ft ?? a.warning_level_ft * 1.2
  if (lv >= crit) return { pct: 100, tone: 'red' as Tone, label: `${fmtNumber(lv)} ft` }
  if (lv >= a.warning_level_ft) return { pct: 75, tone: 'amber' as Tone, label: `${fmtNumber(lv)} ft` }
  const norm = a.normal_level_ft ?? a.warning_level_ft * 0.8
  const pct = norm > 0 ? Math.min(100, Math.max(0, ((lv - norm) / (a.warning_level_ft - norm)) * 75)) : 50
  return { pct, tone: 'sky' as Tone, label: `${fmtNumber(lv)} ft` }
}

const QUICK_LINKS = [
  { label: 'Flood Map', href: '/water/flood-map', icon: Map, accent: 'bg-crit-soft text-crit' },
  { label: 'Alerts', href: '/water/operator/alerts', icon: Bell, accent: 'bg-warn-soft text-warn' },
  { label: 'Predictions', href: '/water/predictions', icon: TrendingUp, accent: 'bg-brand-soft text-brand' },
  { label: 'Sensors', href: '/water/sensors', icon: Radio, accent: 'bg-brand-soft text-brand' },
  { label: 'Operations', href: '/water/operator', icon: ShieldCheck, accent: 'bg-brand-soft text-brand' },
  { label: 'Analyst', href: '/water/analyst', icon: LineChart, accent: 'bg-ok-soft text-ok' },
]

function AssetCard({ asset }: { asset: OperationalAsset }) {
  const fresh = freshnessTone(asset.data_age_hours)
  const lv = levelInfo(asset)
  return (
    <Link href={`/water/operator/assets?highlight=${asset.id}`}>
      <Card className="group cursor-pointer transition-all hover:border-brand/25 hover:bg-surface">
        <CardBody className="p-4">
          <div className="flex items-start justify-between gap-2 mb-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink truncate">{asset.canonical_name}</p>
              <p className="text-[11px] text-ink-subtle">
                {asset.asset_type === 'barrage' ? 'Barrage' : asset.asset_type === 'dam' ? 'Dam' : asset.asset_type}
                {asset.river ? ` \u00b7 ${asset.river}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {asset.active_alert_count > 0 && (
                <Badge tone={severityTone(asset.highest_severity)}>
                  <AlertTriangle className="h-3 w-3" />{asset.active_alert_count}
                </Badge>
              )}
              <Badge tone={fresh.tone}>
                <span className="h-1.5 w-1.5 rounded-full bg-current" />{fresh.label}
              </Badge>
            </div>
          </div>

          <div className="mb-3">
            <div className="flex items-center justify-between text-[10px] mb-1">
              <span className="text-ink-subtle">Level</span>
              <span className="font-medium text-ink-muted">{lv.label}</span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-alt overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  lv.tone === 'red' ? 'bg-crit' : lv.tone === 'amber' ? 'bg-warn' : 'bg-brand'
                }`}
                style={{ width: `${Math.max(2, lv.pct)}%` }}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
            <div className="flex justify-between">
              <span className="text-ink-subtle">Inflow</span>
              <span className="font-medium text-ink">{asset.current_inflow != null ? `${fmtNumber(asset.current_inflow)} cusecs` : '\u2014'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-subtle">Outflow</span>
              <span className="font-medium text-ink">{asset.current_outflow != null ? `${fmtNumber(asset.current_outflow)} cusecs` : '\u2014'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-subtle">Discharge</span>
              <span className="font-medium text-ink">{asset.current_discharge != null ? `${fmtNumber(asset.current_discharge)} cusecs` : '\u2014'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-subtle">Capacity</span>
              <span className="font-medium text-ink">{asset.capacity_maf != null ? `${fmtNumber(asset.capacity_maf)} MAF` : '\u2014'}</span>
            </div>
          </div>

          {asset.warning_level_ft && (
            <div className="mt-3 pt-2 border-t border-line flex gap-3 text-[10px]">
              <span className="text-ink-subtle">Warn: <span className="text-warn font-medium">{fmtNumber(asset.warning_level_ft)} ft</span></span>
              {asset.critical_level_ft && (
                <span className="text-ink-subtle">Crit: <span className="text-crit font-medium">{fmtNumber(asset.critical_level_ft)} ft</span></span>
              )}
            </div>
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
        <div className="flex items-center gap-2 shrink-0">
          <Bell className="h-4 w-4 text-warn" />
          <span className="text-xs font-semibold text-warn">{alerts.length} Active</span>
        </div>
        <div className="overflow-hidden flex-1">
          <div className="flex gap-6 whitespace-nowrap overflow-x-auto">
            {alerts.map((a) => (
              <Link key={a.id} href="/water/operator/alerts" className="flex items-center gap-2 text-xs text-ink-muted hover:text-warn shrink-0">
                <span className={`h-1.5 w-1.5 rounded-full ${a.severity === 'Critical' ? 'bg-crit' : a.severity === 'Danger' ? 'bg-sev-severe' : 'bg-warn'}`} />
                <span className="font-medium text-ink-muted">{a.asset_name ?? `Asset ${a.asset_id}`}</span>
                <span>\u00b7</span>
                <span>{a.alert_type}</span>
                {a.downstream_population_exposed != null && a.downstream_population_exposed > 0 && (
                  <span className="text-warn">{(a.downstream_population_exposed / 1000000).toFixed(1)}M exposed</span>
                )}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function WaterCommandCenterPage() {
  const [assets, setAssets] = useState<OperationalAsset[]>([])
  const [alerts, setAlerts] = useState<OperationalAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchData = async () => {
    try {
      const [assetsRes, alertsRes] = await Promise.allSettled([
        fetch(`${API_BASE}/water/operational/assets`),
        fetch(`${API_BASE}/water/operational/alerts?limit=50`),
      ])
      if (assetsRes.status === 'fulfilled' && assetsRes.value.ok) {
        setAssets(await assetsRes.value.json())
      }
      if (alertsRes.status === 'fulfilled' && alertsRes.value.ok) {
        const data = await alertsRes.value.json()
        setAlerts(Array.isArray(data) ? data.filter((a: OperationalAlert) => a.status !== 'RESOLVED') : [])
      }
      setLastUpdated(new Date())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const iv = setInterval(fetchData, 30_000)
    return () => clearInterval(iv)
  }, [])

  const openAlerts = alerts.filter((a) => a.status === 'NEW')
  const totalAlerts = alerts.length
  const assetsWithAlerts = assets.filter((a) => a.active_alert_count > 0).length
  const avgFreshness = assets.length > 0
    ? assets.reduce((sum, a) => sum + (a.data_age_hours ?? 0), 0) / assets.length
    : 0

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="AquaVision Command Center"
          description="Live overview of Pakistan's water infrastructure. 11 assets across Indus, Jhelum, Kabul, and Chenab basins."
          icon={<Waves className="h-6 w-6" />}
          badge={
            <div className="flex items-center gap-2">
              {lastUpdated && (
                <span className="flex items-center gap-1.5 text-[10px] text-ok">
                  <span className="h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
                  Live {lastUpdated.toLocaleTimeString()}
                </span>
              )}
              <Badge tone={totalAlerts > 0 ? 'amber' : 'emerald'}>
                {totalAlerts > 0 ? `${totalAlerts} active alert(s)` : 'All clear'}
              </Badge>
            </div>
          }
        />

        {loading ? (
          <div className="flex h-64 items-center justify-center"><Spinner label="Loading infrastructure" /></div>
        ) : error ? (
          <ErrorState title="Failed to load" message={error} onRetry={fetchData} />
        ) : (
          <>
            <AlertTicker alerts={openAlerts} />

            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Total Assets</p>
                <p className="text-xl font-bold text-white">{assets.length}</p>
                <p className="text-[11px] text-ink-subtle">{assets.filter(a => a.asset_type === 'dam').length} dams, {assets.filter(a => a.asset_type === 'barrage').length} barrages</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Active Alerts</p>
                <p className={`text-xl font-bold ${totalAlerts > 0 ? 'text-warn' : 'text-ok'}`}>{totalAlerts}</p>
                <p className="text-[11px] text-ink-subtle">{assetsWithAlerts} asset(s) flagged</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Avg Data Freshness</p>
                <p className="text-xl font-bold text-white">{avgFreshness > 0 ? `${Math.round(avgFreshness)}h` : '\u2014'}</p>
                <p className="text-[11px] text-ink-subtle">Across all assets</p>
              </Card>
              <Card className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Quick Access</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {QUICK_LINKS.map((ql) => (
                    <Link key={ql.href} href={ql.href}
                      className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-[10px] font-medium text-ink-muted hover:border-brand/25 hover:text-brand transition-colors"
                    >
                      <ql.icon className="h-3 w-3" />{ql.label}
                    </Link>
                  ))}
                </div>
              </Card>
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-ink">Infrastructure Status</h2>
                <Badge tone="sky">{assets.length} assets</Badge>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {assets.map((a) => (
                  <AssetCard key={a.id} asset={a} />
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {QUICK_LINKS.map((ql) => (
                <Link key={ql.href} href={ql.href}>
                  <Card className="group cursor-pointer transition-all hover:border-brand/25">
                    <CardBody className="flex items-center gap-4 p-4">
                      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${ql.accent}`}>
                        <ql.icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-ink group-hover:text-brand transition-colors">{ql.label}</p>
                        <p className="text-[11px] text-ink-subtle truncate">Navigate to {ql.label.toLowerCase()}</p>
                      </div>
                    </CardBody>
                  </Card>
                </Link>
              ))}
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}
