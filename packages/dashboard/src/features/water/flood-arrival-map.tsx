'use client'

import { useEffect, useState, useMemo, useCallback } from 'react'
import {
  MapContainer,
  TileLayer,
  Polyline,
  CircleMarker,
  Tooltip,
  useMap,
  Popup,
  Rectangle,
  Marker,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import '@/app/water/flood-map/flood-map.css'

import { RIVER_GEOMETRY, SEGMENT_RIVER } from './rivers'

const ASSET_COORDS: Record<number, [number, number]> = {
  1: [34.086, 72.716], 2: [33.215, 73.640], 3: [32.485, 71.480],
  4: [32.960, 71.490], 5: [30.805, 70.880], 6: [28.430, 68.940],
  7: [27.690, 68.410], 8: [25.370, 68.350], 9: [34.010, 71.580],
  10: [32.480, 74.560], 11: [28.400, 69.700],
}

const ASSET_NAMES: Record<number, string> = {
  1: 'Tarbela', 2: 'Mangla', 3: 'Chashma', 4: 'Kalabagh',
  5: 'Taunsa', 6: 'Guddu', 7: 'Sukkur', 8: 'Kotri',
  9: 'Nowshera', 10: 'Marala', 11: 'Panjnad',
}

const ASSET_TYPES: Record<number, string> = {
  1: 'Dam', 2: 'Dam', 3: 'Barrage', 4: 'Barrage',
  5: 'Barrage', 6: 'Barrage', 7: 'Barrage', 8: 'Barrage',
  9: 'Headworks', 10: 'Headworks', 11: 'Headworks',
}

const TRAVEL_TIMES = [
  { min: 0, max: 6, color: '#ef4444', label: '0-6h (Critical)' },
  { min: 6, max: 12, color: '#f97316', label: '6-12h (Urgent)' },
  { min: 12, max: 24, color: '#eab308', label: '12-24h (Warning)' },
  { min: 24, max: 48, color: '#22c55e', label: '24-48h (Watch)' },
  { min: 48, max: Infinity, color: '#3b82f6', label: '48h+ (Advisory)' },
]

const RIVER_COLORS: Record<string, string> = {
  Indus: '#38bdf8', Jhelum: '#34d399', Kabul: '#f59e0b', Chenab: '#a78bfa', Panjnad: '#f472b6',
}

const HISTORICAL_FLOOD_EXTENTS: { bounds: [[number, number], [number, number]]; label: string }[] = [
  { bounds: [[30.5, 69.5], [31.5, 71.5]], label: '2010 Sindh Flood' },
  { bounds: [[27.0, 67.5], [28.5, 70.0]], label: '2022 Sindh Flood' },
  { bounds: [[32.0, 70.5], [33.5, 72.0]], label: '2014 Punjab Flood' },
  { bounds: [[33.5, 72.5], [34.5, 74.0]], label: '2015 AJK Flood' },
  { bounds: [[25.0, 67.5], [26.5, 69.5]], label: '2022 Karachi Flood' },
]

const IMPACT_ICONS: Record<string, string> = {
  population: '\u{1F468}\u200D\u{1F469}\u200D\u{1F467}',
  bridge: '\u{1F309}',
  hospital: '\u2695\uFE0F',
}

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

interface ImpactAsset {
  id: number
  name: string
  lat: number
  lng: number
  type: 'population' | 'bridge' | 'hospital'
  population?: number
}

interface FfdWarning {
  id: number
  station: string
  river: string
  lat: number
  lng: number
  level_ft: number
  discharge_cusecs: number
  status: string
  severity: string
  issued_at: string
}

interface FfdMarker {
  id: number
  station_name: string
  river_name: string | null
  flood_status: string
  discharge_cusecs: number | null
  gauge_level_ft: number | null
  observed_at: string
  latitude: number | null
  longitude: number | null
  asset_id: number | null
}

interface FloodArrivalMapProps {
  segments?: SegmentData[]
  selectedAssetId?: number | null
  onAssetClick?: (assetId: number | null) => void
  height?: number
  assetThresholds?: Record<number, { warning?: number; danger?: number; critical?: number }>
  currentLevels?: Record<number, number>
  impactAssets?: ImpactAsset[]
  ffdWarnings?: FfdWarning[]
  simulationFlow?: { assetId: number; flow: number } | null
  floodClassifications?: Record<number, { probability: number; severity: string; recommendation: string }>
  ffdMarkers?: FfdMarker[]
  impactMarkers?: ImpactMarker[]
  showRivers?: boolean
  showLabels?: boolean
  showWarnings?: boolean
  showImpact?: boolean
  showRainfall?: boolean
  showFloodExtents?: boolean
  timeSlider?: number
}

interface ImpactMarker {
  id: string
  type: string
  name: string
  lat: number
  lng: number
  population?: number
  segment: string
  river?: string
}

function getTravelTimeColor(hours: number): string {
  for (const t of TRAVEL_TIMES) {
    if (hours >= t.min && hours < t.max) return t.color
  }
  return '#6b7280'
}

function getAssetStatusColor(
  assetId: number,
  thresholds?: Record<number, { warning?: number; danger?: number; critical?: number }>,
  levels?: Record<number, number>
): string {
  if (!thresholds || !levels) return '#6b7280'
  const level = levels[assetId]
  const t = thresholds[assetId]
  if (level == null || !t) return '#6b7280'
  if (t.critical != null && level >= t.critical) return '#ef4444'
  if (t.danger != null && level >= t.danger) return '#f97316'
  if (t.warning != null && level >= t.warning) return '#eab308'
  return '#22c55e'
}

function getPulseClass(hours: number): string {
  if (hours <= 6) return 'flood-pulse-critical'
  if (hours > 24) return 'flood-pulse-slow'
  return 'flood-pulse'
}

function midPt(a: [number, number], b: [number, number]): [number, number] {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
}

function makeArrowIcon(from: [number, number], to: [number, number]): L.DivIcon {
  const dx = to[1] - from[1]
  const dy = to[0] - from[0]
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI
  const svg = `<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg"><path d="M3 10 L15 10 M11 6 L15 10 L11 14" stroke="#94a3b8" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" transform="rotate(${angle} 10 10)"/></svg>`
  return L.divIcon({
    html: svg,
    className: 'river-arrow',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  })
}

function FitBounds({ segments }: { segments: SegmentData[] }) {
  const map = useMap()
  useEffect(() => {
    const allCoords = segments.flatMap((s) => {
      const from = ASSET_COORDS[s.from_id]
      const to = ASSET_COORDS[s.to_id]
      return [from, to].filter(Boolean) as [number, number][]
    })
    if (!allCoords.length) {
      map.fitBounds([[24, 63], [37, 78]])
      return
    }
    const lats = allCoords.map((c) => c[0])
    const lngs = allCoords.map((c) => c[1])
    map.fitBounds(
      [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]],
      { padding: [40, 40] }
    )
  }, [segments, map])
  return null
}

