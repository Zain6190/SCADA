'use client'

import { useMemo } from 'react'
import { Target, TrendingDown, Percent, Compass, ShieldCheck } from 'lucide-react'
import { Card, CardBody } from '@/components/ui/card'
import type { AccuracyTimelinePoint } from '../types'

interface Props {
  data: AccuracyTimelinePoint[]
}

function StatCard({ label, value, icon: Icon, color }: {
  label: string
  value: string
  icon: any
  color: string
}) {
  return (
    <Card>
      <CardBody className="p-4 text-center">
        <Icon className={`w-5 h-5 ${color} mx-auto mb-1`} />
        <div className="text-2xl font-bold text-slate-100">{value}</div>
        <div className="text-xs text-slate-400">{label}</div>
      </CardBody>
    </Card>
  )
}

export default function PredictionAccuracyStats({ data }: Props) {
  const stats = useMemo(() => {
    const valid = data.filter((d) => d.actual_value != null && d.predicted_value != null)
    if (valid.length === 0) return null

    const errors = valid.map((d) => (d.actual_value ?? 0) - (d.predicted_value ?? 0))
    const absErrors = errors.map(Math.abs)
    const pctErrors = valid
      .filter((d) => d.pct_error != null)
      .map((d) => d.pct_error!)

    const mae = absErrors.reduce((a, b) => a + b, 0) / absErrors.length
    const mse = errors.reduce((a, b) => a + b * b, 0) / errors.length
    const rmse = Math.sqrt(mse)
    const mape = pctErrors.length > 0
      ? pctErrors.reduce((a, b) => a + b, 0) / pctErrors.length
      : null
    const dirCorrect = valid.filter((d) => d.direction_correct === true).length
    const withinInterval = valid.filter((d) => d.within_interval === true).length

    return {
      mae,
      rmse,
      mape,
      directionAccuracy: ((dirCorrect / valid.length) * 100).toFixed(0),
      intervalPct: ((withinInterval / valid.length) * 100).toFixed(0),
      sampleCount: valid.length,
    }
  }, [data])

  if (!stats) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {['MAE', 'RMSE', 'MAPE', 'Direction', 'In Interval'].map((label) => (
          <Card key={label}>
            <CardBody className="p-4 text-center">
              <div className="text-2xl font-bold text-slate-600">--</div>
              <div className="text-xs text-slate-500">{label}</div>
            </CardBody>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      <StatCard
        label="MAE"
        value={stats.mae >= 1000 ? `${(stats.mae / 1000).toFixed(1)}k` : stats.mae.toFixed(0)}
        icon={Target}
        color="text-sky-400"
      />
      <StatCard
        label="RMSE"
        value={stats.rmse >= 1000 ? `${(stats.rmse / 1000).toFixed(1)}k` : stats.rmse.toFixed(0)}
        icon={TrendingDown}
        color="text-violet-400"
      />
      <StatCard
        label="MAPE"
        value={stats.mape != null ? `${stats.mape.toFixed(1)}%` : '--'}
        icon={Percent}
        color="text-amber-400"
      />
      <StatCard
        label="Direction"
        value={`${stats.directionAccuracy}%`}
        icon={Compass}
        color="text-emerald-400"
      />
      <StatCard
        label="In Interval"
        value={`${stats.intervalPct}%`}
        icon={ShieldCheck}
        color="text-emerald-400"
      />
    </div>
  )
}
