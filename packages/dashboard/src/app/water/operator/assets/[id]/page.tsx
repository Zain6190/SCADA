// packages/dashboard/src/app/water/operator/assets/[id]/page.tsx
// Static export requires generateStaticParams here; the interactive UI is a client component.
import { AssetDetailClient } from './client'

export function generateStaticParams() {
  return Array.from({ length: 11 }, (_, i) => ({ id: String(i + 1) }))
}

export default function AssetDetailPage() {
  return <AssetDetailClient />
}
