// packages/dashboard/src/app/water/indicators/page.tsx
// AquaVision Indicators - detailed weekly metric table & sparkline.
'use client'

import { useState } from 'react'
import { Activity, TrendingDown } from 'lucide-react'
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
import { useWaterIndicators, useWaterRegions } from '@/features/water/hooks'
import { regionNameById } from '@/features/water/mappers'
import { fmtNumber, fmtPct, fmtDate } from '@/lib/format'
import { normalizeSeverity } from '@/lib/severity'

export default function IndicatorsPage() {
  const regionsQuery = useWaterRegions()
  const indicatorsQuery = useWaterIndicators({ limit: 500 })
  const [regionId, setRegionId] = useState<string>('all')

  const regions = regionsQuery.data ?? []
  const indicators = indicatorsQuery.data ?? []

  const filtered = regionId === 'all' ? indicators : indicators.filter((i) => i.regionId === Number(regionId))
  const regionName = regionId === 'all' ? 'All regions' : regionNameById(regions, Number(regionId))

  const chartData = [...filtered]
    .sort((a, b) => a.weekStart.localeCompare(b.weekStart))
    .slice(-24)
    .map((i) => ({
      week: i.weekStart,
      wai: i.waiScore,
      rain: i.rainfallMm30day,
      et: i.etMm8day,
      sev: normalizeSeverity(i.severity),
      i,
    }))

  const latest = chartData.at(-1)?.i

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Indicators"
          description="Weekly water availability index, rainfall, ET, and surface-water deltas."
          icon={<Activity className="h-6 w-6" />}
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

        {latest?.weekStart && <Badge tone="sky">Latest week {fmtDate(latest.weekStart)}</Badge>}

        <Card>
          <CardHeader
            title="WAI Trend"
            subtitle={regionName}
            icon={<TrendingDown className="h-5 w-5" />}
            accent="bg-sky-500/10 text-sky-300"
          />
          <CardBody>
            {indicatorsQuery.isPending ? (
              <Spinner />
            ) : indicatorsQuery.isError ? (
              <ErrorState onRetry={() => indicatorsQuery.refetch()} />
            ) : chartData.length === 0 ? (
              <EmptyState title="No indicators" message="Run the GEE fetch + ingest pipeline." />
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="waiFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
                    <RTooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(v: any, n: any) => [v, n]}
                    />
                    <Area type="monotone" dataKey="wai" stroke="#38bdf8" strokeWidth={2} fill="url(#waiFill)" name="WAI" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Weekly Detail" subtitle={`${regionName} · ${chartData.length} rows shown`} icon={<Activity className="h-5 w-5" />} accent="bg-sky-500/10 text-sky-300" />
          <CardBody className="p-0">
            {chartData.length === 0 ? (
              <div className="p-8"><EmptyState title="No rows" /></div>
            ) : (
              <div className="max-h-[480px] overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
                    <tr>
                      <Th>Week</Th><Th>WAI</Th><Th>Severity</Th><Th>Rain (30d)</Th><Th>Rain anom</Th><Th>ET (8d)</Th><Th>Δ surface water</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {[...chartData].reverse().map((d) => (
                      <tr key={d.i.id} className="text-slate-300 hover:bg-slate-800/30">
                        <Td>{fmtDate(d.week)}</Td>
                        <Td>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-100">{fmtNumber(d.wai)}</span>
                            <ProgressBar value={d.wai ?? 0} severity={d.sev} className="w-16" />
                          </div>
                        </Td>
                        <Td><SeverityBadge severity={d.sev} /></Td>
                        <Td>{fmtNumber(d.rain)} mm</Td>
                        <Td>{fmtPct(d.i.rainfallAnomaly)}</Td>
                        <Td>{fmtNumber(d.et)} mm</Td>
                        <Td>{fmtPct(d.i.surfaceWaterChangePct)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}

function Th({ children }: { children: string }) {
  return <th className="px-4 py-2.5 font-medium">{children}</th>
}
function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-4 py-2.5 text-xs">{children}</td>
}