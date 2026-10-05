// packages/dashboard/src/app/water/regions/[id]/page.tsx
// Static export requires generateStaticParams here; the interactive UI is a client component.
import { RegionDetailClient } from './client'

export function generateStaticParams() {
  const ids = Array.from({ length: 24 }, (_, i) => String(i + 1)).concat(['39', '40', '41'])
  return ids.map((id) => ({ id }))
}

export default function RegionDetailPage() {
  return <RegionDetailClient />
}
