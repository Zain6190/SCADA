// packages/dashboard/src/features/water/use-flood-map-state.ts
'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8100'

export interface SegmentData {
  from_id: number
  to_id: number
  river: string | null
  travel_time_hours: number | null
  arrival_time?: string | null
  distance_km: number | null
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
  total_travel_hours: number | null
  furthest_asset: string
  furthest_arrival: string | null
  segments: Array<{
    segment_order: number
    river_name: string
    upstream_asset: string
    downstream_asset: string
    distance_km: number
    travel_time_hours: number | null
    arrival_time: string | null
    population_exposed: number
    bridges_count: number
    hospitals_count: number
  }>
}

export interface AlertMarker {
  id: number
  station: string
  river: string | null
  lat: number
  lng: number
  level_ft: number | null
  discharge_cusecs: number | null
  status: string
  severity: string
  issued_at: string
}

export interface AssetReading {
  id: number
  name: string
  assetType: string | null
  river: string | null
  lat: number | null
  lng: number | null
  warningFt: number | null
  dangerFt: number | null
  criticalFt: number | null
  levelFt: number | null
  dischargeCusecs: number | null
  value: number | null
  unit: 'ft' | 'cusecs' | null
  observedAt: string | null
  ageHours: number | null
  source: string | null
}

export interface ThreatenedPlace {
  kind: 'town' | 'bridge' | 'hospital' | 'asset' | string
  name: string
  lat: number
  lng: number
  district: string
}

export interface FloodTerritoryProperties {
  district: string
  province: string
  flood_probability: number
  flood_severity: string
  population_exposed: number
  bridges: number
  hospitals: number
  recommendation: string
  source_asset_id: number
  source_asset_name: string
  alert: boolean
  ot_source?: string
  ot_mode?: string
  ot_device_code?: string
  inside?: ThreatenedPlace[]
}

export interface FloodTerritoryFeature {
  type: string
  geometry: { type?: string; coordinates?: unknown }
  properties: FloodTerritoryProperties
}

export interface RegionAlert {
  district: string
  province: string
  severity: string
  flood_probability: number
  population_exposed: number
  bridges: number
  hospitals: number
  recommendation: string
  source_asset_id: number
  source_asset_name: string
  inside_count?: number
  inside?: ThreatenedPlace[]
}

export interface LayerState {
  showTerritories: boolean
  showRivers: boolean
  showLabels: boolean
  showWarnings: boolean
  showRainfall: boolean
}

interface FloodMapOverview {
  segments: SegmentData[]
  alertMarkers: AlertMarker[]
  assets: AssetReading[]
  ffdMarkers: any[]
  floodClassifications: Record<number, { probability: number; severity: string; recommendation: string }>
  territories: FloodTerritoryFeature[]
  regionAlerts: RegionAlert[]
  degraded: string[]
}

const RIVER_NAMES = ['Indus', 'Jhelum', 'Kabul', 'Chenab', 'Panjnad']

function riverFromNotes(notes?: string | null): string | null {
  if (!notes) return null
  for (const river of RIVER_NAMES) {
    if (notes.includes(river)) return river
  }
  return null
}

function mapAssetReading(raw: any): AssetReading {
  const levelFt = raw.current_level_ft ?? null
  const dischargeCusecs = raw.current_discharge ?? null
  const value = levelFt ?? dischargeCusecs
  const unit: AssetReading['unit'] = levelFt != null ? 'ft' : dischargeCusecs != null ? 'cusecs' : null
  return {
    id: raw.id,
    name: raw.canonical_name,
    assetType: raw.asset_type ?? null,
    river: raw.river ?? null,
    lat: raw.latitude ?? null,
    lng: raw.longitude ?? null,
    warningFt: raw.warning_level_ft ?? null,
    dangerFt: raw.danger_level_ft ?? null,
    criticalFt: raw.critical_level_ft ?? null,
    levelFt,
    dischargeCusecs,
    value,
    unit,
    observedAt: raw.last_observed_at ?? null,
    ageHours: raw.data_age_hours ?? null,
    source: raw.latest_source ?? null,
  }
}

