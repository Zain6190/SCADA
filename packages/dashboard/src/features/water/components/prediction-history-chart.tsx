'use client'

import { useMemo } from 'react'
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import type { AccuracyTimelinePoint } from '../types'

interface Props {
  data: AccuracyTimelinePoint[]
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '--'
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function AccuracyTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const predicted = payload.find((p: any) => p.dataKey === 'predicted')
  const actual = payload.find((p: any) => p.dataKey === 'actual')
  const meta = payload[0]?.payload

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-slate-400">{label}</p>
      <p style={{ color: '#a78bfa' }} className="font-mono">
        Predicted: {fmt(predicted?.value)}
      </p>
      <p style={{ color: '#38bdf8' }} className="font-mono">
        Actual: {fmt(actual?.value)}
      </p>
      {predicted && actual && (
        <>
          <div className="my-1 border-t border-slate-700" />
          <p className="font-mono text-slate-400">
            Error: {fmt(Math.abs(predicted.value - actual.value))}
          </p>
          {actual.value !== 0 && (
            <p className="font-mono text-slate-400">
              {((Math.abs(predicted.value - actual.value) / Math.abs(actual.value)) * 100).toFixed(1)}% off
            </p>
          )}
        </>
      )}
      {meta?.withinInterval != null && (
        <p className={`mt-1 font-medium ${meta.withinInterval ? 'text-emerald-400' : 'text-red-400'}`}>
          {meta.withinInterval ? 'Within interval' : 'Outside interval'}
        </p>
      )}
    </div>
  )
}

export default function PredictionHistoryChart({ data }: Props) {
  const chartData = useMemo(() => {
    return data
      .filter((d) => d.predicted_value != null && d.actual_value != null)
      .map((d) => ({
        date: formatDate(d.date),
        predicted: d.predicted_value,
        actual: d.actual_value,
        withinInterval: d.withinInterval ?? d.within_interval,
        directionCorrect: d.direction_correct,
        modelVersion: d.model_version,
      }))
  }, [data])

  if (chartData.length === 0) {
    return (
      <Card>
        <CardBody className="flex h-80 items-center justify-center text-slate-500">
          No accuracy data available for the selected filters.
        </CardBody>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">Predicted vs Actual</h3>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-full bg-violet-400" />
            <span className="text-slate-400">Predicted</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded-full bg-sky-400" />
            <span className="text-slate-400">Actual</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-5 rounded bg-red-400/20" />
            <span className="text-slate-400">Error</span>
          </span>
        </div>
      </CardHeader>
      <CardBody>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <defs>
                <linearGradient id="errorGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#64748b' }}
                tickLine={false}
                axisLine={{ stroke: '#334155' }}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#64748b' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
              />
              <Tooltip content={<AccuracyTooltip />} />
              <Area
                type="monotone"
                dataKey="predicted"
                stroke="none"
                fill="url(#errorGrad)"
                fillOpacity={1}
                activeDot={false}
              />
              <Area
                type="monotone"
                dataKey="actual"
                stroke="none"
                fill="#0f172a"
                fillOpacity={1}
                activeDot={false}
              />
              <Line
                type="monotone"
                dataKey="predicted"
                stroke="#a78bfa"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#a78bfa' }}
              />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#38bdf8' }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  )
}