function FloodPulsePolyline({
  positions,
  travelTime,
  tooltipContent,
}: {
  positions: [number, number][]
  travelTime: number
  tooltipContent?: React.ReactNode
}) {
  const color = getTravelTimeColor(travelTime)
  const pulseClass = getPulseClass(travelTime)
  const polylineRef = useCallback(
    (el: L.Polyline | null) => {
      if (el) {
        const pathEl = el.getElement?.()
        if (pathEl) {
          pathEl.classList.remove('flood-pulse', 'flood-pulse-critical', 'flood-pulse-slow')
          pathEl.classList.add(pulseClass)
        }
      }
    },
    [pulseClass]
  )

  return (
    <Polyline
      ref={polylineRef}
      positions={positions}
      pathOptions={{
        color,
        weight: 5,
        opacity: 0.9,
        dashArray: travelTime > 24 ? '10, 8' : undefined,
        className: pulseClass,
      }}
    >
      {tooltipContent}
    </Polyline>
  )
}

function AlertPulseRing({ center, color }: { center: [number, number]; color: string }) {
  return (
    <>
      <CircleMarker
        center={center}
        radius={18}
        pathOptions={{ color, weight: 1, fillColor: color, fillOpacity: 0.15, className: 'alert-pulse-ring' }}
      />
      <CircleMarker
        center={center}
        radius={12}
        pathOptions={{ color, weight: 1.5, fillColor: color, fillOpacity: 0.25, className: 'alert-pulse-ring' }}
      />
    </>
  )
}

