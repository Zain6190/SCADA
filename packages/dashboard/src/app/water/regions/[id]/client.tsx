'use client'

// packages/dashboard/src/app/water/regions/[id]/client.tsx
import { useParams } from 'next/navigation'
import { MapPin, TrendingUp, Bell, Activity } from 'lucide-react'
import Link from 'next/link'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RTooltip,
  CartesianGrid,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { ProgressBar } from '@/components/ui/progress'
import { useWaterIndicators, useWaterAlerts, useWaterPredictions, useWaterRegions } from '@/features/water/hooks'
import { regionNameById, sortBySeverity } from '@/features/water/mappers'
import { fmtNumber, fmtDate } from '@/lib/format'

export function RegionDetailClient() {
  const params = useParams<{ id: string }>()
  const id = Number(params.id)
  const indicatorsQuery = useWaterIndicators({ region_id: id, limit: 200 })
  const alertsQuery = useWaterAlerts({})
  const predictionsQuery = useWaterPredictions()
  const regionsQuery = useWaterRegions()

  const name = regionNameById(regionsQuery.data ?? [], id)
  const indicators = indicatorsQuery.data ?? []
  const sorted = [...indicators].sort((a, b) => a.weekStart.localeCompare(b.weekStart))
  const chart = sorted.map((i) => ({ week: i.weekStart, wai: i.waiScore, sev: i.severity }))
  const sortedAlerts = sortBySeverity((alertsQuery.data ?? []).filter((a) => a.regionId === id))
  const openAlerts = sortedAlerts.filter((a) => a.status !== 'Resolved')
  const regionPred = predictionsQuery.data?.find((p) => p.regionId === id)

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title={name}
          description={`Region #${id} · AquaVision monitoring`}
          icon={<MapPin className="h-6 w-6" />}
          badge={<Link href="/water/regions"><Badge tone="slate">← All regions</Badge></Link>}
        />

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader title="WAI History" subtitle={name} icon={<Activity className="h-5 w-5" />} accent="bg-sky-500/10 text-sky-300" />
            <CardBody>
              {indicatorsQuery.isPending ? (
                <Spinner />
              ) : chart.length === 0 ? (
                <EmptyState title="No indicators" message="No data for this region yet." />
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chart} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="rg" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#64748b' }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
                      <RTooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12 }} labelStyle={{ color: '#94a3b8' }} />
                      <Area type="monotone" dataKey="wai" stroke="#38bdf8" strokeWidth={2} fill="url(#rg)" name="WAI" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardBody>
          </Card>

          <div className="space-y-6">
            {regionPred && (
              <Card>
                <CardHeader title="2-Week Forecast" icon={<TrendingUp className="h-5 w-5" />} accent="bg-violet-500/10 text-violet-300" />
                <CardBody>
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-semibold text-slate-100">
                      WAI {fmtNumber(regionPred.predictedWaiScore)}
                    </span>
                    <SeverityBadge severity={regionPred.predictedSeverity} />
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">target {fmtDate(regionPred.targetWeekStart)}</p>
                  <div className="mt-3">
                    <ProgressBar value={regionPred.predictedWaiScore ?? 0} severity={regionPred.predictedSeverity} />
                  </div>
                  {regionPred.confidence != null && (
                    <p className="mt-2 text-xs text-slate-500">Confidence {(regionPred.confidence * 100).toFixed(0)}%</p>
                  )}
                </CardBody>
              </Card>
            )}

            <Card>
              <CardHeader title="Open Alerts" icon={<Bell className="h-5 w-5" />} accent="bg-amber-500/10 text-amber-300" />
              <CardBody>
                {openAlerts.length === 0 ? (
                  <p className="text-sm text-slate-500">No open alerts.</p>
                ) : (
                  <div className="space-y-3">
                    {openAlerts.map((a) => (
                      <Link href="/water/alerts" key={a.id} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 p-3 hover:border-slate-700">
                        <div>
                          <p className="text-sm font-medium text-slate-200">{a.alertType}</p>
                          <p className="text-[11px] text-slate-500">{fmtDate(a.weekStartDate)}</p>
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
      </div>
    </AppShell>
  )
}