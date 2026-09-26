'use client'

import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import {
  MapContainer,
  TileLayer,
  Polyline,
  Polygon,
  CircleMarker,
  Tooltip,
  useMap,
  Popup,
  Marker,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import '@/app/water/flood-map/flood-map.css'

import { RIVER_GEOMETRY, SEGMENT_RIVER } from './rivers'
import type { AssetReading, FloodTerritoryFeature, SegmentData, AlertMarker } from './use-flood-map-state'

const TERRITORY_STYLE: Record<string, { fill: string; opacity: number }> = {
  NONE: { fill: '#64748b', opacity: 0.12 },
  LOW: { fill: '#3b82f6', opacity: 0.28 },
  MODERATE: { fill: '#f59e0b', opacity: 0.42 },
  HIGH: { fill: '#f97316', opacity: 0.52 },
  EXTREME: { fill: '#ef4444', opacity: 0.58 },
  CRITICAL: { fill: '#ef4444', opacity: 0.58 },
}

function ringsForGeometry(geometry: { type?: string; coordinates?: any } | undefined): [number, number][][] {
  if (!geometry?.coordinates) return []
  const coords = geometry.coordinates
  if (geometry.type === 'Polygon') {
    const rings = coords as any[]
    const normalized = Array.isArray(rings[0]?.[0]) ? rings : [rings]
    return normalized.map((ring: any) =>
      ring.map((pt: any) => [pt[1], pt[0]] as [number, number])
    )
  }
  if (geometry.type === 'MultiPolygon') {
    return (coords as any[]).flatMap((poly: any) =>
      poly.map((ring: any) => ring.map((pt: any) => [pt[1], pt[0]] as [number, number]))
    )
  }
  return []
}

const INSIDE_STYLE: Record<string, { color: string; label: string }> = {
  town: { color: '#fbbf24', label: 'Town' },
  bridge: { color: '#fb923c', label: 'Bridge' },
  hospital: { color: '#f87171', label: 'Hospital' },
  asset: { color: '#38bdf8', label: 'Asset' },
}

function isThreatened(severity: string | undefined, alert: boolean | undefined): boolean {
  const level = (severity || 'NONE').toUpperCase()
  return Boolean(alert) || ['MODERATE', 'HIGH', 'EXTREME', 'CRITICAL'].includes(level)
}

function formatPeople(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1_000) return `${Math.round(count / 1_000)}k`
  return count.toLocaleString()
}

const TRAVEL_TIMES = [
  { min: 0, max: 6, color: '#ef4444', label: '0-6h (Critical)' },
  { min: 6, max: 12, color: '#f97316', label: '6-12h (Urgent)' },
  { min: 12, max: 24, color: '#eab308', label: '12-24h (Warning)' },
  { min: 24, max: 48, color: '#22c55e', label: '24-48h (Watch)' },
  { min: 48, max: Infinity, color: '#3b82f6', label: '48h+ (Advisory)' },
]

function formatAge(hours: number): string {
  return hours < 48 ? `${Math.round(hours)}h` : `${(hours / 24).toFixed(1)}d`
}

function freshness(ageHours: number | null): { color: string; label: string } {
  if (ageHours == null) return { color: '#94a3b8', label: 'No official reading' }
  if (ageHours <= 24) return { color: '#22c55e', label: `observed ${formatAge(ageHours)} ago` }
  if (ageHours <= 48) return { color: '#eab308', label: `aging · observed ${formatAge(ageHours)} ago` }
  return { color: '#ef4444', label: `STALE · observed ${formatAge(ageHours)} ago` }
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
  height?: number | string
  assets?: AssetReading[]
  ffdWarnings?: AlertMarker[]
  floodClassifications?: Record<number, { probability: number; severity: string; recommendation: string }>
  ffdMarkers?: FfdMarker[]
  showRivers?: boolean
  showLabels?: boolean
  showWarnings?: boolean
  showRainfall?: boolean
  showTerritories?: boolean
  territories?: FloodTerritoryFeature[]
  selectedDistrict?: string | null
  onDistrictClick?: (district: string | null) => void
  timeSlider?: number
}

