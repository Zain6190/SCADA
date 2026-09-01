'use client'

import { useState } from 'react'
import { LineChart, RefreshCw } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardBody } from '@/components/ui/card'
import { Spinner } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useQuery } from '@tanstack/react-query'
import PredictionHistoryChart from '@/features/water/components/prediction-history-chart'
import PredictionAccuracyStats from '@/features/water/components/prediction-accuracy-stats'

const ASSETS: Record<number, string> = {
  1: 'Tarbela', 2: 'Mangla', 3: 'Chashma', 4: 'Kalabagh',
  5: 'Taunsa', 6: 'Guddu', 7: 'Sukkur', 8: 'Kotri',
  9: 'Kabul @ Nowshera', 10: 'Chenab @ Marala', 11: 'Panjnad',
}
const ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
const HORIZONS = [7, 14, 30]
const DAYS_OPTIONS = [30, 60, 90, 180]

export default function PredictionHistoryPage() {
  const [assetId, setAssetId] = useState(1)
  const [horizon, setHorizon] = useState(7)
  const [days, setDays] = useState(90)

  const { data: timeline = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ['accuracy-timeline', assetId, horizon, days],
    queryFn: () => waterApi.getAccuracyTimeline(assetId, { horizon, days }),
    staleTime: 5 * 60_000,
  })

  return (
    <AppShell>
      <PageHeader
        title="Prediction History"
        subtitle="How past predictions compared to actual outcomes"
        icon={<LineChart className="h-6 w-6" />}
      />

      <div className="space-y-4">
        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={assetId}
            onChange={(e) => setAssetId(Number(e.target.value))}
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
          >
            {ASSET_IDS.map((id) => (
              <option key={id} value={id}>{ASSETS[id]}</option>
            ))}
          </select>

          <select
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
          >
            {HORIZONS.map((h) => (
              <option key={h} value={h}>{h}-day</option>
            ))}
          </select>

          <div className="flex gap-1">
            {DAYS_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors ${
                  days === d
                    ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                    : 'text-slate-500 hover:text-slate-300 border border-transparent'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm text-slate-200"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          {timeline.length > 0 && (
            <span className="text-xs text-slate-500 ml-auto">
              {timeline.length} data points
            </span>
          )}
        </div>

        {/* Stats */}
        <PredictionAccuracyStats data={timeline} />

        {/* Chart */}
        {isLoading ? (
          <Card>
            <CardBody className="flex h-80 items-center justify-center">
              <Spinner label="Loading accuracy timeline..." />
            </CardBody>
          </Card>
        ) : (
          <PredictionHistoryChart data={timeline} />
        )}
      </div>
    </AppShell>
  )
}
