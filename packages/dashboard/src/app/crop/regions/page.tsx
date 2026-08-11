// packages/dashboard/src/app/crop/regions/page.tsx
// CropVision Regions - seasonal forecast by administrative region (simulation data).
'use client'

import { MapPin, TrendingUp, Gauge } from 'lucide-react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { fmtNumber } from '@/lib/format'

const CROP = 'bg-emerald-500/10 text-emerald-300'

type RegionSeverity = 'Normal' | 'Moderate' | 'Stressed' | 'Severe'

interface ForecastRegion {
  id: string
  name: string
  primaryCrop: string
  areaHa: number
  forecastTPerHa: number
  severity: RegionSeverity
  healthy: boolean
  trend: number[]
}

const REGIONS: ForecastRegion[] = [
  { id: 'pb', name: 'Punjab', primaryCrop: 'Wheat', areaHa: 6_920_000, forecastTPerHa: 3.1, severity: 'Normal', healthy: true, trend: [2.6, 2.8, 2.9, 3.0, 3.1] },
  { id: 'sd', name: 'Sindh', primaryCrop: 'Rice', areaHa: 2_060_000, forecastTPerHa: 2.5, severity: 'Moderate', healthy: true, trend: [2.1, 2.2, 2.2, 2.4, 2.5] },
  { id: 'kp', name: 'Khyber Pakhtunkhwa', primaryCrop: 'Sugarcane', areaHa: 930_000, forecastTPerHa: 2.1, severity: 'Stressed', healthy: false, trend: [2.4, 2.3, 2.2, 2.1, 2.1] },
  { id: 'bl', name: 'Balochistan', primaryCrop: 'Wheat', areaHa: 800_000, forecastTPerHa: 1.4, severity: 'Severe', healthy: false, trend: [1.8, 1.7, 1.6, 1.5, 1.4] },
]

const healthyCount = REGIONS.filter((r) => r.healthy).length
const avgForecast = REGIONS.reduce((s, r) => s + r.forecastTPerHa, 0) / REGIONS.length

const TOOLTIP_STYLE = {
  backgroundColor: '#0f172a',
  border: '1px solid #334155',
  borderRadius: 12,
  color: '#e2e8f0',
}

export default function CropRegionsPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Regional Crop Forecast"
          description="Seasonal yield forecast and crop-health status per province (simulation data, API-ready structure)."
          accent={CROP}
          icon={<MapPin className="h-6 w-6" />}
          badge={<Badge tone="slate">Simulation data</Badge>}
          updatedAt="2026-08-06T08:00:00"
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Regions Forecast" value={REGIONS.length} detail="Provincial administrative areas" icon={MapPin} accent={CROP} />
          <KpiCard label="Healthy Regions" value={healthyCount} detail="Within nominal NDVI band" icon={Gauge} accent="bg-teal-500/10 text-teal-300" />
          <KpiCard label="Avg Forecast" value={fmtNumber(avgForecast)} detail="Tonnes per hectare" icon={TrendingUp} accent={CROP} />
          <KpiCard label="Total Area" value={`${(REGIONS.reduce((s, r) => s + r.areaHa, 0) / 1_000_000).toFixed(1)}M`} detail="Hectares under crop cover" icon={Gauge} accent="bg-emerald-500/10 text-emerald-300" />
        </div>

        <Card>
          <CardHeader
            title="Forecast by Region"
            subtitle="Current season yield forecast in tonnes per hectare"
            icon={<TrendingUp className="h-5 w-5" />}
            accent={CROP}
            action={<Badge tone="emerald">Kharif 2026</Badge>}
          />
          <CardBody className="p-0">
            <div className="divide-y divide-slate-800/70">
              {REGIONS.map((region) => {
                const trendData = region.trend.map((v, i) => ({ season: `S${i + 1}`, value: v }))
                return (
                  <div key={region.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-200">{region.name}</p>
                      <p className="text-[11px] text-slate-500">{region.primaryCrop} · {region.areaHa.toLocaleString()} ha</p>
                    </div>

                    <div className="hidden h-12 w-32 sm:block">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={trendData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
                          <defs>
                            <linearGradient id={`trend-${region.id}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={region.healthy ? '#34d399' : '#f59e0b'} stopOpacity={0.35} />
                              <stop offset="100%" stopColor={region.healthy ? '#34d399' : '#f59e0b'} stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <Area type="monotone" dataKey="value" stroke={region.healthy ? '#34d399' : '#f59e0b'} strokeWidth={2} fill={`url(#trend-${region.id})`} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>

                    <div className="text-right">
                      <p className="text-sm font-semibold text-slate-100">{fmtNumber(region.forecastTPerHa)} <span className="text-[11px] font-normal text-slate-500">t/ha</span></p>
                    </div>

                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={region.severity} />
                      <Badge tone={region.healthy ? 'emerald' : 'amber'}>{region.healthy ? 'Healthy' : 'At risk'}</Badge>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}