function getTravelTimeColor(hours: number): string {
  for (const t of TRAVEL_TIMES) {
    if (hours >= t.min && hours < t.max) return t.color
  }
  return '#6b7280'
}

function getAssetStatusColor(asset?: AssetReading): string {
  if (!asset || asset.unit !== 'ft' || asset.value == null) return '#6b7280'
  const { warningFt, dangerFt, criticalFt, value } = asset
  if (warningFt == null && dangerFt == null && criticalFt == null) return '#6b7280'
  if (criticalFt != null && value >= criticalFt) return '#ef4444'
  if (dangerFt != null && value >= dangerFt) return '#f97316'
  if (warningFt != null && value >= warningFt) return '#eab308'
  return '#22c55e'
}

function getPulseClass(hours: number): string {
  if (hours <= 6) return 'flood-pulse-critical'
  if (hours > 24) return 'flood-pulse-slow'
  return 'flood-pulse'
}

function FocusDistrict({
  district,
  territories,
}: {
  district: string
  territories: FloodTerritoryFeature[]
}) {
  const map = useMap()
  const ready = territories.some((feature) => feature.properties.district === district)
  useEffect(() => {
    if (!ready) return
    const feature = territories.find((item) => item.properties.district === district)
    const positions = ringsForGeometry(feature?.geometry).flat()
    if (!positions.length) return
    map.fitBounds(positions, { padding: [48, 48], maxZoom: 8 })
  }, [district, ready, map])
  return null
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

function FitBounds({ assets, districtKey }: { assets: AssetReading[]; districtKey: string | null }) {
  const map = useMap()
  const lastFit = useRef<string | null>(null)
  useEffect(() => {
    const key = districtKey || '__overview__'
    if (lastFit.current === key) return
    lastFit.current = key
    if (districtKey) return
    const positions = assets
      .map((a) => (a.lat != null && a.lng != null ? ([a.lat, a.lng] as [number, number]) : null))
      .filter((c): c is [number, number] => c != null)
    if (!positions.length) {
      map.fitBounds([[24, 63], [37, 78]])
      return
    }
    const lats = positions.map((c) => c[0])
    const lngs = positions.map((c) => c[1])
    map.fitBounds(
      [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]],
      { padding: [40, 40] }
    )
  }, [districtKey, assets, map])
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
  height = '100%',
  assets = [],
  ffdWarnings,
  floodClassifications,
  ffdMarkers,
  showRivers = true,
  showLabels = true,
  showWarnings = true,
  showRainfall = false,
  showTerritories = true,
  territories = [],
  selectedDistrict = null,
  onDistrictClick,
  timeSlider = 48,
}: FloodArrivalMapProps) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const assetsById = useMemo(() => {
    const map: Record<number, AssetReading> = {}
    for (const asset of assets) map[asset.id] = asset
    return map
  }, [assets])

  const visibleSegments = useMemo(
    () => segments.filter((s) => s.travel_time_hours != null && s.travel_time_hours <= timeSlider),
    [segments, timeSlider]
  )

  const alertAssetIds = useMemo(() => {
    const ids = new Set<number>()
    for (const asset of assets) {
      if (asset.unit !== 'ft' || asset.value == null) continue
      const breached =
        (asset.criticalFt != null && asset.value >= asset.criticalFt) ||
        (asset.dangerFt != null && asset.value >= asset.dangerFt) ||
        (asset.warningFt != null && asset.value >= asset.warningFt)
      if (breached) ids.add(asset.id)
    }
    return ids
  }, [assets])

  const otTerritories = useMemo(
    () => territories.filter((feature) => Boolean(feature.properties.ot_source)),
    [territories],
  )
  const scenarioDistricts = useMemo(
    () => otTerritories.filter((feature) => feature.properties.ot_source === 'SOFT_OT_SCENARIO').length,
    [otTerritories],
  )

  if (!mounted) return <div style={{ height }} className="rounded-2xl bg-surface" />

  return (
    <div className="relative overflow-hidden rounded-2xl" style={{ height }}>
      {/* Clear selection button inside map - top left */}
      {selectedAssetId && onAssetClick && (
        <div className="absolute top-4 left-4 z-[1000]">
          <button
            onClick={() => onAssetClick(null)}
            className="flex items-center gap-1.5 rounded-lg border border-brand/25 bg-surface px-3 py-2 text-[11px] font-medium text-brand backdrop-blur hover:bg-surface-alt hover:text-brand transition-colors shadow-lg"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            Back to Overview
          </button>
        </div>
      )}

      {/* Paint-source badge - top right */}
      {otTerritories.length > 0 && (
        <div className="absolute top-4 right-4 z-[1000]">
          {scenarioDistricts > 0 ? (
            <div className="rounded-lg border border-amber-400/50 bg-amber-500/15 px-3 py-2 text-right shadow-lg backdrop-blur">
              <p className="m-0 text-[11px] font-semibold uppercase tracking-wide text-amber-300">Soft OT scenario</p>
              <p className="m-0 text-[10px] text-amber-200/80">
                {scenarioDistricts} of {otTerritories.length} districts · rest official
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-sky-400/40 bg-sky-500/15 px-3 py-2 text-right shadow-lg backdrop-blur">
              <p className="m-0 text-[11px] font-semibold uppercase tracking-wide text-sky-300">Official · IRSA / FFD</p>
              <p className="m-0 text-[10px] text-sky-200/80">No active Soft OT scenario</p>
            </div>
          )}
        </div>
      )}

      {/* Empty state - no assets from the official feed */}
      {assets.length === 0 && (
        <div className="absolute inset-0 z-[999] flex items-center justify-center bg-slate-950/60 backdrop-blur-[2px]">
          <div className="mx-6 max-w-sm rounded-xl border border-line bg-surface/95 px-6 py-5 text-center shadow-2xl">
            <p className="m-0 text-sm font-semibold text-ink">No monitoring assets available</p>
            <p className="mt-1.5 m-0 text-xs text-ink-subtle">
              The official station feed returned no assets. Arrival times stay hidden until readings are back.
            </p>
          </div>
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

        {showTerritories && territories.map((feature) => {
          const rings = ringsForGeometry(feature.geometry)
          const props = feature.properties
          if (!rings.length || !props || !isThreatened(props.flood_severity, props.alert)) return null
          const severity = (props.flood_severity || 'NONE').toUpperCase()
          const style = TERRITORY_STYLE[severity] || TERRITORY_STYLE.MODERATE
          const selected = selectedDistrict === props.district
          const inside = props.inside || []
          return rings.map((ring, ringIndex) => (
            <Polygon
              key={`territory-${props.district}-${ringIndex}`}
              positions={ring}
              pathOptions={{
                color: selected ? '#7dd3fc' : style.fill,
                weight: selected ? 3.5 : 2.5,
                fillColor: style.fill,
                fillOpacity: selected ? Math.min(style.opacity + 0.12, 0.72) : style.opacity,
                className: 'territory-alert',
              }}
              eventHandlers={{
                click: () => onDistrictClick?.(props.district),
              }}
            >
              <Tooltip>
                <div className="p-1">
                  <p className="text-sm font-semibold text-slate-900 m-0">{props.district} zone</p>
                  <p className="text-xs text-slate-700 m-0">
                    {severity} · {Math.round((props.flood_probability || 0) * 100)}% · {formatPeople(props.population_exposed || 0)} people
                  </p>
                  <p className="text-xs text-slate-700 m-0">{inside.length} places inside</p>
                  {props.ot_source === 'SOFT_OT_SCENARIO' && (
                    <p className="text-xs font-semibold text-amber-700 m-0">
                      Scenario · Soft OT twin{props.ot_device_code ? ` · ${props.ot_device_code}` : ''}
                    </p>
                  )}
                </div>
              </Tooltip>
              <Popup>
                <div className="space-y-1 min-w-[180px]">
                  <p className="text-xs font-bold m-0">{props.district}</p>
                  <p className="text-[10px] text-slate-400 m-0">{props.province} · threatened area</p>
                  <p className="text-[10px] m-0">
                    Prediction: <span className="font-semibold">{severity}</span>
                    {' '}({Math.round((props.flood_probability || 0) * 100)}%)
                  </p>
                  <p className="text-[10px] m-0">Population: <span className="font-semibold">{(props.population_exposed || 0).toLocaleString()}</span></p>
                  <p className="text-[10px] m-0">Bridges: <span className="font-semibold">{props.bridges}</span> · Hospitals: <span className="font-semibold">{props.hospitals}</span></p>
                  {inside.length > 0 && (
                    <p className="text-[10px] m-0">Inside: {inside.map((place) => place.name).slice(0, 6).join(', ')}{inside.length > 6 ? '…' : ''}</p>
                  )}
                  {props.ot_source === 'SOFT_OT_SCENARIO' && (
                    <p className="text-[10px] font-semibold text-amber-600 m-0">
                      Painted from Soft OT scenario{props.ot_device_code ? ` · ${props.ot_device_code}` : ''}
                    </p>
                  )}
                  {props.recommendation && <p className="text-[10px] m-0">{props.recommendation}</p>}
                  <p className="text-[10px] text-slate-400 m-0">Source: {props.source_asset_name}</p>
                </div>
              </Popup>
            </Polygon>
          ))
        })}

        {showTerritories && territories.flatMap((feature) => {
          const props = feature.properties
          if (!props || !isThreatened(props.flood_severity, props.alert)) return []
          return (props.inside || []).map((place) => {
            const style = INSIDE_STYLE[place.kind] || INSIDE_STYLE.town
            return (
              <CircleMarker
                key={`inside-${props.district}-${place.kind}-${place.name}`}
                center={[place.lat, place.lng]}
                radius={place.kind === 'town' || place.kind === 'asset' ? 7 : 5}
                pathOptions={{ color: style.color, fillColor: style.color, fillOpacity: 0.9, weight: 1.5 }}
              >
                <Tooltip>
                  <span className="text-xs">{style.label}: {place.name}<br />{props.district} danger zone</span>
                </Tooltip>
              </CircleMarker>
            )
          })
        })}

        {showTerritories && selectedDistrict && (
          <FocusDistrict district={selectedDistrict} territories={territories} />
        )}

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
          const fromAsset = assetsById[seg.from_id]
          const toAsset = assetsById[seg.to_id]
          const from = fromAsset && fromAsset.lat != null && fromAsset.lng != null
            ? ([fromAsset.lat, fromAsset.lng] as [number, number]) : null
          const to = toAsset && toAsset.lat != null && toAsset.lng != null
            ? ([toAsset.lat, toAsset.lng] as [number, number]) : null
          const travel = seg.travel_time_hours
          if (!from || !to || travel == null) return null
          const riverName = SEGMENT_RIVER[`${seg.from_id}-${seg.to_id}`] || seg.river
          const arrival = seg.arrival_time ? new Date(seg.arrival_time) : null
          const arrivalValid = arrival != null && !Number.isNaN(arrival.getTime())
          return (
            <FloodPulsePolyline
              key={`segment-${seg.from_id}-${seg.to_id}-${i}`}
              positions={[from, to]}
              travelTime={travel}
              tooltipContent={
                <Tooltip>
                  <div className="space-y-0.5">
                    <p className="text-[11px] font-semibold">{fromAsset?.name ?? '—'} → {toAsset?.name ?? '—'}</p>
                    {riverName && <p className="text-[10px] text-ink-subtle">{riverName} River</p>}
                    <p className="text-[10px]">Travel: <span className="font-semibold">{travel}h</span> <span className="text-ink-subtle">(model estimate)</span></p>
                    <p className="text-[10px]">
                      Arrival:{' '}
                      {arrivalValid ? (
                        <span className="font-semibold">
                          {arrival!.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : (
                        <span className="font-semibold">in {travel}h <span className="text-ink-subtle">(from now)</span></span>
                      )}
                    </p>
                    <p className="text-[10px]">Distance: <span className="font-semibold">{seg.distance_km != null ? `${seg.distance_km} km` : '—'}</span></p>
                    <p className="text-[10px]">Pop: <span className="font-semibold text-warn">{(seg.population_exposed / 1000000).toFixed(1)}M</span></p>
                  </div>
                </Tooltip>
              }
            />
          )
        })}

        {visibleSegments.map((seg, i) => {
          const fromAsset = assetsById[seg.from_id]
          const toAsset = assetsById[seg.to_id]
          const from = fromAsset && fromAsset.lat != null && fromAsset.lng != null
            ? ([fromAsset.lat, fromAsset.lng] as [number, number]) : null
          const to = toAsset && toAsset.lat != null && toAsset.lng != null
            ? ([toAsset.lat, toAsset.lng] as [number, number]) : null
          if (!from || !to) return null
          return (
            <Marker
              key={`arrow-${seg.from_id}-${seg.to_id}-${i}`}
              position={midPt(from, to)}
              icon={makeArrowIcon(from, to)}
            />
          )
        })}

        {assets.map((asset) => {
          if (asset.lat == null || asset.lng == null) return null
          const id = asset.id
          const name = asset.name
          const type = asset.assetType
          const coords: [number, number] = [asset.lat, asset.lng]
          const isSelected = id === selectedAssetId
          const hasAlert = alertAssetIds.has(id)
          const statusColor = getAssetStatusColor(asset)
          const classification = floodClassifications?.[id]
          const ffdMarker = ffdMarkers?.find(m => m.asset_id === id)
          const fresh = freshness(asset.ageHours)
          const valueLabel = asset.unit === 'ft' ? 'Level' : 'Discharge'

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
                    {type && <p className="text-[9px] text-ink-muted m-0">{type}</p>}
                    {asset.value != null && asset.unit && (
                      <p className="text-[10px] m-0">
                        <span
                          className="inline-block h-1.5 w-1.5 rounded-full mr-1 align-middle"
                          style={{ backgroundColor: fresh.color }}
                        />
                        {asset.value.toLocaleString()} {asset.unit}
                      </p>
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
                    {type && <p className="text-[10px] text-ink-muted m-0">{type}</p>}
                  </div>
                  {asset.value != null && asset.unit && (
                    <p className="text-[11px] m-0">{valueLabel}: <span className="font-semibold">{asset.value.toLocaleString()} {asset.unit}</span></p>
                  )}
                  <p className="text-[10px] m-0" style={{ color: fresh.color }}>
                    Observed {fresh.label}{asset.source ? ` · ${asset.source}` : ''}
                  </p>
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
                    className="w-full mt-1 rounded bg-brand px-2 py-1 text-[10px] font-medium text-white hover:bg-brand cursor-pointer"
                  >
                    Calculate Impact
                  </button>
                </div>
              </Popup>
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
                  {w.river && <p className="text-[10px] text-ink-muted m-0">{w.river}</p>}
                  {w.discharge_cusecs != null && (
                    <p className="text-[10px] m-0">Trigger value: <span className="font-semibold">{w.discharge_cusecs.toLocaleString()}</span></p>
                  )}
                  {w.level_ft != null && (
                    <p className="text-[10px] m-0">Trigger value: <span className="font-semibold">{w.level_ft} ft</span></p>
                  )}
                  <p className="text-[10px] m-0">Status: <span className="font-semibold" style={{ color: severityColor }}>{w.severity}</span></p>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

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
                  <p className="text-[10px] text-ink-muted m-0">{marker.river_name}</p>
                  {marker.discharge_cusecs != null && <p className="text-[10px] m-0">Discharge: <span className="font-semibold">{marker.discharge_cusecs.toLocaleString()} cusecs</span></p>}
                  {marker.gauge_level_ft != null && <p className="text-[10px] m-0">Level: <span className="font-semibold">{marker.gauge_level_ft} ft</span></p>}
                  <p className="text-[10px] m-0">Status: <span className="font-semibold" style={{ color: statusColor }}>{marker.flood_status}</span></p>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        <FitBounds assets={assets} districtKey={selectedDistrict} />
      </MapContainer>
    </div>
  )
}
