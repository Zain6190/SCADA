'use client'

// packages/dashboard/src/app/water/flood-map/page.tsx
// AquaVision Flood Arrival Map - real-time flood propagation visualization.
import { useState, useEffect } from 'react'
import { Map } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { FloodArrivalMapDynamic } from '@/features/water/flood-arrival-map-dynamic'
import { fmtNumber } from '@/lib/format'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8100'

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

interface ImpactSummary {
  source_asset: string
  release_flow_cusecs: number
  total_population_exposed: number
  total_bridges: number
  total_hospitals: number
  total_travel_hours: number
  furthest_asset: string
  segments: Array<{
    segment_order: number
    river_name: string
    upstream_asset: string
    downstream_asset: string
    distance_km: number
    travel_time_hours: number
    population_exposed: number
    bridges_count: number
    hospitals_count: number
  }>
}

interface Alert {
  id: number
  asset_name: string
  severity: string
  message: string
  downstream_population_exposed?: number
  downstream_bridges_at_risk?: number
  downstream_hospitals_at_risk?: number
  flood_probability?: number
  flood_severity?: string
}

const ASSET_MAP: Record<string, number> = {
  'Tarbela': 1, 'Mangla': 2, 'Chashma': 3, 'Kalabagh': 4,
  'Taunsa': 5, 'Guddu': 6, 'Sukkur': 7, 'Kotri': 8,
  'Kabul @ Nowshera': 9, 'Nowshera': 9, 'Chenab @ Marala': 10, 'Marala': 10,
  'Panjnad': 11,
}

