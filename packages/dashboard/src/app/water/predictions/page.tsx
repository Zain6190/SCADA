// packages/dashboard/src/app/water/predictions/page.tsx
// AquaVision Predictions - 2-week ahead WAI forecast table.
'use client'

import { LineChart, Cpu } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { ProgressBar } from '@/components/ui/progress'
import { useWaterPredictions, useWaterRegions } from '@/features/water/hooks'
import { regionNameById, sortBySeverity } from '@/features/water/mappers'
import { fmtNumber, fmtDate } from '@/lib/format'

export default function PredictionsPage() {
  const predictionsQuery = useWaterPredictions()
  const regionsQuery = useWaterRegions()

  const predictions = sortBySeverity(predictionsQuery.data ?? [], (p) => p.predictedSeverity)
  const regions = regionsQuery.data ?? []

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Predictions"
          description="2-week-ahead WAI and severity forecasts served by the XGBoost pipeline."
          icon={<LineChart className="h-6 w-6" />}
          badge={<Badge tone="violet">model xgb-v1.0</Badge>}
        />

        <Card>
          <CardHeader
            title="Forecast Roster"
            subtitle={`${predictions.length} region forecasts · sorted by worst severity`}
            icon={<Cpu className="h-5 w-5" />}
            accent="bg-violet-500/10 text-violet-300"
          />
          <CardBody className="p-0">
            {predictionsQuery.isPending ? (
              <div className="p-8"><Spinner /></div>
            ) : predictionsQuery.isError ? (
              <div className="p-8"><ErrorState onRetry={() => predictionsQuery.refetch()} /></div>
            ) : predictions.length === 0 ? (
              <div className="p-8"><EmptyState title="No forecasts" message="Run predict_weekly.py to populate." /></div>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <Th>Region</Th><Th>Target Week</Th><Th>Predicted WAI</Th><Th>Severity</Th><Th>Confidence</Th><Th>Model</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {predictions.map((p) => (
                    <tr key={p.id} className="text-slate-300 hover:bg-slate-800/30">
                      <Td className="font-medium text-slate-100">{regionNameById(regions, p.regionId)}</Td>
                      <Td>{fmtDate(p.targetWeekStart)}</Td>
                      <Td>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{fmtNumber(p.predictedWaiScore)}</span>
                          <ProgressBar value={p.predictedWaiScore ?? 0} severity={p.predictedSeverity} className="w-16" />
                        </div>
                      </Td>
                      <Td><SeverityBadge severity={p.predictedSeverity} /></Td>
                      <Td>{p.confidence != null ? `${(p.confidence * 100).toFixed(0)}%` : '—'}</Td>
                      <Td><Badge tone="slate">{p.modelVersion}</Badge></Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
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
  return <td className={`px-4 py-2.5 text-xs ${className ?? ''}`}>{children}</td>
}