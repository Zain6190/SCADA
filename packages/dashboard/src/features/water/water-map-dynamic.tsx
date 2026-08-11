'use client'

// packages/dashboard/src/features/water/water-map-dynamic.tsx
// Client-only wrapper: leaflet touches `window` at module scope, so it
// must never be evaluated during server-side prerender (output: 'export').
import dynamic from 'next/dynamic'
import { Skeleton } from '@/components/ui/state'

const WaterMapInner = dynamic(
  () => import('@/features/water/water-map').then((m) => m.WaterMap),
  {
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <Skeleton className="h-3/4 w-full" />
      </div>
    ),
    ssr: false,
  }
)

export function WaterMapDynamic(props: any) {
  return <WaterMapInner {...props} />
}