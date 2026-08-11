// packages/dashboard/src/app/water/map/page.tsx
// AquaVision Live Map - full-screen choropleth.
'use client'

import { useState } from 'react'
import { Map } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useWaterMapData } from '@/features/water/hooks'
import { WaterMapDynamic } from '@/features/water/water-map-dynamic'
import { normalizeSeverity } from '@/lib/severity'
import { fmtNumber } from '@/lib/format'

export default function WaterMapPage() {
  const mapData = useWaterMapData()
  const [selected, setSelected] = useState<any | null>(null)

  const features = mapData.data ?? []

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="AquaVision Live Map"
          description="District-level WAI severity choropleth for the latest observed week."
          icon={<Map className="h-6 w-6" />}
          action={
            features.length ? (
              <Badge tone="sky">{features.length} regions rendered</Badge>
            ) : undefined
          }
        />

        {mapData.isPending ? (
          <div className="flex h-[480px] items-center justify-center"><Spinner label="Loading map" /></div>
        ) : mapData.isError ? (
          <ErrorState onRetry={() => mapData.refetch()} message="Could not reach AquaVision service." />
        ) : features.length === 0 ? (
          <EmptyState title="No map regions" message="Run the GEE fetch + ingest pipeline to populate geometry." />
        ) : (
          <Card className="overflow-hidden p-3">
            <WaterMapDynamic features={features} height={560} onSelect={setSelected} />
            {selected && (
              <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Region</p>
                  <p className="text-sm font-semibold text-slate-100">{selected.name}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">WAI</p>
                  <p className="text-sm font-semibold text-slate-100">{fmtNumber(selected.waiScore)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Severity</p>
                  <SeverityBadge severity={selected.severity} className="mt-0.5" />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">Rainfall (30d)</p>
                  <p className="text-sm font-semibold text-slate-100">{fmtNumber(selected.rainfallMm30day)} mm</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-500">ET (8d)</p>
                  <p className="text-sm font-semibold text-slate-100">{fmtNumber(selected.etMm8day)} mm</p>
                </div>
              </div>
            )}
          </Card>
        )}
      </div>
    </AppShell>
  )
}