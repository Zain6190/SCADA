// packages/dashboard/src/app/crop/page.tsx
// CropVision Overview - regional yield forecasts and crop health (simulation data).
'use client'

import { Sprout, MapPin, TrendingUp, AlertTriangle } from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
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
import { fmtNumber, fmtPct } from '@/lib/format'

const CROP = 'bg-emerald-500/10 text-emerald-300'

type RegionSeverity = 'Normal' | 'Moderate' | 'Stressed' | 'Severe'

interface Region {
  id: string
  name: string
  crop: string
  yieldTonnes: number
  yieldPerHectare: number
  ndvi: number
  severity: RegionSeverity
  changePct: number
  hectares: number
}

const REGIONS: Region[] = [
  { id: 'pb', name: 'Punjab', crop: 'Wheat', yieldTonnes: 21_440_000, yieldPerHectare: 3.1, ndvi: 0.72, severity: 'Normal', changePct: 4.2, hectares: 6_920_000 },
  { id: 'sd', name: 'Sindh', crop: 'Rice', yieldTonnes: 5_180_000, yieldPerHectare: 2.5, ndvi: 0.61, severity: 'Moderate', changePct: -1.8, hectares: 2_060_000 },
  { id: 'kp', name: 'Khyber Pakhtunkhwa', crop: 'Sugarcane', yieldTonnes: 1_940_000, yieldPerHectare: 2.1, ndvi: 0.54, severity: 'Stressed', changePct: -5.4, hectares: 930_000 },
  { id: 'bl', name: 'Balochistan', crop: 'Wheat', yieldTonnes: 1_120_000, yieldPerHectare: 1.4, ndvi: 0.38, severity: 'Severe', changePct: -9.7, hectares: 800_000 },
]

const avgYield = REGIONS.reduce((s, r) => s + r.yieldPerHectare, 0) / REGIONS.length
const ndviMean = REGIONS.reduce((s, r) => s + r.ndvi, 0) / REGIONS.length
const stressed = REGIONS.filter((r) => r.severity !== 'Normal').length

const TOOLTIP_STYLE = {
  backgroundColor: '#0f172a',
  border: '1px solid #334155',
  borderRadius: 12,
  color: '#e2e8f0',
}

export default function CropOverviewPage() {
  const chartData = REGIONS.map((r) => ({ name: r.name, yield: r.yieldPerHectare }))

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Crop Yield Overview"
          description="Regional yield forecasts and crop health (simulation data, API-ready structure)."
          accent={CROP}
          icon={<Sprout className="h-6 w-6" />}
          badge={<Badge tone="slate">Simulation data</Badge>}
          updatedAt="2026-08-06T08:00:00"
          action={<Badge tone="emerald">Kharif 2026</Badge>}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Avg Yield"
            value={fmtNumber(avgYield)}
            detail="Tonnes per hectare, all regions"
            icon={TrendingUp}
            accent={CROP}
          />
          <KpiCard
            label="Regions Tracked"
            value={REGIONS.length}
            detail={`${REGIONS.reduce((s, r) => s + r.hectares, 0).toLocaleString()} ha under cover`}
            icon={MapPin}
            accent={CROP}
          />
          <KpiCard
            label="NDVI Mean"
            value={fmtNumber(ndviMean, 2)}
            detail="Normalized Difference Vegetation Index"
            icon={Sprout}
            accent="bg-teal-500/10 text-teal-300"
          />
          <KpiCard
            label="Stressed Crops"
            value={stressed}
            detail="Regions below healthy threshold"
            icon={AlertTriangle}
            accent="bg-amber-500/10 text-amber-300"
          />
        </div>

        <Card>
          <CardHeader
            title="Forecast Yield by Region"
            subtitle="Estimated tonnes per hectare for the current season"
            icon={<TrendingUp className="h-5 w-5" />}
            accent={CROP}
            action={<Badge tone="emerald">t/ha</Badge>}
          />
          <CardBody>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: 'rgba(30,41,59,0.4)' }} contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#94a3b8' }} />
                <Bar dataKey="yield" fill="#34d399" radius={[6, 6, 0, 0]} maxBarSize={56} />
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Regional Crop Health"
            subtitle="NDVI, severity and yield trend by province"
            icon={<MapPin className="h-5 w-5" />}
            accent={CROP}
            action={<Badge tone="slate">{REGIONS.length} regions</Badge>}
          />
          <CardBody className="p-0">
            <div className="divide-y divide-slate-800/70">
              {REGIONS.map((region) => (
                <div key={region.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-200">{region.name}</p>
                    <p className="text-[11px] text-slate-500">{region.crop} · {region.hectares.toLocaleString()} ha</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-slate-400">NDVI <span className="font-semibold text-slate-100">{fmtNumber(region.ndvi, 2)}</span></p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs font-semibold ${region.changePct >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                      {fmtPct(region.changePct)}
                    </span>
                    <SeverityBadge severity={region.severity} />
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}
