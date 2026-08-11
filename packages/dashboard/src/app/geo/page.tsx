// packages/dashboard/src/app/geo/page.tsx
// GeoVision Overview - remote-sensing indices landing page.
'use client'

import { Satellite, SatelliteDish, Leaf, Droplets, Gauge, MapPin } from 'lucide-react'
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
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { cn } from '@/lib/utils'
import { fmtNumber, fmtDate } from '@/lib/format'

const VIOLET = 'bg-violet-500/10 text-violet-300'
const AMBER = 'bg-amber-500/10 text-amber-300'

interface DistrictScene {
  id: number
  name: string
  ndvi: number
  ndwi: number
  soilMoisture: number
  satellite: 'Landsat-9' | 'Sentinel-2'
  acquisitionDate: string
  severity: string
}

const scenes: DistrictScene[] = [
  { id: 1, name: 'Multan', ndvi: 0.62, ndwi: 0.31, soilMoisture: 34, satellite: 'Landsat-9', acquisitionDate: '2026-08-04', severity: 'Normal' },
  { id: 2, name: 'Hyderabad', ndvi: 0.48, ndwi: 0.24, soilMoisture: 28, satellite: 'Sentinel-2', acquisitionDate: '2026-08-03', severity: 'Moderate' },
  { id: 3, name: 'Peshawar', ndvi: 0.71, ndwi: 0.38, soilMoisture: 41, satellite: 'Sentinel-2', acquisitionDate: '2026-08-02', severity: 'Normal' },
  { id: 4, name: 'Quetta', ndvi: 0.18, ndwi: 0.05, soilMoisture: 12, satellite: 'Landsat-9', acquisitionDate: '2026-08-04', severity: 'Severe' },
  { id: 5, name: 'Sukkur', ndvi: 0.34, ndwi: 0.15, soilMoisture: 19, satellite: 'Landsat-9', acquisitionDate: '2026-08-01', severity: 'Stressed' },
  { id: 6, name: 'Lahore', ndvi: 0.66, ndwi: 0.35, soilMoisture: 39, satellite: 'Sentinel-2', acquisitionDate: '2026-08-03', severity: 'Normal' },
  { id: 7, name: 'Faisalabad', ndvi: 0.55, ndwi: 0.27, soilMoisture: 32, satellite: 'Sentinel-2', acquisitionDate: '2026-08-02', severity: 'Moderate' },
  { id: 8, name: 'Dera Ghazi Khan', ndvi: 0.29, ndwi: 0.11, soilMoisture: 15, satellite: 'Landsat-9', acquisitionDate: '2026-08-04', severity: 'Warning' },
  { id: 9, name: 'Khairpur', ndvi: 0.41, ndwi: 0.19, soilMoisture: 24, satellite: 'Landsat-9', acquisitionDate: '2026-08-01', severity: 'Moderate' },
  { id: 10, name: 'Gwadar', ndvi: 0.09, ndwi: -0.02, soilMoisture: 8, satellite: 'Sentinel-2', acquisitionDate: '2026-08-03', severity: 'Critical' },
]

const ndviSeries = [
  { month: 'Jan', ndvi: 0.21 },
  { month: 'Feb', ndvi: 0.27 },
  { month: 'Mar', ndvi: 0.36 },
  { month: 'Apr', ndvi: 0.45 },
  { month: 'May', ndvi: 0.41 },
  { month: 'Jun', ndvi: 0.32 },
  { month: 'Jul', ndvi: 0.38 },
  { month: 'Aug', ndvi: 0.49 },
  { month: 'Sep', ndvi: 0.55 },
  { month: 'Oct', ndvi: 0.46 },
  { month: 'Nov', ndvi: 0.33 },
  { month: 'Dec', ndvi: 0.24 },
]

export default function GeoOverviewPage() {
  const meanNdvi =
    scenes.reduce((s, d) => s + d.ndvi, 0) / scenes.length
  const meanNdwi =
    scenes.reduce((s, d) => s + d.ndwi, 0) / scenes.length
  const meanMoisture =
    scenes.reduce((s, d) => s + d.soilMoisture, 0) / scenes.length
  const latestDate = scenes[0].acquisitionDate

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="GeoVision Overview"
          description="Remote-sensing indices (NDVI/NDWI) for agricultural monitoring. (Simulation data — API-ready structure.)"
          badge={<Badge tone="slate">Simulation data</Badge>}
          icon={<Satellite className="h-6 w-6" />}
          accent={VIOLET}
          updatedAt={latestDate}
          action={
            <Link href="/geo/ndvi">
              <Badge tone="violet">NDVI Analysis →</Badge>
            </Link>
          }
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Mean NDVI"
            value={fmtNumber(meanNdvi, 2)}
            detail="National vegetation greenness"
            icon={Leaf}
            accent={VIOLET}
          />
          <KpiCard
            label="Scenes Available"
            value={scenes.length}
            detail="Landsat-9 + Sentinel-2"
            icon={SatelliteDish}
            accent={AMBER}
          />
          <KpiCard
            label="Mean NDWI"
            value={fmtNumber(meanNdwi, 2)}
            detail="Surface-water presence index"
            icon={Droplets}
            accent="bg-sky-500/10 text-sky-300"
          />
          <KpiCard
            label="Moisture Mean"
            value={`${fmtNumber(meanMoisture)}%`}
            detail="Topsoil moisture estimate"
            icon={Gauge}
            accent="bg-emerald-500/10 text-emerald-300"
          />
        </div>

        <Card>
          <CardHeader
            title="NDVI Time Series"
            subtitle="Mean monthly vegetation index across the season"
            icon={<Satellite className="h-5 w-5" />}
            accent={VIOLET}
            action={<Badge tone="violet">Jan – Dec</Badge>}
          />
          <CardBody>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={ndviSeries} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="ndviFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#a78bfa" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <RTooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }}
                    labelStyle={{ color: '#94a3b8' }}
                    formatter={(v: any, n: any) => [Number(v).toFixed(2), n]}
                  />
                  <Area type="monotone" dataKey="ndvi" stroke="#a78bfa" strokeWidth={2} fill="url(#ndviFill)" name="NDVI" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Satellite Scene Index"
            subtitle="Latest acquisition per district"
            icon={<MapPin className="h-5 w-5" />}
            accent={VIOLET}
            action={<Badge tone="violet">{scenes.length} scenes</Badge>}
          />
          <CardBody className="p-0">
            <div className="max-h-[460px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <Th>District</Th>
                    <Th>NDVI</Th>
                    <Th>NDWI</Th>
                    <Th>Severity</Th>
                    <Th>Satellite</Th>
                    <Th>Acquired</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {scenes.map((s) => (
                    <tr key={s.id} className="text-slate-300 hover:bg-slate-800/30">
                      <Td>
                        <Link href={`/geo/regions`} className="font-medium text-slate-100 hover:text-violet-300">
                          {s.name}
                        </Link>
                      </Td>
                      <Td><span className="font-semibold text-slate-100">{s.ndvi.toFixed(2)}</span></Td>
                      <Td>{s.ndwi.toFixed(2)}</Td>
                      <Td><SeverityBadge severity={s.severity} /></Td>
                      <Td><Badge tone="slate">{s.satellite}</Badge></Td>
                      <Td className="text-[11px] text-slate-500">{fmtDate(s.acquisitionDate)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-4 py-2.5 font-medium">{children}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn('px-4 py-2.5 text-xs', className)}>{children}</td>
}