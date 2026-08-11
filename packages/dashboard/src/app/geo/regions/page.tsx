// packages/dashboard/src/app/geo/regions/page.tsx
// GeoVision Regional Index - quarterly NDVI by region.
'use client'

import { MapPin, TrendingUp } from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
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
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { fmtNumber, fmtDate } from '@/lib/format'
import { ListOrdered } from 'lucide-react'

const VIOLET = 'bg-violet-500/10 text-violet-300'

interface Region {
  id: number
  name: string
  sensor: 'Landsat-9' | 'Sentinel-2'
  lastNdvi: number
  severity: string
  acquisitionDate: string
  q1: number
  q2: number
  q3: number
  q4: number
  status: string
}

const regions: Region[] = [
  { id: 1, name: 'Punjab — Punjab Core', sensor: 'Sentinel-2', lastNdvi: 0.62, severity: 'Normal', acquisitionDate: '2026-08-04', q1: 0.34, q2: 0.52, q3: 0.41, q4: 0.58, status: 'Green wave' },
  { id: 2, name: 'Sindh — Lower Indus', sensor: 'Landsat-9', lastNdvi: 0.44, severity: 'Moderate', acquisitionDate: '2026-08-03', q1: 0.29, q2: 0.46, q3: 0.38, q4: 0.43, status: 'Seasonal dryback' },
  { id: 3, name: 'KPK — Swat Valley', sensor: 'Sentinel-2', lastNdvi: 0.71, severity: 'Normal', acquisitionDate: '2026-08-02', q1: 0.47, q2: 0.63, q3: 0.68, q4: 0.66, status: 'Dense cover' },
  { id: 4, name: 'Balochistan — Quetta', sensor: 'Landsat-9', lastNdvi: 0.16, severity: 'Severe', acquisitionDate: '2026-08-04', q1: 0.14, q2: 0.21, q3: 0.12, q4: 0.15, status: 'Arid stress' },
  { id: 5, name: 'Punjab — Thal', sensor: 'Landsat-9', lastNdvi: 0.31, severity: 'Warning', acquisitionDate: '2026-08-01', q1: 0.19, q2: 0.34, q3: 0.26, q4: 0.3, status: 'Moisture limited' },
]

const chartData = regions.map((r) => ({
  name: r.name.split('—')[1]?.trim() ?? r.name,
  Q1: r.q1,
  Q2: r.q2,
  Q3: r.q3,
  Q4: r.q4,
}))

export default function RegionalIndexPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Regional Remote-Sensing Index"
          description="Quarterly NDVI aggregation per agricultural region, with current sensor status."
          badge={<Badge tone="slate">Simulation data</Badge>}
          icon={<TrendingUp className="h-6 w-6" />}
          accent={VIOLET}
        />

        <Card>
          <CardHeader
            title="NDVI by Quarter"
            subtitle="Regional vegetation index across the year"
            icon={<ListOrdered className="h-5 w-5" />}
            accent={VIOLET}
            action={<Badge tone="violet">Q1 – Q4</Badge>}
          />
          <CardBody>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} interval={0} angle={-12} textAnchor="end" height={50} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <RTooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }}
                    labelStyle={{ color: '#94a3b8' }}
                    formatter={(v: any, n: any) => [Number(v).toFixed(2), n]}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
                  <Bar dataKey="Q1" fill="#a78bfa" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Q2" fill="#34d399" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Q3" fill="#fbbf24" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Q4" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Region Summary"
            subtitle="Latest index, sensor, and acquisition per region"
            icon={<MapPin className="h-5 w-5" />}
            accent={VIOLET}
            action={<Badge tone="violet">{regions.length} regions</Badge>}
          />
          <CardBody className="p-0">
            <div className="max-h-[460px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <Th>Region</Th>
                    <Th>Sensor</Th>
                    <Th>Last NDVI</Th>
                    <Th>Severity</Th>
                    <Th>Acquired</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {regions.map((r) => (
                    <tr key={r.id} className="text-slate-300 hover:bg-slate-800/30">
                      <Td>
                        <p className="font-medium text-slate-100">{r.name}</p>
                        <p className="text-[11px] text-slate-500">{r.status}</p>
                      </Td>
                      <Td><Badge tone="slate">{r.sensor}</Badge></Td>
                      <Td><span className="font-semibold text-slate-100">{fmtNumber(r.lastNdvi, 2)}</span></Td>
                      <Td><SeverityBadge severity={r.severity} /></Td>
                      <Td className="text-[11px] text-slate-500">{fmtDate(r.acquisitionDate)}</Td>
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