export default function FloodMapPage() {
  const [segments, setSegments] = useState<SegmentData[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null)
  const [impactSummary, setImpactSummary] = useState<ImpactSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch pre-calculated impacts and active alerts
  useEffect(() => {
    async function fetchData() {
      try {
        const [impRes, alertRes] = await Promise.all([
          fetch(`${API_BASE}/water/impact/precalculated`),
          fetch(`${API_BASE}/water/alerts?status=New&severity=Warning,Danger,Critical`),
        ])

        if (impRes.ok) {
          const impacts = await impRes.json()
          const segs: SegmentData[] = impacts.map((imp: any) => ({
            from_id: imp.source_asset_id,
            to_id: imp.downstream_asset_id || imp.source_asset_id + 1,
            river: imp.notes?.includes('Indus') ? 'Indus' : imp.notes?.includes('Jhelum') ? 'Jhelum' : imp.notes?.includes('Kabul') ? 'Kabul' : imp.notes?.includes('Chenab') ? 'Chenab' : 'Indus',
            travel_time_hours: imp.travel_time_hours_expected || imp.travel_time_hours_min || 24,
            distance_km: imp.distance_km || 100,
            population_exposed: imp.affected_population_est || 0,
            bridges: imp.bridges_count || 0,
            hospitals: imp.hospitals_count || 0,
          }))
          setSegments(segs)
        }

        if (alertRes.ok) {
          const data = await alertRes.json()
          setAlerts(data.items || data || [])
        }
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  // Calculate impact when asset is clicked
  useEffect(() => {
    if (!selectedAsset) { setImpactSummary(null); return }
    async function calc() {
      setCalculating(true)
      try {
        const res = await fetch(`${API_BASE}/water/impact/calculate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_asset_id: selectedAsset,
            release_flow_cusecs: 100000,
            release_time: new Date().toISOString(),
          }),
        })
        if (res.ok) setImpactSummary(await res.json())
      } catch {}
      setCalculating(false)
    }
    calc()
  }, [selectedAsset])

  // Build segments for selected asset
  const displaySegments = selectedAsset && impactSummary
    ? impactSummary.segments.map(s => ({
        from_id: ASSET_MAP[s.upstream_asset] || 1,
        to_id: ASSET_MAP[s.downstream_asset] || 1,
        river: s.river_name,
        travel_time_hours: s.travel_time_hours,
        distance_km: s.distance_km,
        population_exposed: s.population_exposed,
        bridges: s.bridges_count,
        hospitals: s.hospitals_count,
      }))
    : segments

  const totalPop = displaySegments.reduce((sum, s) => sum + s.population_exposed, 0)
  const totalBridges = displaySegments.reduce((sum, s) => sum + s.bridges, 0)
  const totalHospitals = displaySegments.reduce((sum, s) => sum + s.hospitals, 0)
  const maxTravel = Math.max(...displaySegments.map(s => s.travel_time_hours), 0)

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Flood Arrival Map"
          description="Real-time flood propagation across Pakistan's river network. Click assets to calculate downstream impact."
          icon={<Map className="h-6 w-6" />}
          action={
            displaySegments.length ? (
              <Badge tone="sky">{displaySegments.length} segments rendered</Badge>
            ) : undefined
          }
        />

        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card className="px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">Population at Risk</p>
            <p className="text-xl font-bold text-white">{(totalPop / 1000000).toFixed(1)}M</p>
          </Card>
          <Card className="px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">Bridges</p>
            <p className="text-xl font-bold text-amber-400">{totalBridges}</p>
          </Card>
          <Card className="px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">Hospitals</p>
            <p className="text-xl font-bold text-rose-400">{totalHospitals}</p>
          </Card>
          <Card className="px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-slate-500">Max Travel Time</p>
            <p className="text-xl font-bold text-sky-400">{maxTravel.toFixed(0)}h</p>
          </Card>
        </div>

        {/* Map */}
        {loading ? (
          <div className="flex h-[600px] items-center justify-center">
            <Spinner label="Loading flood map" />
          </div>
        ) : error ? (
          <ErrorState message={error} />
        ) : (
          <FloodArrivalMapDynamic
            segments={displaySegments}
            selectedAssetId={selectedAsset}
            onAssetClick={setSelectedAsset}
            height={600}
          />
        )}

        {/* Selected asset impact summary */}
        {selectedAsset && (
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white">
                Impact: {impactSummary?.source_asset || `Asset ${selectedAsset}`}
                {calculating && <span className="ml-2 text-xs text-slate-400">Calculating...</span>}
              </h3>
              {impactSummary && (
                <Badge tone={impactSummary.total_population_exposed > 5000000 ? 'red' : impactSummary.total_population_exposed > 1000000 ? 'amber' : 'emerald'}>
                  {(impactSummary.total_population_exposed / 1000000).toFixed(1)}M exposed
                </Badge>
              )}
            </div>

            {impactSummary && (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-5 text-xs">
                <div>
                  <p className="text-slate-500">Release Flow</p>
                  <p className="font-semibold text-white">{fmtNumber(impactSummary.release_flow_cusecs)} cusecs</p>
                </div>
                <div>
                  <p className="text-slate-500">Total Distance</p>
                  <p className="font-semibold text-white">{impactSummary.segments[impactSummary.segments.length - 1]?.distance_km?.toFixed(0) || '—'} km</p>
                </div>
                <div>
                  <p className="text-slate-500">Travel Time</p>
                  <p className="font-semibold text-white">{impactSummary.total_travel_hours?.toFixed(1) || '—'}h</p>
                </div>
                <div>
                  <p className="text-slate-500">Furthest Asset</p>
                  <p className="font-semibold text-white">{impactSummary.furthest_asset}</p>
                </div>
                <div>
                  <p className="text-slate-500">Rivers Affected</p>
                  <p className="font-semibold text-white">{impactSummary.segments.length} segments</p>
                </div>
              </div>
            )}
          </Card>
        )}

        {/* Active alerts */}
        {alerts.length > 0 && (
          <Card className="p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Active Flood Alerts ({alerts.length})</h3>
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {alerts.slice(0, 20).map(alert => (
                <div key={alert.id} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                  <div className="flex-1">
                    <p className="text-xs font-medium text-white">{alert.asset_name}</p>
                    <p className="text-[11px] text-slate-400 line-clamp-1">{alert.message}</p>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    {alert.downstream_population_exposed != null && (
                      <span className="text-[10px] text-amber-400">{(alert.downstream_population_exposed / 1000000).toFixed(1)}M</span>
                    )}
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      alert.severity === 'Critical' ? 'bg-red-500/20 text-red-400' :
                      alert.severity === 'Danger' ? 'bg-orange-500/20 text-orange-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>{alert.severity}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </AppShell>
  )
}
