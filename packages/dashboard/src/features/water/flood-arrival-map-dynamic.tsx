'use client'

// packages/dashboard/src/features/water/flood-arrival-map-dynamic.tsx
// Client-only wrapper: leaflet touches `window` at module scope, so it
// must never be evaluated during server-side prerender (output: 'export').
import dynamic from 'next/dynamic'
import { Skeleton } from '@/components/ui/state'

const FloodArrivalMapInner = dynamic(
  () => import('@/features/water/flood-arrival-map').then((m) => m.FloodArrivalMap),
  {
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <Skeleton className="h-3/4 w-full" />
      </div>
    ),
    ssr: false,
  }
)

export function FloodArrivalMapDynamic(props: any) {
  return <FloodArrivalMapInner {...props} />
}
