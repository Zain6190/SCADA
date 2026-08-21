'use client'

// packages/dashboard/src/features/water/flood-arrival-map.tsx
// Leaflet map showing river network, assets, and flood arrival visualization.
import { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip, useMap, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

// Asset coordinates (from downstream_engine.py)
const ASSET_COORDS: Record<number, [number, number]> = {
  1: [34.086, 72.716],   // Tarbela
  2: [33.215, 73.640],   // Mangla
  3: [32.485, 71.480],   // Chashma
  4: [32.960, 71.490],   // Kalabagh
  5: [30.805, 70.880],   // Taunsa
  6: [28.430, 68.940],   // Guddu
  7: [27.690, 68.410],   // Sukkur
  8: [25.370, 68.350],   // Kotri
  9: [34.010, 71.580],   // Kabul @ Nowshera
  10: [32.480, 74.560],  // Chenab @ Marala
  11: [28.400, 69.700],  // Panjnad
}

const ASSET_NAMES: Record<number, string> = {
  1: 'Tarbela', 2: 'Mangla', 3: 'Chashma', 4: 'Kalabagh',
  5: 'Taunsa', 6: 'Guddu', 7: 'Sukkur', 8: 'Kotri',
  9: 'Nowshera', 10: 'Marala', 11: 'Panjnad',
}

// River network segments (from downstream_engine.py)
const RIVER_SEGMENTS = [
  { from: 1, to: 4, river: 'Indus', order: 0 },
  { from: 4, to: 3, river: 'Indus', order: 1 },
  { from: 3, to: 5, river: 'Indus', order: 2 },
  { from: 5, to: 6, river: 'Indus', order: 3 },
  { from: 6, to: 7, river: 'Indus', order: 4 },
  { from: 7, to: 8, river: 'Indus', order: 5 },
  { from: 2, to: 3, river: 'Jhelum', order: 0 },
  { from: 9, to: 4, river: 'Kabul', order: 0 },
  { from: 10, to: 3, river: 'Chenab', order: 0 },
  { from: 11, to: 6, river: 'Panjnad', order: 0 },
]

// Travel time ranges (hours) for flood arrival color coding
const TRAVEL_TIMES = [
  { min: 0, max: 6, color: '#ef4444', label: '0-6h (Critical)' },
  { min: 6, max: 12, color: '#f97316', label: '6-12h (Urgent)' },
  { min: 12, max: 24, color: '#eab308', label: '12-24h (Warning)' },
  { min: 24, max: 48, color: '#22c55e', label: '24-48h (Watch)' },
  { min: 48, max: Infinity, color: '#3b82f6', label: '48h+ (Advisory)' },
]

function getTravelTimeColor(hours: number): string {
  for (const t of TRAVEL_TIMES) {
    if (hours >= t.min && hours < t.max) return t.color
  }
  return '#6b7280'
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

interface FloodArrivalMapProps {
  segments?: SegmentData[]
  selectedAssetId?: number | null
  onAssetClick?: (assetId: number) => void
  height?: number
}

function FitBounds({ segments }: { segments: SegmentData[] }) {
  const map = useMap()
  useEffect(() => {
    const allCoords = segments.flatMap(s => {
      const from = ASSET_COORDS[s.from_id]
      const to = ASSET_COORDS[s.to_id]
      return [from, to].filter(Boolean)
    })
    if (!allCoords.length) {
      map.fitBounds([[24, 63], [37, 78]])
      return
    }
    const lats = allCoords.map(c => c[0])
    const lngs = allCoords.map(c => c[1])
    map.fitBounds([
      [Math.min(...lats), Math.min(...lngs)],
      [Math.max(...lats), Math.max(...lngs)],
    ], { padding: [40, 40] })
  }, [segments, map])
  return null
}

export function FloodArrivalMap({
  segments = [],
  selectedAssetId,
  onAssetClick,
  height = 600,
}: FloodArrivalMapProps) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const activeAssets = useMemo(() => {
    const ids = new Set<number>()
    segments.forEach(s => { ids.add(s.from_id); ids.add(s.to_id) })
    return Array.from(ids)
  }, [segments])

  if (!mounted) return <div style={{ height }} className="rounded-xl bg-slate-900" />

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-800" style={{ height }}>
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

        {/* River network segments */}
        {segments.map((seg, i) => {
          const from = ASSET_COORDS[seg.from_id]
          const to = ASSET_COORDS[seg.to_id]
          if (!from || !to) return null
          const color = getTravelTimeColor(seg.travel_time_hours)
          return (
            <Polyline
              key={`seg-${i}`}
              positions={[from, to]}
              pathOptions={{
                color,
                weight: 4,
                opacity: 0.8,
                dashArray: seg.travel_time_hours > 24 ? '8, 8' : undefined,
              }}
            >
              <Tooltip>
                <div className="p-1 min-w-[180px]">
                  <p className="font-semibold text-sm">{seg.river}</p>
                  <p className="text-xs">{ASSET_NAMES[seg.from_id]} → {ASSET_NAMES[seg.to_id]}</p>
                  <p className="text-xs mt-1">
                    <span className="font-medium">Travel:</span> {seg.travel_time_hours.toFixed(1)}h
                  </p>
                  <p className="text-xs">
                    <span className="font-medium">Distance:</span> {seg.distance_km.toFixed(0)} km
                  </p>
                  <p className="text-xs">
                    <span className="font-medium">Population:</span> {(seg.population_exposed / 1000000).toFixed(1)}M
                  </p>
                  <p className="text-xs">
                    <span className="font-medium">Bridges:</span> {seg.bridges} · <span className="font-medium">Hospitals:</span> {seg.hospitals}
                  </p>
                </div>
              </Tooltip>
            </Polyline>
          )
        })}

        {/* Asset markers */}
        {activeAssets.map(id => {
          const coords = ASSET_COORDS[id]
          if (!coords) return null
          const isSelected = selectedAssetId === id
          const name = ASSET_NAMES[id]
          const segs = segments.filter(s => s.from_id === id || s.to_id === id)
          const totalPop = segs.reduce((sum, s) => sum + s.population_exposed, 0)
          const maxTravel = Math.max(...segs.map(s => s.travel_time_hours), 0)
          const color = maxTravel > 0 ? getTravelTimeColor(maxTravel) : '#6b7280'

          return (
            <CircleMarker
              key={`asset-${id}`}
              center={coords}
              radius={isSelected ? 12 : 8}
              pathOptions={{
                color: isSelected ? '#ffffff' : color,
                weight: isSelected ? 3 : 2,
                fillColor: color,
                fillOpacity: 0.9,
              }}
              eventHandlers={{ click: () => onAssetClick?.(id) }}
            >
              <Popup>
                <div className="p-2 min-w-[200px]">
                  <p className="font-bold text-base">{name}</p>
                  <p className="text-xs text-slate-600 mt-1">Asset ID: {id}</p>
                  <div className="mt-2 space-y-1 text-xs">
                    <p><span className="font-medium">Population at risk:</span> {(totalPop / 1000000).toFixed(1)}M</p>
                    <p><span className="font-medium">Furthest arrival:</span> {maxTravel.toFixed(1)}h</p>
                    <p><span className="font-medium">Segments:</span> {segs.length}</p>
                  </div>
                </div>
              </Popup>
              <Tooltip direction="top" offset={[0, -10]}>
                <span className="font-semibold">{name}</span>
              </Tooltip>
            </CircleMarker>
          )
        })}

        <FitBounds segments={segments} />
      </MapContainer>

      {/* Legend */}
      <div className="absolute bottom-4 right-4 z-[1000] rounded-xl border border-slate-700 bg-slate-900/95 px-4 py-3 backdrop-blur">
        <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-2 font-medium">Travel Time</p>
        <div className="space-y-1.5">
          {TRAVEL_TIMES.map(t => (
            <div key={t.label} className="flex items-center gap-2">
              <div className="w-3 h-1 rounded-full" style={{ backgroundColor: t.color }} />
              <span className="text-[11px] text-slate-300">{t.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
