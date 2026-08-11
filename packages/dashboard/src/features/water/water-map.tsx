'use client'

// packages/dashboard/src/features/water/water-map.tsx
// Leaflet choropleth of Pakistan SCADA regions colored by WAI severity.
import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Polygon, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { SEVERITY_STYLES, normalizeSeverity, type SeverityLevel } from '@/lib/severity'

type Geo = { type?: string; coordinates?: any }

/** Convert GeoJSON coords ([lng,lat]) to Leaflet LatLng rings. */
function ringsForGeometry(geometry: Geo | undefined): [number, number][][] {
  if (!geometry?.coordinates) return []
  const c = geometry.coordinates
  if (geometry.type === 'Polygon') {
    return [(c as any[]).map((pt) => [pt[1], pt[0]])]
  }
  if (geometry.type === 'MultiPolygon') {
    return (c as any[]).flatMap((poly: any) =>
      poly.map((ring: any) => ring.map((pt: any) => [pt[1], pt[0]]))
    )
  }
  return []
}

function ringsFor(feature: any): [number, number][][] {
  return ringsForGeometry(feature?.geometry)
}

function FeaturePolygons({
  feature,
  onSelect,
}: {
  feature: any
  onSelect?: (f: any) => void
}) {
  const rings = ringsFor(feature)
  const severity: SeverityLevel = normalizeSeverity(feature.severity)
  const style = SEVERITY_STYLES[severity]
  if (!rings.length) return null

  return (
    <>
      {rings.map((ring, i) => (
        <Polygon
          key={`${feature.regionId}-${i}`}
          positions={ring}
          pathOptions={{
            color: style.dot,
            weight: severity === 'Critical' || severity === 'Severe' ? 2.5 : 1.5,
            fillColor: style.dot,
            fillOpacity: severity === 'Critical' || severity === 'Severe' ? 0.55 : 0.35,
          }}
          eventHandlers={{ click: () => onSelect?.(feature) }}
        >
          <Tooltip>
            <div className="p-1">
              <p className="text-sm font-semibold text-slate-900">{feature.name}</p>
              <p className="text-xs text-slate-700">
                WAI {feature.waiScore ?? '—'} · {style.label}
              </p>
            </div>
          </Tooltip>
        </Polygon>
      ))}
    </>
  )
}

function FitRegion({ features }: { features: any[] }) {
  const map = useMap()
  useEffect(() => {
    if (!features?.length) return
    const pts = features.flatMap((f) => ringsFor(f)).flat()
    if (!pts.length) return
    let latMin = Infinity,
      latMax = -Infinity,
      lngMin = Infinity,
      lngMax = -Infinity
    for (const [lat, lng] of pts) {
      if (lat < latMin) latMin = lat
      if (lat > latMax) latMax = lat
      if (lng < lngMin) lngMin = lng
      if (lng > lngMax) lngMax = lng
    }
    map.fitBounds(
      [
        [latMin, lngMin],
        [latMax, lngMax],
      ],
      { padding: [30, 30] }
    )
  }, [features, map])
  return null
}

export type WaterMapProps = {
  features: any[]
  height?: number
  onSelect?: (feature: any) => void
}

export function WaterMap({ features, height = 520, onSelect }: WaterMapProps) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  if (!mounted) return <div style={{ height }} />

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-800" style={{ height }}>
      <MapContainer
        center={[30.0, 69.35]}
        zoom={5}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%', background: '#0b1220' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {features.map((f, idx) => (
          <FeaturePolygons key={`${f.regionId}-${idx}`} feature={f} onSelect={onSelect} />
        ))}
        <FitRegion features={features} />
      </MapContainer>
    </div>
  )
}