async function fetchOverview(): Promise<FloodMapOverview> {
  const [impRes, alertRes, assetsRes, ffdRes, territoryRes] = await Promise.all([
    fetch(`${API_BASE}/water/impact/precalculated`),
    fetch(`${API_BASE}/water/operational/alerts?status=NEW`),
    fetch(`${API_BASE}/water/operational/assets`),
    fetch(`${API_BASE}/water/operational/ffd/markers`),
    fetch(`${API_BASE}/water/flood-map/territory`),
  ])

  const degraded: string[] = []
  if (!impRes.ok) degraded.push('impact')
  if (!alertRes.ok) degraded.push('alerts')
  if (!assetsRes.ok) degraded.push('assets')
  if (!ffdRes.ok) degraded.push('ffd')
  if (!territoryRes.ok) degraded.push('territory')

  const rawAssets = assetsRes.ok ? await assetsRes.json() : []
  const assets: AssetReading[] = (Array.isArray(rawAssets) ? rawAssets : []).map(mapAssetReading)
  const assetsById: Record<number, AssetReading> = {}
  const assetsByName: Record<string, AssetReading> = {}
  for (const asset of assets) {
    assetsById[asset.id] = asset
    assetsByName[asset.name] = asset
  }

  let segments: SegmentData[] = []
  if (impRes.ok) {
    const impacts = await impRes.json()
    segments = (Array.isArray(impacts) ? impacts : [])
      .filter((imp: any) => imp.downstream_asset_id != null)
      .map((imp: any) => ({
        from_id: imp.source_asset_id,
        to_id: imp.downstream_asset_id,
        river: riverFromNotes(imp.notes),
        travel_time_hours: imp.travel_time_hours_expected ?? imp.travel_time_hours_min ?? null,
        distance_km: imp.distance_km ?? null,
        population_exposed: imp.affected_population_est ?? 0,
        bridges: imp.bridges_count ?? 0,
        hospitals: imp.hospitals_count ?? 0,
      }))
      .filter((seg: SegmentData) => assetsById[seg.from_id] && assetsById[seg.to_id])
  }

  let alertMarkers: AlertMarker[] = []
  if (alertRes.ok) {
    const alertList = await alertRes.json()
    alertMarkers = (Array.isArray(alertList) ? alertList : [])
      .map((a: any): AlertMarker | null => {
        const asset: AssetReading | undefined = assetsById[a.asset_id] ?? assetsByName[a.asset_name]
        if (!asset || asset.lat == null || asset.lng == null) return null
        return {
          id: a.id,
          station: asset.name,
          river: asset.river,
          lat: asset.lat,
          lng: asset.lng,
          level_ft: a.reading_level_ft ?? null,
          discharge_cusecs: a.reading_discharge_cusecs ?? a.triggered_value ?? null,
          status: a.status || 'NEW',
          severity: a.severity || 'WATCH',
          issued_at: a.created_at || new Date().toISOString(),
        }
      })
      .filter((marker: AlertMarker | null): marker is AlertMarker => marker !== null)
  }

  const floodClassifications: FloodMapOverview['floodClassifications'] = {}
  for (const asset of assets) {
    const raw = (Array.isArray(rawAssets) ? rawAssets : []).find((a: any) => a.id === asset.id)
    if (raw?.flood_probability != null) {
      floodClassifications[asset.id] = {
        probability: raw.flood_probability,
        severity: raw.flood_severity || 'NONE',
        recommendation: raw.flood_recommendation || '',
      }
    }
  }

  let territories: FloodTerritoryFeature[] = []
  let regionAlerts: RegionAlert[] = []
  if (territoryRes.ok) {
    const territory = await territoryRes.json()
    territories = Array.isArray(territory.features) ? territory.features : []
    regionAlerts = Array.isArray(territory.alerts) ? territory.alerts : []
  }

  const ffdMarkers = ffdRes.ok ? await ffdRes.json() : []

  return {
    segments,
    alertMarkers,
    assets,
    ffdMarkers: Array.isArray(ffdMarkers) ? ffdMarkers : [],
    floodClassifications,
    territories,
    regionAlerts,
    degraded,
  }
}

