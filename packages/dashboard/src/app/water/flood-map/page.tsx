'use client'

// packages/dashboard/src/app/water/flood-map/page.tsx
// AquaVision Flood Arrival Map - map left + sidebar right layout.
import { useState, useEffect } from 'react'
import { Map } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { FloodArrivalMapDynamic } from '@/features/water/flood-arrival-map-dynamic'
import { FloodMapSidebar } from '@/features/water/flood-map-sidebar'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8100'

interface SegmentData {
  from_id: number
  to_id: number
  river: string
  travel_time_hours: number
  distance_km: number
  population_exposed: number
  bridges: number
  hospitals: number
}

interface ImpactSummary {
  source_asset: string
  release_flow_cusecs: number
  total_population_exposed: number
  total_bridges: number
  total_hospitals: number
  total_travel_hours: number
  furthest_asset: string
  segments: Array<{
    segment_order: number
    river_name: string
    upstream_asset: string
    downstream_asset: string
    distance_km: number
    travel_time_hours: number
    population_exposed: number
    bridges_count: number
    hospitals_count: number
  }>
}

interface Alert {
  id: number
  asset_name: string
  severity: string
  message: string
  downstream_population_exposed?: number
}

const ASSET_MAP: Record<string, number> = {
  'Tarbela': 1, 'Mangla': 2, 'Chashma': 3, 'Kalabagh': 4,
  'Taunsa': 5, 'Guddu': 6, 'Sukkur': 7, 'Kotri': 8,
  'Kabul @ Nowshera': 9, 'Nowshera': 9, 'Chenab @ Marala': 10, 'Marala': 10,
  'Panjnad': 11,
}

const DEFAULT_THRESHOLDS: Record<number, { warning?: number; danger?: number; critical?: number }> = {
  1: { warning: 1550, danger: 1570, critical: 1600 },
  2: { warning: 1242, danger: 1248, critical: 1255 },
  9: { warning: 100000, danger: 150000, critical: 200000 },
  10: { warning: 80000, danger: 120000, critical: 160000 },
}

const ASSET_NAMES: Record<number, string> = {
  1: 'Tarbela', 2: 'Mangla', 3: 'Chashma', 4: 'Kalabagh',
  5: 'Taunsa', 6: 'Guddu', 7: 'Sukkur', 8: 'Kotri',
  9: 'Nowshera', 10: 'Marala', 11: 'Panjnad',
}

