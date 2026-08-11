'use client'

// packages/dashboard/src/components/map/leaflet-setup.tsx
// Loads Leaflet CSS once (Next.js/SSR guard).
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

// Fix default marker icons under bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

export {}