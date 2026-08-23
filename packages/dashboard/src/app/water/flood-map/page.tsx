'use client'

// packages/dashboard/src/app/water/flood-map/page.tsx
// AquaVision Flood Arrival Map - map left + sidebar right layout.
import { Map } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { FloodArrivalMapDynamic } from '@/features/water/flood-arrival-map-dynamic'
import { FloodMapSidebar } from '@/features/water/flood-map-sidebar'
import {
  useFloodMapState,
  DEFAULT_THRESHOLDS,
  ASSET_NAMES,
} from '@/features/water/use-flood-map-state'

export default function FloodMapPage() {
  const {
    loading, calculating, error,
    selectedAsset, setSelectedAsset,
    mobileSidebarOpen, setMobileSidebarOpen,
    layers, toggleLayer,
    timeSlider, setTimeSlider,
    simAssetId, setSimAssetId, simFlow, setSimFlow,
    displaySegments, totals, visibleSegments, simImpact,
    impactSummary,
    currentLevels, ffdWarnings, floodClassifications,
    ffdMarkers, impactMarkers,
  } = useFloodMapState()

  return (
    <AppShell>
      <div className="space-y-4">
        <PageHeader
          title="Flood Arrival Map"
          description="Real-time flood propagation across Pakistan's river network. Click assets to calculate downstream impact."
          icon={<Map className="h-6 w-6" />}
          action={
            <div className="flex items-center gap-2">
              {selectedAsset && (
                <button
                  onClick={() => setSelectedAsset(null)}
                  className="flex items-center gap-1 rounded-lg bg-sky-500/10 px-3 py-1.5 text-xs text-sky-400 hover:bg-sky-500/20 transition-colors"
                >
                  Back to Overview
                </button>
              )}
              <Badge tone="sky">{displaySegments.length} segments</Badge>
            </div>
          }
        />

        <div className="relative">
          <div className="flex gap-0 rounded-2xl border border-slate-800 overflow-hidden" style={{ height: 'calc(100vh - 220px)', minHeight: '600px' }}>
            <div className="flex-1 relative">
              {loading ? (
                <div className="flex h-full items-center justify-center bg-slate-950">
                  <Spinner label="Loading flood map" />
                </div>
              ) : error ? (
                <div className="flex h-full items-center justify-center bg-slate-950">
                  <ErrorState message={error} />
                </div>
              ) : (
                <FloodArrivalMapDynamic
                  segments={displaySegments}
                  selectedAssetId={selectedAsset}
                  onAssetClick={setSelectedAsset}
                  height={800}
                  assetThresholds={DEFAULT_THRESHOLDS}
                  currentLevels={currentLevels}
                  ffdWarnings={ffdWarnings}
                  floodClassifications={floodClassifications}
                  ffdMarkers={ffdMarkers}
                  impactMarkers={impactMarkers}
                  showRivers={layers.showRivers}
                  showLabels={layers.showLabels}
                  showWarnings={layers.showWarnings}
                  showImpact={layers.showImpact}
                  showRainfall={layers.showRainfall}
                  showFloodExtents={layers.showFloodExtents}
                  timeSlider={timeSlider}
                  simulationFlow={selectedAsset ? null : { assetId: simAssetId, flow: simFlow }}
                />
              )}
            </div>

            {/* Desktop sidebar */}
            <div className="w-[280px] flex-shrink-0 hidden lg:block">
              <FloodMapSidebar
                timeSlider={timeSlider}
                onTimeSliderChange={setTimeSlider}
                showRivers={layers.showRivers}
                showLabels={layers.showLabels}
                showWarnings={layers.showWarnings}
                showImpact={layers.showImpact}
                showRainfall={layers.showRainfall}
                showFloodExtents={layers.showFloodExtents}
                onToggleLayer={toggleLayer}
                totalPopulation={totals.population}
                totalBridges={totals.bridges}
                totalHospitals={totals.hospitals}
                visibleSegments={visibleSegments.length}
                totalSegments={displaySegments.length}
                selectedAssetId={selectedAsset}
                impactSummary={impactSummary}
                calculating={calculating}
                onClearSelection={() => setSelectedAsset(null)}
                simAssetId={simAssetId}
                simFlow={simFlow}
                onSimAssetChange={setSimAssetId}
                onSimFlowChange={setSimFlow}
                simImpact={simImpact}
                assetNames={ASSET_NAMES}
              />
            </div>
          </div>

          {/* Mobile sidebar toggle */}
          <button
            onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
            className="lg:hidden fixed bottom-6 right-6 z-[1001] flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/95 px-4 py-3 text-xs font-medium text-slate-200 shadow-xl backdrop-blur hover:bg-slate-800 transition-colors"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
            Controls
          </button>

          {/* Mobile sidebar overlay */}
          {mobileSidebarOpen && (
            <div className="lg:hidden fixed inset-0 z-[1000]">
              <div className="absolute inset-0 bg-black/50" onClick={() => setMobileSidebarOpen(false)} />
              <div className="absolute right-0 top-0 bottom-0 w-[300px]">
                <FloodMapSidebar
                  timeSlider={timeSlider}
                  onTimeSliderChange={setTimeSlider}
                  showRivers={layers.showRivers}
                  showLabels={layers.showLabels}
                  showWarnings={layers.showWarnings}
                  showImpact={layers.showImpact}
                  showRainfall={layers.showRainfall}
                  showFloodExtents={layers.showFloodExtents}
                  onToggleLayer={toggleLayer}
                  totalPopulation={totals.population}
                  totalBridges={totals.bridges}
                  totalHospitals={totals.hospitals}
                  visibleSegments={visibleSegments.length}
                  totalSegments={displaySegments.length}
                  selectedAssetId={selectedAsset}
                  impactSummary={impactSummary}
                  calculating={calculating}
                  onClearSelection={() => { setSelectedAsset(null); setMobileSidebarOpen(false) }}
                  simAssetId={simAssetId}
                  simFlow={simFlow}
                  onSimAssetChange={setSimAssetId}
                  onSimFlowChange={setSimFlow}
                  simImpact={simImpact}
                  assetNames={ASSET_NAMES}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