export function FloodArrivalMap({
  segments = [],
  selectedAssetId,
  onAssetClick,
  height = 600,
  assetThresholds,
  currentLevels,
  impactAssets,
  ffdWarnings,
  simulationFlow,
  floodClassifications,
  ffdMarkers,
  impactMarkers,
  showRivers = true,
  showLabels = true,
  showWarnings = true,
  showImpact = true,
  showRainfall = false,
  showFloodExtents = false,
  timeSlider = 48,
}: FloodArrivalMapProps) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const visibleSegments = useMemo(
    () => segments.filter((s) => s.travel_time_hours <= timeSlider),
    [segments, timeSlider]
  )

  const totalPopulation = useMemo(
    () => visibleSegments.reduce((sum, s) => sum + s.population_exposed, 0),
    [visibleSegments]
  )

  const totalBridges = useMemo(
    () => visibleSegments.reduce((sum, s) => sum + s.bridges, 0),
    [visibleSegments]
  )

  const totalHospitals = useMemo(
    () => visibleSegments.reduce((sum, s) => sum + s.hospitals, 0),
    [visibleSegments]
  )

  const alertAssetIds = useMemo(() => {
    if (!currentLevels || !assetThresholds) return new Set<number>()
    const ids = new Set<number>()
    for (const [idStr, level] of Object.entries(currentLevels)) {
      const id = Number(idStr)
      const t = assetThresholds[id]
      if (!t || level == null) continue
      if ((t.critical != null && level >= t.critical) || (t.danger != null && level >= t.danger) || (t.warning != null && level >= t.warning)) {
        ids.add(id)
      }
    }
    return ids
  }, [currentLevels, assetThresholds])

  if (!mounted) return <div style={{ height }} className="rounded-2xl bg-slate-900" />

  return (
    <div className="relative overflow-hidden rounded-2xl" style={{ height }}>
      {/* Clear selection button inside map - top left */}
      {selectedAssetId && onAssetClick && (
        <div className="absolute top-4 left-4 z-[1000]">
          <button
            onClick={() => onAssetClick(null)}
            className="flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-slate-900/95 px-3 py-2 text-[11px] font-medium text-sky-400 backdrop-blur hover:bg-slate-800 hover:text-sky-300 transition-colors shadow-lg"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            Back to Overview
          </button>
        </div>
      )}

      <MapContainer
        center={[30.5, 70.5]}
        zoom={6}
        scrollWheelZoom={true}
        style={{ height: '100%', width: '100%', background: '#0b1220' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        {showRivers && RIVER_GEOMETRY.map((river) => (
          <Polyline
            key={`river-${river.name}`}
            positions={river.paths}
            pathOptions={{
              color: river.color,
              weight: river.weight,
              opacity: 0.7,
            }}
          >
            <Tooltip>
              <span className="text-xs font-medium">{river.name} River</span>
            </Tooltip>
          </Polyline>
        ))}

        {/* Confluence connectors */}
        {showRivers && (
          <>
            {/* Jhelum → Trimmu (confluence with Chenab) */}
            <Polyline
              positions={[[32.00, 71.55], [31.80, 71.40], [31.60, 71.30], [31.40, 71.20], [31.30, 72.10]]}
              pathOptions={{ color: '#34d399', weight: 2, opacity: 0.4, dashArray: '4, 6' }}
            >
              <Tooltip><span className="text-[10px]">Jhelum → Trimmu Confluence</span></Tooltip>
            </Polyline>
            {/* Chenab → Trimmu */}
            <Polyline
              positions={[[31.50, 72.15], [31.45, 72.12], [31.40, 72.10], [31.30, 72.10]]}
              pathOptions={{ color: '#a78bfa', weight: 2, opacity: 0.4, dashArray: '4, 6' }}
            >
              <Tooltip><span className="text-[10px]">Chenab → Trimmu Confluence</span></Tooltip>
            </Polyline>
            {/* Panjnad → Indus (near Panjnad Headworks) */}
            <Polyline
              positions={[[28.400, 69.700], [28.35, 69.60], [28.30, 69.50], [28.430, 68.940]]}
              pathOptions={{ color: '#f472b6', weight: 2, opacity: 0.4, dashArray: '4, 6' }}
            >
              <Tooltip><span className="text-[10px]">Panjnad → Indus Confluence</span></Tooltip>
            </Polyline>
            {/* Kabul → Indus (near Attock) */}
            <Polyline
              positions={[[33.55, 72.55], [33.50, 72.60], [33.45, 72.65], [33.40, 72.25]]}
              pathOptions={{ color: '#f59e0b', weight: 2, opacity: 0.4, dashArray: '4, 6' }}
            >
              <Tooltip><span className="text-[10px]">Kabul → Indus Confluence</span></Tooltip>
            </Polyline>
          </>
        )}

        {visibleSegments.map((seg, i) => {
          const from = ASSET_COORDS[seg.from_id]
          const to = ASSET_COORDS[seg.to_id]
          if (!from || !to) return null
          const riverName = SEGMENT_RIVER[`${seg.from_id}-${seg.to_id}`] || seg.river
          return (
            <FloodPulsePolyline
              key={`segment-${seg.from_id}-${seg.to_id}-${i}`}
              positions={[from, to]}
              travelTime={seg.travel_time_hours}
              tooltipContent={
                <Tooltip>
                  <div className="space-y-0.5">
                    <p className="text-[11px] font-semibold">{ASSET_NAMES[seg.from_id]} → {ASSET_NAMES[seg.to_id]}</p>
                    <p className="text-[10px] text-slate-500">{riverName} River</p>
                    <p className="text-[10px]">Travel: <span className="font-semibold">{seg.travel_time_hours}h</span></p>
                    <p className="text-[10px]">Distance: <span className="font-semibold">{seg.distance_km} km</span></p>
                    <p className="text-[10px]">Pop: <span className="font-semibold text-amber-500">{(seg.population_exposed / 1000000).toFixed(1)}M</span></p>
                  </div>
                </Tooltip>
              }
            />
          )
        })}

        {visibleSegments.map((seg, i) => {
          const from = ASSET_COORDS[seg.from_id]
          const to = ASSET_COORDS[seg.to_id]
          if (!from || !to) return null
          return (
            <Marker
              key={`arrow-${seg.from_id}-${seg.to_id}-${i}`}
              position={midPt(from, to)}
              icon={makeArrowIcon(from, to)}
            />
          )
        })}

        {Object.entries(ASSET_COORDS).map(([idStr, coords]) => {
          const id = Number(idStr)
          const name = ASSET_NAMES[id]
          const type = ASSET_TYPES[id]
          const isSelected = id === selectedAssetId
          const hasAlert = alertAssetIds.has(id)
          const statusColor = getAssetStatusColor(id, assetThresholds, currentLevels)
          const classification = floodClassifications?.[id]
          const assetFfdMarkers = ffdMarkers?.filter(m => m.asset_id === id) || []
          const ffdMarker = assetFfdMarkers[0]

          let radius = 7
          if (type === 'Dam') radius = 9
          else if (type === 'Barrage') radius = 8

          if (isSelected) radius += 3

          return (
            <CircleMarker
              key={`asset-${id}`}
              center={coords}
              radius={radius}
              pathOptions={{
                color: isSelected ? '#38bdf8' : statusColor,
                weight: isSelected ? 3 : 2,
                fillColor: isSelected ? '#38bdf8' : statusColor,
                fillOpacity: isSelected ? 0.9 : 0.7,
              }}
              eventHandlers={{
                click: () => {
                  if (onAssetClick) onAssetClick(id)
                },
              }}
            >
              {hasAlert && !isSelected && <AlertPulseRing center={coords} color={statusColor} />}

              {showLabels && (
                <Tooltip permanent direction="right" offset={[12, 0]} className="asset-label-tooltip">
                  <div>
                    <p className="text-[11px] font-bold m-0">{name}</p>
                    <p className="text-[9px] text-slate-400 m-0">{type}</p>
                    {currentLevels?.[id] != null && (
                      <p className="text-[10px] m-0">{currentLevels[id].toLocaleString()} {id <= 2 ? 'ft' : 'cusecs'}</p>
                    )}
                    {classification && (
                      <p className="text-[10px] m-0 font-semibold" style={{ color: classification.severity === 'HIGH' ? '#ef4444' : classification.severity === 'MEDIUM' ? '#f97316' : '#22c55e' }}>
                        Flood: {(classification.probability * 100).toFixed(0)}%
                      </p>
                    )}
                  </div>
                </Tooltip>
              )}

              <Popup>
                <div className="space-y-1.5 min-w-[180px]">
                  <div>
                    <p className="text-sm font-bold m-0">{name}</p>
                    <p className="text-[10px] text-slate-400 m-0">{type}</p>
                  </div>
                  {currentLevels?.[id] != null && (
                    <p className="text-[11px] m-0">Level: <span className="font-semibold">{currentLevels[id].toLocaleString()} {id <= 2 ? 'ft' : 'cusecs'}</span></p>
                  )}
                  {ffdMarker && (
                    <div className="text-[10px] space-y-0.5">
                      <p className="m-0">FFD: <span className="font-semibold">{ffdMarker.flood_status}</span></p>
                      {ffdMarker.discharge_cusecs != null && <p className="m-0">Discharge: {ffdMarker.discharge_cusecs.toLocaleString()} cusecs</p>}
                      {ffdMarker.gauge_level_ft != null && <p className="m-0">Level: {ffdMarker.gauge_level_ft} ft</p>}
                    </div>
                  )}
                  {classification && (
                    <p className="text-[11px] m-0 font-semibold" style={{ color: classification.severity === 'HIGH' ? '#ef4444' : classification.severity === 'MEDIUM' ? '#f97316' : '#22c55e' }}>
                      Flood Probability: {(classification.probability * 100).toFixed(0)}% ({classification.severity})
                    </p>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); if (onAssetClick) onAssetClick(id) }}
                    className="w-full mt-1 rounded bg-sky-500 px-2 py-1 text-[10px] font-medium text-white hover:bg-sky-600 cursor-pointer"
                  >
                    Calculate Impact
                  </button>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {showImpact && impactMarkers?.map((marker) => {
          const isPop = marker.type === 'population'
          const isBridge = marker.type === 'bridge'
          const isHosp = marker.type === 'hospital'
          const color = isPop ? '#22c55e' : isBridge ? '#f59e0b' : '#ef4444'
          const radius = isPop ? 6 : isBridge ? 4 : 4
          return (
            <CircleMarker
              key={marker.id}
              center={[marker.lat, marker.lng]}
              radius={radius}
              pathOptions={{ color, fillColor: color, fillOpacity: 0.7, weight: 1 }}
            >
              <Tooltip>
                <span className="text-xs">
                  {isPop && `${(marker.population / 1000000).toFixed(1)}M people`}
                  {isBridge && 'Bridge'}
                  {isHosp && 'Hospital'}
                  <br />
                  <span className="text-[10px] text-slate-400">{marker.segment}</span>
                </span>
              </Tooltip>
            </CircleMarker>
          )
        })}

        {showWarnings && ffdWarnings?.map((w) => {
          const severityColor = w.severity === 'Critical' ? '#ef4444' : w.severity === 'Danger' ? '#f97316' : '#eab308'
          return (
            <CircleMarker
              key={`warn-${w.id}`}
              center={[w.lat, w.lng]}
              radius={10}
              pathOptions={{
                color: severityColor,
                weight: 2,
                fillColor: severityColor,
                fillOpacity: 0.2,
              }}
            >
              <Popup>
                <div className="space-y-1 min-w-[160px]">
                  <p className="text-xs font-bold m-0">{w.station}</p>
                  <p className="text-[10px] text-slate-400 m-0">{w.river}</p>
                  <p className="text-[10px] m-0">Discharge: <span className="font-semibold">{w.discharge_cusecs?.toLocaleString()} cusecs</span></p>
                  <p className="text-[10px] m-0">Level: <span className="font-semibold">{w.level_ft} ft</span></p>
                  <p className="text-[10px] m-0">Status: <span className="font-semibold" style={{ color: severityColor }}>{w.severity}</span></p>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {showFloodExtents && HISTORICAL_FLOOD_EXTENTS.map((extent, i) => (
          <Rectangle
            key={`extent-${i}`}
            bounds={extent.bounds}
            pathOptions={{
              color: '#3b82f6',
              weight: 1,
              fillColor: '#3b82f6',
              fillOpacity: 0.08,
              dashArray: '4, 6',
            }}
          >
            <Tooltip>
              <span className="text-xs">{extent.label}</span>
            </Tooltip>
          </Rectangle>
        ))}

        {showRainfall && ffdMarkers?.map((marker) => {
          if (marker.latitude == null || marker.longitude == null) return null
          const statusColor = marker.flood_status === 'HIGH' ? '#ef4444'
            : marker.flood_status === 'MEDIUM' ? '#f97316'
            : marker.flood_status === 'ABOVE_NORMAL' ? '#eab308'
            : '#22c55e'
          const radius = marker.flood_status === 'HIGH' ? 10
            : marker.flood_status === 'MEDIUM' ? 8
            : 6
          return (
            <CircleMarker
              key={`ffd-station-${marker.id}`}
              center={[marker.latitude, marker.longitude]}
              radius={radius}
              pathOptions={{
                color: statusColor,
                weight: 2,
                fillColor: statusColor,
                fillOpacity: 0.6,
              }}
            >
              <Popup>
                <div className="space-y-1 min-w-[160px]">
                  <p className="text-xs font-bold m-0">{marker.station_name}</p>
                  <p className="text-[10px] text-slate-400 m-0">{marker.river_name}</p>
                  {marker.discharge_cusecs != null && <p className="text-[10px] m-0">Discharge: <span className="font-semibold">{marker.discharge_cusecs.toLocaleString()} cusecs</span></p>}
                  {marker.gauge_level_ft != null && <p className="text-[10px] m-0">Level: <span className="font-semibold">{marker.gauge_level_ft} ft</span></p>}
                  <p className="text-[10px] m-0">Status: <span className="font-semibold" style={{ color: statusColor }}>{marker.flood_status}</span></p>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {simulationFlow && (() => {
          const downstream = segments.filter((s) => s.from_id === simulationFlow.assetId)
          if (!downstream.length) return null
          return downstream.map((seg, i) => {
            const from = ASSET_COORDS[seg.from_id]
            const to = ASSET_COORDS[seg.to_id]
            if (!from || !to) return null
            return (
              <Polyline
                key={`sim-${seg.from_id}-${seg.to_id}-${i}`}
                positions={[from, to]}
                pathOptions={{
                  color: '#f59e0b',
                  weight: 6,
                  opacity: 0.5,
                  dashArray: '4, 8',
                }}
              >
                <Tooltip>
                  <span className="text-xs">Simulation: {simulationFlow.flow.toLocaleString()} cusecs</span>
                </Tooltip>
              </Polyline>
            )
          })
        })()}

        <FitBounds segments={segments} />
      </MapContainer>
    </div>
  )
}
