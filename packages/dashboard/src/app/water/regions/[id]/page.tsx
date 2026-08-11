// packages/dashboard/src/app/water/regions/[id]/page.tsx
// Static export requires generateStaticParams here; the interactive UI is a client component.
import { RegionDetailClient } from './client'

export function generateStaticParams() {
  return Array.from({ length: 24 }, (_, i) => ({ id: String(i + 1) }))
}

export default function RegionDetailPage() {
  return <RegionDetailClient />
}