export function useFloodMapState() {
  const overview = useQuery({
    queryKey: ['flood-map', 'overview'],
    queryFn: fetchOverview,
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  })

  const [impactSummary, setImpactSummary] = useState<ImpactSummary | null>(null)
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null)

  // UI state
  const [calculating, setCalculating] = useState(false)
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  // Layers
  const [layers, setLayers] = useState<LayerState>({
    showTerritories: true,
    showRivers: true,
    showLabels: true,
    showWarnings: true,
    showRainfall: false,
  })

  // Controls
  const [timeSlider, setTimeSlider] = useState(48)

  const toggleLayer = useCallback((layer: keyof LayerState) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }))
  }, [])

  const segments = overview.data?.segments ?? []
  const alertMarkers = overview.data?.alertMarkers ?? []
  const assets = overview.data?.assets ?? []
  const ffdMarkers = overview.data?.ffdMarkers ?? []
  const floodClassifications = overview.data?.floodClassifications ?? {}
  const territories = overview.data?.territories ?? []
  const regionAlerts = overview.data?.regionAlerts ?? []
  const degraded = overview.data?.degraded ?? []

  const assetsById = useMemo(() => {
    const map: Record<number, AssetReading> = {}
    for (const asset of assets) map[asset.id] = asset
    return map
  }, [assets])

  const assetsByName = useMemo(() => {
    const map: Record<string, AssetReading> = {}
    for (const asset of assets) map[asset.name] = asset
    return map
  }, [assets])

  // Impact calculation when asset selected
  const [impactReason, setImpactReason] = useState<'no-flow' | 'failed' | null>(null)
  useEffect(() => {
    if (!selectedAsset) { setImpactSummary(null); setImpactReason(null); return }
    async function calc() {
      setCalculating(true)
      setImpactReason(null)
      try {
        let flow: number | null = null
        try {
          const flowRes = await fetch(`${API_BASE}/water/impact/latest-flow/${selectedAsset}`)
          if (flowRes.ok) {
            const flowData = await flowRes.json()
            flow = flowData.effective_flow ?? null
          }
        } catch {}

        if (flow == null) {
          setImpactSummary(null)
          setImpactReason('no-flow')
          return
        }

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
        else { setImpactSummary(null); setImpactReason('failed') }
      } catch {
        setImpactSummary(null)
        setImpactReason('failed')
      }
      setCalculating(false)
    }
    calc()
  }, [selectedAsset])

  const displaySegments = useMemo(() => {
    if (selectedAsset && impactSummary) {
      return impactSummary.segments
        .map(s => {
          const from = assetsByName[s.upstream_asset]
          const to = assetsByName[s.downstream_asset]
          if (!from || !to) return null
          return {
            from_id: from.id,
            to_id: to.id,
            river: s.river_name || null,
            travel_time_hours: s.travel_time_hours ?? null,
            arrival_time: s.arrival_time ?? null,
            distance_km: s.distance_km ?? null,
            population_exposed: s.population_exposed,
            bridges: s.bridges_count,
            hospitals: s.hospitals_count,
          } as SegmentData
        })
        .filter((s): s is SegmentData => s !== null)
    }
    return segments
  }, [selectedAsset, impactSummary, segments, assetsByName])

  const totals = useMemo(() => ({
    population: displaySegments.reduce((sum, s) => sum + s.population_exposed, 0),
    bridges: displaySegments.reduce((sum, s) => sum + s.bridges, 0),
    hospitals: displaySegments.reduce((sum, s) => sum + s.hospitals, 0),
  }), [displaySegments])

  const visibleSegments = useMemo(
    () => displaySegments.filter(s => s.travel_time_hours != null && s.travel_time_hours <= timeSlider),
    [displaySegments, timeSlider]
  )

  const alertedPopulation = useMemo(
    () => regionAlerts.reduce((sum, alert) => sum + (alert.population_exposed || 0), 0),
    [regionAlerts],
  )

  const selectedTerritory = useMemo(
    () => territories.find((feature) => feature.properties.district === selectedDistrict) ?? null,
    [territories, selectedDistrict],
  )

  const newestObservedAt = useMemo(() => {
    let newest: string | null = null
    for (const asset of assets) {
      if (asset.observedAt && (!newest || asset.observedAt > newest)) newest = asset.observedAt
    }
    return newest
  }, [assets])

  const loading = overview.isLoading
  const error = overview.error ? (overview.error as Error).message : null

  return {
    // Data
    assets, assetsById, ffdWarnings: alertMarkers, floodClassifications, ffdMarkers,
    territories, regionAlerts, selectedDistrict, selectedTerritory, alertedPopulation,
    // UI
    loading, calculating, error, selectedAsset, mobileSidebarOpen, degraded, impactReason,
    // Layers
    layers, toggleLayer,
    // Controls
    timeSlider, setTimeSlider,
    // Derived
    displaySegments, totals, visibleSegments, newestObservedAt, impactSummary,
    // Actions
    setSelectedAsset, setSelectedDistrict, setMobileSidebarOpen,
  }
}