export default function FloodMapPage() {
  const [segments, setSegments] = useState<SegmentData[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null)
  const [impactSummary, setImpactSummary] = useState<ImpactSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentLevels, setCurrentLevels] = useState<Record<number, number>>({})
  const [ffdWarnings, setFfdWarnings] = useState<any[]>([])
  const [floodClassifications, setFloodClassifications] = useState<Record<number, { probability: number; severity: string; recommendation: string }>>({})
  const [ffdMarkers, setFfdMarkers] = useState<any[]>([])
  const [impactMarkers, setImpactMarkers] = useState<any[]>([])

  // Sidebar layer states
  const [showRivers, setShowRivers] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [showWarnings, setShowWarnings] = useState(true)
  const [showImpact, setShowImpact] = useState(true)
  const [showRainfall, setShowRainfall] = useState(false)
  const [showFloodExtents, setShowFloodExtents] = useState(false)

  // Sidebar controls
  const [timeSlider, setTimeSlider] = useState(48)
  const [simAssetId, setSimAssetId] = useState<number>(1)
  const [simFlow, setSimFlow] = useState<number>(100000)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  useEffect(() => {
    async function fetchData() {
      try {
        const [impRes, alertRes, levelsRes, ffdRes, markersRes] = await Promise.all([
          fetch(`${API_BASE}/water/impact/precalculated`),
          fetch(`${API_BASE}/water/operational/alerts?status=NEW`),
          fetch(`${API_BASE}/water/operational/assets`),
          fetch(`${API_BASE}/water/operational/ffd/markers`),
          fetch(`${API_BASE}/water/impact/markers`),
        ])

        if (impRes.ok) {
          const impacts = await impRes.json()
          const segs: SegmentData[] = impacts.map((imp: any) => ({
            from_id: imp.source_asset_id,
            to_id: imp.downstream_asset_id || imp.source_asset_id + 1,
            river: imp.notes?.includes('Indus') ? 'Indus' : imp.notes?.includes('Jhelum') ? 'Jhelum' : imp.notes?.includes('Kabul') ? 'Kabul' : imp.notes?.includes('Chenab') ? 'Chenab' : 'Indus',
            travel_time_hours: imp.travel_time_hours_expected || imp.travel_time_hours_min || 24,
            distance_km: imp.distance_km || 100,
            population_exposed: imp.affected_population_est || 0,
            bridges: imp.bridges_count || 0,
            hospitals: imp.hospitals_count || 0,
          }))
          setSegments(segs)
        }

        if (alertRes.ok) {
          const alertList = await alertRes.json()
          setAlerts(alertList)
          setFfdWarnings(alertList.map((a: any) => {
            const assetId = ASSET_MAP[a.asset_name] || a.asset_id
            const coords: Record<number, [number, number]> = {
              1: [34.086, 72.716], 2: [33.215, 73.640], 3: [32.485, 71.480],
              4: [32.960, 71.490], 5: [30.805, 70.880], 6: [28.430, 68.940],
              7: [27.690, 68.410], 8: [25.370, 68.350], 9: [34.010, 71.580],
              10: [32.480, 74.560], 11: [28.400, 69.700],
            }
            return {
              id: a.id,
              station: a.asset_name || 'Unknown',
              river: 'Indus',
              lat: coords[assetId]?.[0] || 30.5,
              lng: coords[assetId]?.[1] || 70.5,
              level_ft: a.reading_level_ft || 0,
              discharge_cusecs: a.reading_discharge_cusecs || a.triggered_value || 0,
              status: a.status || 'NEW',
              severity: a.severity || 'WATCH',
              issued_at: a.created_at || new Date().toISOString(),
            }
          }))
        }

        if (levelsRes.ok) {
          const assetsData = await levelsRes.json()
          const assetList = Array.isArray(assetsData) ? assetsData : []
          const levels: Record<number, number> = {}
          const classifications: Record<number, { probability: number; severity: string; recommendation: string }> = {}
          for (const asset of assetList) {
            if (asset.current_level_ft != null) levels[asset.id] = asset.current_level_ft
            else if (asset.current_discharge != null) levels[asset.id] = asset.current_discharge
            if (asset.flood_probability != null) {
              classifications[asset.id] = {
                probability: asset.flood_probability,
                severity: asset.flood_severity || 'NONE',
                recommendation: asset.flood_recommendation || '',
              }
            }
          }
          setCurrentLevels(levels)
          setFloodClassifications(classifications)
        }

        if (ffdRes.ok) {
          setFfdMarkers(await ffdRes.json())
        }

        if (markersRes.ok) {
          setImpactMarkers(await markersRes.json())
        }
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
    const iv = setInterval(fetchData, 30_000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    if (!selectedAsset) { setImpactSummary(null); return }
    async function calc() {
      setCalculating(true)
      try {
        let flow = 100000
        try {
          const flowRes = await fetch(`${API_BASE}/water/impact/latest-flow/${selectedAsset}`)
          if (flowRes.ok) {
            const flowData = await flowRes.json()
            flow = flowData.effective_flow || 100000
          }
        } catch {}

        const res = await fetch(`${API_BASE}/water/impact/calculate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_asset_id: selectedAsset,
            release_flow_cusecs: flow,
            release_time: new Date().toISOString(),
          }),
        })
        if (res.ok) setImpactSummary(await res.json())
      } catch {}
      setCalculating(false)
    }
    calc()
  }, [selectedAsset])

  const displaySegments = selectedAsset && impactSummary
    ? impactSummary.segments.map(s => ({
        from_id: ASSET_MAP[s.upstream_asset] || 1,
        to_id: ASSET_MAP[s.downstream_asset] || 1,
        river: s.river_name,
        travel_time_hours: s.travel_time_hours,
        distance_km: s.distance_km,
        population_exposed: s.population_exposed,
        bridges: s.bridges_count,
        hospitals: s.hospitals_count,
      }))
    : segments

  const totalPopulation = displaySegments.reduce((sum, s) => sum + s.population_exposed, 0)
  const totalBridges = displaySegments.reduce((sum, s) => sum + s.bridges, 0)
  const totalHospitals = displaySegments.reduce((sum, s) => sum + s.hospitals, 0)
  const maxTravel = Math.max(...displaySegments.map(s => s.travel_time_hours), 0)

  const visibleSegments = displaySegments.filter(s => s.travel_time_hours <= timeSlider)

  const simImpact = (() => {
    const downstream = segments.filter(s => s.from_id === simAssetId)
    if (!downstream.length) return null
    const scaleFactor = simFlow / 100000
    return {
      segments: downstream.length,
      population: Math.round(totalPopulation * scaleFactor),
      bridges: Math.round(totalBridges * scaleFactor),
      hospitals: Math.round(totalHospitals * scaleFactor),
      maxTravel: Math.max(...downstream.map(s => s.travel_time_hours)),
    }
  })()

  const handleToggleLayer = (layer: string) => {
    switch (layer) {
      case 'rivers': setShowRivers(!showRivers); break
      case 'labels': setShowLabels(!showLabels); break
      case 'warnings': setShowWarnings(!showWarnings); break
      case 'impact': setShowImpact(!showImpact); break
      case 'rainfall': setShowRainfall(!showRainfall); break
      case 'floodExtents': setShowFloodExtents(!showFloodExtents); break
    }
  }

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

        {/* Map + Sidebar layout */}
        <div className="relative">
          <div className="flex gap-0 rounded-2xl border border-slate-800 overflow-hidden" style={{ height: 'calc(100vh - 220px)', minHeight: '600px' }}>
            {/* Map area */}
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
                  showRivers={showRivers}
                  showLabels={showLabels}
                  showWarnings={showWarnings}
                  showImpact={showImpact}
                  showRainfall={showRainfall}
                  showFloodExtents={showFloodExtents}
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
                showRivers={showRivers}
                showLabels={showLabels}
                showWarnings={showWarnings}
                showImpact={showImpact}
                showRainfall={showRainfall}
                showFloodExtents={showFloodExtents}
                onToggleLayer={handleToggleLayer}
                totalPopulation={totalPopulation}
                totalBridges={totalBridges}
                totalHospitals={totalHospitals}
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
                  showRivers={showRivers}
                  showLabels={showLabels}
                  showWarnings={showWarnings}
                  showImpact={showImpact}
                  showRainfall={showRainfall}
                  showFloodExtents={showFloodExtents}
                  onToggleLayer={handleToggleLayer}
                  totalPopulation={totalPopulation}
                  totalBridges={totalBridges}
                  totalHospitals={totalHospitals}
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
