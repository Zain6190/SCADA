// packages/dashboard/src/app/geo/ndvi/page.tsx
// GeoVision NDVI Analysis - vegetation greenness trends and scale.
'use client'

import { Leaf, Activity, Layers } from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
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
import { ProgressBar } from '@/components/ui/progress'
import { fmtNumber } from '@/lib/format'

const VIOLET = 'bg-violet-500/10 text-violet-300'

const cropSeries = [
  { month: 'Jan', wheat: 0.31, rice: 0.0, pasture: 0.18 },
  { month: 'Feb', wheat: 0.4, rice: 0.0, pasture: 0.22 },
  { month: 'Mar', wheat: 0.58, rice: 0.0, pasture: 0.3 },
  { month: 'Apr', wheat: 0.72, rice: 0.12, pasture: 0.44 },
  { month: 'May', wheat: 0.55, rice: 0.38, pasture: 0.51 },
  { month: 'Jun', wheat: 0.3, rice: 0.62, pasture: 0.46 },
  { month: 'Jul', wheat: 0.22, rice: 0.74, pasture: 0.39 },
  { month: 'Aug', wheat: 0.24, rice: 0.68, pasture: 0.36 },
  { month: 'Sep', wheat: 0.35, rice: 0.51, pasture: 0.42 },
  { month: 'Oct', wheat: 0.46, rice: 0.3, pasture: 0.5 },
  { month: 'Nov', wheat: 0.5, rice: 0.15, pasture: 0.47 },
  { month: 'Dec', wheat: 0.38, rice: 0.0, pasture: 0.35 },
]

const ndviBands = [
  { label: 'Bare / water', range: '< 0.1', color: '#ef4444' },
  { label: 'Sparse vegetation', range: '0.2 – 0.4', color: '#facc15' },
  { label: 'Moderate vegetation', range: '0.4 – 0.6', color: '#84cc16' },
  { label: 'Dense vegetation', range: '> 0.6', color: '#22c55e' },
]

const districtTiles = [
  { name: 'Multan', ndvi: 0.62, severity: 'Normal' },
  { name: 'Peshawar', ndvi: 0.71, severity: 'Normal' },
  { name: 'Lahore', ndvi: 0.66, severity: 'Normal' },
  { name: 'Faisalabad', ndvi: 0.55, severity: 'Moderate' },
  { name: 'Hyderabad', ndvi: 0.48, severity: 'Moderate' },
  { name: 'Khairpur', ndvi: 0.41, severity: 'Moderate' },
  { name: 'Sukkur', ndvi: 0.34, severity: 'Stressed' },
  { name: 'Dera Ghazi Khan', ndvi: 0.29, severity: 'Warning' },
  { name: 'Quetta', ndvi: 0.18, severity: 'Severe' },
  { name: 'Gwadar', ndvi: 0.09, severity: 'Critical' },
]

export default function NdviAnalysisPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="NDVI Analysis"
          description="Normalized Difference Vegetation Index — greenness and vegetation density from satellite imagery."
          badge={<Badge tone="slate">Simulation data</Badge>}
          icon={<Leaf className="h-6 w-6" />}
          accent={VIOLET}
        />

        <Card>
          <CardHeader
            title="Monthly NDVI by Crop"
            subtitle="Wheat, rice, and pasture growing cycles"
            icon={<Activity className="h-5 w-5" />}
            accent={VIOLET}
            action={<Badge tone="violet">Jan – Dec</Badge>}
          />
          <CardBody>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={cropSeries} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <RTooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }}
                    labelStyle={{ color: '#94a3b8' }}
                    formatter={(v: any, n: any) => [Number(v).toFixed(2), n]}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
                  <Line type="monotone" dataKey="wheat" stroke="#a78bfa" strokeWidth={2} dot={false} name="Wheat" />
                  <Line type="monotone" dataKey="rice" stroke="#34d399" strokeWidth={2} dot={false} name="Rice" />
                  <Line type="monotone" dataKey="pasture" stroke="#fbbf24" strokeWidth={2} dot={false} name="Pasture" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="NDVI Color Scale"
              subtitle="Standard red-to-green vegetation legend"
              icon={<Layers className="h-5 w-5" />}
              accent={VIOLET}
            />
            <CardBody>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>0.0</span>
                <span>0.5</span>
                <span>1.0</span>
              </div>
              <div
                className="mt-1 h-4 w-full rounded-full"
                style={{
                  background:
                    'linear-gradient(to right, #ef4444 0%, #facc15 35%, #84cc16 60%, #22c55e 100%)',
                }}
              />
              <div className="mt-5 space-y-3">
                {ndviBands.map((b) => (
                  <div key={b.label} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3">
                    <div className="flex items-center gap-3">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: b.color }} />
                      <span className="text-sm font-medium text-slate-200">{b.label}</span>
                    </div>
                    <span className="text-xs text-slate-500">{b.range}</span>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Latest NDVI by District"
              subtitle="Current scene greenness per district"
              icon={<Leaf className="h-5 w-5" />}
              accent={VIOLET}
              action={<Badge tone="violet">{districtTiles.length} districts</Badge>}
            />
            <CardBody>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {districtTiles.map((d) => (
                  <div key={d.name} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-200">{d.name}</p>
                      <SeverityBadge severity={d.severity} />
                    </div>
                    <p className="mt-2 text-2xl font-semibold text-slate-100">
                      {fmtNumber(d.ndvi, 2)}
                    </p>
                    <div className="mt-2">
                      <ProgressBar value={d.ndvi} max={1} severity={d.severity} />
                    </div>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}