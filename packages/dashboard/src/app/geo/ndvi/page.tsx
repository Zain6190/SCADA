// packages/dashboard/src/app/geo/ndvi/page.tsx
// GeoVision NDVI Analysis - vegetation greenness trends and scale.
'use client'

import { useEffect, useMemo, useState } from 'react'
import { Leaf, Activity, Layers } from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RTooltip,
  CartesianGrid,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { ProgressBar } from '@/components/ui/progress'
import { fmtNumber } from '@/lib/format'
import { waterApi } from '@/features/water/api'
import { EmptyState } from '@/components/ui/state'

const VIOLET = 'bg-brand-soft text-brand'

const ndviBands = [
  { label: 'Bare / water', range: '< 0.1', color: '#ef4444' },
  { label: 'Sparse vegetation', range: '0.2 – 0.4', color: '#facc15' },
  { label: 'Moderate vegetation', range: '0.4 – 0.6', color: '#84cc16' },
  { label: 'Dense vegetation', range: '> 0.6', color: '#22c55e' },
]

function ndviSeverity(value: number): string {
  if (value < 0.2) return 'Severe'
  if (value < 0.4) return 'Stressed'
  if (value < 0.6) return 'Moderate'
  return 'Normal'
}

export default function NdviAnalysisPage() {
  const [latest, setLatest] = useState<any[]>([])
  const [history, setHistory] = useState<any[]>([])

  useEffect(() => {
    waterApi.getNdvi()
      .then((payload) => {
        setLatest(payload?.latest || [])
        setHistory(payload?.history || [])
      })
      .catch(() => {
        setLatest([])
        setHistory([])
      })
  }, [])

  const chartRows = useMemo(() => {
    const byMonth = new Map<string, { month: string; ndvi: number; count: number }>()
    for (const row of history) {
      const current = byMonth.get(row.month) || { month: row.month, ndvi: 0, count: 0 }
      current.ndvi += Number(row.ndvi)
      current.count += 1
      byMonth.set(row.month, current)
    }
    return Array.from(byMonth.values())
      .sort((a, b) => a.month.localeCompare(b.month))
      .map((row) => ({ month: row.month.slice(0, 7), ndvi: row.ndvi / row.count }))
  }, [history])

  const imageWeek = latest[0]?.month
  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="NDVI Analysis"
          description="Sentinel-2 NDVI for the districts published by the weekly satellite fetch."
          badge={<Badge tone="slate">{imageWeek ? `Image week ${imageWeek}` : 'Awaiting fetch'}</Badge>}
          icon={<Leaf className="h-6 w-6" />}
          accent={VIOLET}
        />

        <Card>
          <CardHeader
            title="District NDVI"
            subtitle="Mean Sentinel-2 NDVI across the published districts"
            icon={<Activity className="h-5 w-5" />}
            accent={VIOLET}
            action={<Badge tone="violet">{chartRows.length ? `${chartRows.length} months` : 'No rows'}</Badge>}
          />
          <CardBody>
            <div className="h-72">
              {chartRows.length === 0 ? (
                <EmptyState title="No Sentinel-2 NDVI yet" message="The weekly Earth Engine fetch has not written district NDVI." />
              ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartRows} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis domain={[-0.2, 1]} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <RTooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }}
                    labelStyle={{ color: '#94a3b8' }}
                    formatter={(v: any) => [Number(v).toFixed(2), 'NDVI']}
                  />
                  <Line type="monotone" dataKey="ndvi" stroke="#a78bfa" strokeWidth={2} dot={false} name="NDVI" />
                </LineChart>
              </ResponsiveContainer>
              )}
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
              <div className="flex items-center justify-between text-[11px] text-ink-subtle">
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
                  <div key={b.label} className="flex items-center justify-between rounded-xl border border-line bg-canvas px-4 py-3">
                    <div className="flex items-center gap-3">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: b.color }} />
                      <span className="text-sm font-medium text-ink">{b.label}</span>
                    </div>
                    <span className="text-xs text-ink-subtle">{b.range}</span>
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
              action={<Badge tone="violet">{latest.length} districts</Badge>}
            />
            <CardBody>
              {latest.length === 0 ? (
                <EmptyState title="No district NDVI" message="Published Sentinel-2 rows will appear here after the weekly fetch." />
              ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {latest.map((d) => (
                  <div key={d.region_id} className="rounded-xl border border-line bg-canvas p-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-ink">{d.name}</p>
                      <SeverityBadge severity={ndviSeverity(Number(d.ndvi))} />
                    </div>
                    <p className="mt-2 text-2xl font-semibold text-ink">
                      {fmtNumber(d.ndvi, 2)}
                    </p>
                    <div className="mt-2">
                      <ProgressBar value={Math.max(0, Number(d.ndvi))} max={1} severity={ndviSeverity(Number(d.ndvi))} />
                    </div>
                  </div>
                ))}
              </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}