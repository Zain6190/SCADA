// packages/dashboard/src/app/crop/historical/page.tsx
// CropVision Historical - multi-year yield trends by crop (simulation data).
'use client'

import { History, Wheat, TrendingUp, CalendarDays, Leaf } from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { fmtNumber } from '@/lib/format'

const CROP = 'bg-emerald-500/10 text-emerald-300'

interface SeasonPoint {
  year: number
  wheat: number
  rice: number
  cotton: number
  sugarcane: number
}

const SERIES: SeasonPoint[] = [
  { year: 2019, wheat: 2.6, rice: 2.1, cotton: 1.9, sugarcane: 2.8 },
  { year: 2020, wheat: 2.7, rice: 2.2, cotton: 1.8, sugarcane: 2.9 },
  { year: 2021, wheat: 2.8, rice: 2.3, cotton: 1.9, sugarcane: 3.0 },
  { year: 2022, wheat: 2.9, rice: 2.4, cotton: 2.0, sugarcane: 3.1 },
  { year: 2023, wheat: 3.0, rice: 2.2, cotton: 1.7, sugarcane: 3.0 },
  { year: 2024, wheat: 3.1, rice: 2.5, cotton: 1.9, sugarcane: 3.2 },
  { year: 2025, wheat: 3.0, rice: 2.6, cotton: 2.0, sugarcane: 3.3 },
  { year: 2026, wheat: 3.2, rice: 2.7, cotton: 2.1, sugarcane: 3.4 },
]

const LINKS = [
  { key: 'wheat', color: '#34d399' },
  { key: 'rice', color: '#a3e635' },
  { key: 'cotton', color: '#f59e0b' },
  { key: 'sugarcane', color: '#22d3ee' },
]

const latest = SERIES[SERIES.length - 1]
const avgLatestAll = (latest.wheat + latest.rice + latest.cotton + latest.sugarcane) / 4
const growth = ((latest.sugarcane - SERIES[0].sugarcane) / SERIES[0].sugarcane) * 100

const TOOLTIP_STYLE = {
  backgroundColor: '#0f172a',
  border: '1px solid #334155',
  borderRadius: 12,
  color: '#e2e8f0',
}

export default function HistoricalYieldPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Historical Yield"
          description="Long-run crop yield trends in tonnes per hectare, 2019–2026 (simulation data, API-ready structure)."
          accent={CROP}
          icon={<History className="h-6 w-6" />}
          badge={<Badge tone="slate">Simulation data</Badge>}
          updatedAt="2026-08-06T08:00:00"
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Seasons Covered" value={SERIES.length} detail="2019 – 2026 crop years" icon={CalendarDays} accent={CROP} />
          <KpiCard label="Crops Tracked" value={4} detail="Wheat, rice, cotton, sugarcane" icon={Wheat} accent="bg-teal-500/10 text-teal-300" />
          <KpiCard label="Latest Avg Yield" value={fmtNumber(avgLatestAll)} detail="Tonnes per hectare, 2026" icon={TrendingUp} accent={CROP} />
          <KpiCard
            label="Sugarcane Gain"
            value={`+${fmtNumber(growth, 0)}%`}
            detail="vs 2019 base season"
            icon={Leaf}
            accent="bg-cyan-500/10 text-cyan-300"
            trend={{ value: 'improving', positive: true }}
          />
        </div>

        <Card>
          <CardHeader
            title="Yield Trends by Crop"
            subtitle="Tonnes per hectare · 2019–2026"
            icon={<TrendingUp className="h-5 w-5" />}
            accent={CROP}
            action={<Badge tone="emerald">t/ha</Badge>}
          />
          <CardBody>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={SERIES} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="year" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#94a3b8' }} />
                <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
                {LINKS.map((line) => (
                  <Line
                    key={line.key}
                    type="monotone"
                    dataKey={line.key}
                    stroke={line.color}
                    strokeWidth={2}
                    dot={{ r: 2, fill: line.color }}
                    activeDot={{ r: 4 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Season Summary" subtitle="Latest-season snapshot by crop" icon={<Leaf className="h-5 w-5" />} accent={CROP} />
          <CardBody>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {LINKS.map((line) => {
                const point = latest[line.key as keyof SeasonPoint]
                return (
                  <div key={line.key} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                    <div className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: line.color }} />
                      <p className="text-xs font-medium capitalize text-slate-400">{line.key}</p>
                    </div>
                    <p className="mt-2 text-2xl font-semibold text-slate-100">{fmtNumber(point)}</p>
                    <p className="text-[11px] text-slate-500">t/ha · {latest.year}</p>
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