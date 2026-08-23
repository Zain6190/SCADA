// packages/dashboard/src/features/water/use-flood-map-state.ts
'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8100'

export interface SegmentData {
  from_id: number
  to_id: number
  river: string
  travel_time_hours: number
  distance_km: number
  population_exposed: number
  bridges: number
  hospitals: number
}

export interface ImpactSummary {
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

export interface Alert {
  id: number
  asset_name: string
  severity: string
  message: string
  downstream_population_exposed?: number
}

export const ASSET_MAP: Record<string, number> = {
  Tarbela: 1, Mangla: 2, Chashma: 3, Kalabagh: 4,
  Taunsa: 5, Guddu: 6, Sukkur: 7, Kotri: 8,
  'Kabul @ Nowshera': 9, Nowshera: 9, 'Chenab @ Marala': 10, Marala: 10,
  Panjnad: 11,
}

export const DEFAULT_THRESHOLDS: Record<number, { warning?: number; danger?: number; critical?: number }> = {
  1: { warning: 1550, danger: 1570, critical: 1600 },
  2: { warning: 1242, danger: 1248, critical: 1255 },
  9: { warning: 100000, danger: 150000, critical: 200000 },
  10: { warning: 80000, danger: 120000, critical: 160000 },
}

export const ASSET_NAMES: Record<number, string> = {
  1: 'Tarbela', 2: 'Mangla', 3: 'Chashma', 4: 'Kalabagh',
  5: 'Taunsa', 6: 'Guddu', 7: 'Sukkur', 8: 'Kotri',
  9: 'Nowshera', 10: 'Marala', 11: 'Panjnad',
}

interface LayerState {
  showRivers: boolean
  showLabels: boolean
  showWarnings: boolean
  showImpact: boolean
  showRainfall: boolean
  showFloodExtents: boolean
}

export function useFloodMapState() {
  // Data
  const [segments, setSegments] = useState<SegmentData[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [impactSummary, setImpactSummary] = useState<ImpactSummary | null>(null)
  const [currentLevels, setCurrentLevels] = useState<Record<number, number>>({})
  const [ffdWarnings, setFfdWarnings] = useState<any[]>([])
  const [floodClassifications, setFloodClassifications] = useState<Record<number, { probability: number; severity: string; recommendation: string }>>({})
  const [ffdMarkers, setFfdMarkers] = useState<any[]>([])
  const [impactMarkers, setImpactMarkers] = useState<any[]>([])

  // UI state
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  // Layers
  const [layers, setLayers] = useState<LayerState>({
    showRivers: true,
    showLabels: true,
    showWarnings: true,
    showImpact: true,
    showRainfall: false,
    showFloodExtents: false,
  })

  // Controls
  const [timeSlider, setTimeSlider] = useState(48)
  const [simAssetId, setSimAssetId] = useState<number>(1)
  const [simFlow, setSimFlow] = useState<number>(100000)

  const toggleLayer = useCallback((layer: keyof LayerState) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }))
  }, [])

  // Fetch all data
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
          setSegments(impacts.map((imp: any) => ({
            from_id: imp.source_asset_id,
            to_id: imp.downstream_asset_id || imp.source_asset_id + 1,
            river: imp.notes?.includes('Indus') ? 'Indus' : imp.notes?.includes('Jhelum') ? 'Jhelum' : imp.notes?.includes('Kabul') ? 'Kabul' : imp.notes?.includes('Chenab') ? 'Chenab' : 'Indus',
            travel_time_hours: imp.travel_time_hours_expected || imp.travel_time_hours_min || 24,
            distance_km: imp.distance_km || 100,
            population_exposed: imp.affected_population_est || 0,
            bridges: imp.bridges_count || 0,
            hospitals: imp.hospitals_count || 0,
          })))
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

        if (ffdRes.ok) setFfdMarkers(await ffdRes.json())
        if (markersRes.ok) setImpactMarkers(await markersRes.json())
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

  // Impact calculation when asset selected
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

  const displaySegments = useMemo(() => {
    if (selectedAsset && impactSummary) {
      return impactSummary.segments.map(s => ({
        from_id: ASSET_MAP[s.upstream_asset] || 1,
        to_id: ASSET_MAP[s.downstream_asset] || 1,
        river: s.river_name,
        travel_time_hours: s.travel_time_hours,
        distance_km: s.distance_km,
        population_exposed: s.population_exposed,
        bridges: s.bridges_count,
        hospitals: s.hospitals_count,
      }))
    }
    return segments
  }, [selectedAsset, impactSummary, segments])

  const totals = useMemo(() => ({
    population: displaySegments.reduce((sum, s) => sum + s.population_exposed, 0),
    bridges: displaySegments.reduce((sum, s) => sum + s.bridges, 0),
    hospitals: displaySegments.reduce((sum, s) => sum + s.hospitals, 0),
    maxTravel: Math.max(...displaySegments.map(s => s.travel_time_hours), 0),
  }), [displaySegments])

  const visibleSegments = useMemo(
    () => displaySegments.filter(s => s.travel_time_hours <= timeSlider),
    [displaySegments, timeSlider]
  )

  const simImpact = useMemo(() => {
    const downstream = segments.filter(s => s.from_id === simAssetId)
    if (!downstream.length) return null
    const scaleFactor = simFlow / 100000
    return {
      segments: downstream.length,
      population: Math.round(totals.population * scaleFactor),
      bridges: Math.round(totals.bridges * scaleFactor),
      hospitals: Math.round(totals.hospitals * scaleFactor),
      maxTravel: Math.max(...downstream.map(s => s.travel_time_hours)),
    }
  }, [segments, simAssetId, simFlow, totals])

  return {
    // Data
    segments, alerts, impactSummary, currentLevels, ffdWarnings,
    floodClassifications, ffdMarkers, impactMarkers,
    // UI
    loading, calculating, error, selectedAsset, mobileSidebarOpen,
    // Layers
    layers, toggleLayer,
    // Controls
    timeSlider, setTimeSlider, simAssetId, setSimAssetId, simFlow, setSimFlow,
    // Derived
    displaySegments, totals, visibleSegments, simImpact,
    // Actions
    setSelectedAsset, setMobileSidebarOpen,
  }
}
