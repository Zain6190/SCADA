'use client'

import { useState, useEffect } from 'react'
import { CloudRain, Download } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { KpiCard } from '@/components/ui/kpi'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState, ErrorState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtNumber } from '@/lib/format'
import type { FFDObservation } from '@/features/water/types'

const STATUS_BADGE_TONE: Record<string, 'emerald' | 'sky' | 'amber' | 'violet' | 'red' | 'slate'> = {
  NORMAL: 'emerald',
  BELOW_LOW: 'sky',
  LOW: 'amber',
  MEDIUM: 'violet',
  HIGH: 'red',
  VERY_HIGH: 'red',
  EXCEPTIONALLY_HIGH: 'red',
}

const RIVER_ACCENT: Record<string, string> = {
  Indus: 'border-l-sky-400',
  Kabul: 'border-l-cyan-400',
  Jhelum: 'border-l-teal-400',
  Chenab: 'border-l-emerald-400',
  Ravi: 'border-l-amber-400',
  Sutlej: 'border-l-orange-400',
}

const RIVER_DOT: Record<string, string> = {
  Indus: 'bg-sky-400',
  Kabul: 'bg-cyan-400',
  Jhelum: 'bg-teal-400',
  Chenab: 'bg-emerald-400',
  Ravi: 'bg-amber-400',
  Sutlej: 'bg-orange-400',
}

export default function FFDPage() {
  const [observations, setObservations] = useState<FFDObservation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ingesting, setIngesting] = useState(false)
  const [lastIngest, setLastIngest] = useState<string | null>(null)

  const fetchData = async () => {
    try {
      setLoading(true)
      const data = await waterApi.getFFDObservations()
      setObservations(data)
      setError(null)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleIngest = async () => {
    try {
      setIngesting(true)
      const result = await waterApi.triggerFFDIngest()
      setLastIngest(`Ingested ${result.stored} observations for ${result.date}`)
      await fetchData()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setIngesting(false)
    }
  }

  const byRiver = observations.reduce((acc, obs) => {
    const river = obs.river_name || 'Unknown'
    if (!acc[river]) acc[river] = []
    acc[river].push(obs)
    return acc
  }, {} as Record<string, FFDObservation[]>)

  const statusCounts = observations.reduce((acc, obs) => {
    acc[obs.flood_status] = (acc[obs.flood_status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="FFD Flood Bulletins"
          description="Pakistan Meteorological Department — Flood Forecasting Division"
          icon={<CloudRain className="h-6 w-6" />}
          accent="bg-cyan-500/10 text-cyan-300"
          action={
            <button
              onClick={handleIngest}
              disabled={ingesting}
              className="inline-flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-300 transition-colors hover:bg-sky-500/20 disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              {ingesting ? 'Ingesting...' : 'Ingest Latest Bulletin'}
            </button>
          }
        />

        {lastIngest && (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-emerald-300">{lastIngest}</div>
        )}

        {error && <ErrorState title="Failed to load FFD data" message={error} onRetry={fetchData} />}

        {loading ? (
          <Spinner label="Loading FFD data" />
        ) : (
          <>
            {/* Status Summary */}
            {Object.keys(statusCounts).length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                {Object.entries(statusCounts).map(([status, count]) => {
                  const tone = STATUS_BADGE_TONE[status] || 'slate'
                  const accentMap: Record<string, string> = {
                    emerald: 'bg-emerald-500/10 text-emerald-300',
                    sky: 'bg-sky-500/10 text-sky-300',
                    amber: 'bg-amber-500/10 text-amber-300',
                    violet: 'bg-violet-500/10 text-violet-300',
                    red: 'bg-red-500/10 text-red-300',
                    slate: 'bg-slate-500/10 text-slate-300',
                  }
                  return (
                    <KpiCard
                      key={status}
                      label="Stations"
                      value={count}
                      detail={status.replace(/_/g, ' ')}
                      accent={accentMap[tone]}
                    />
                  )
                })}
              </div>
            )}

            {/* River Groups */}
            {Object.entries(byRiver).map(([river, obs]) => (
              <div key={river} className="space-y-3">
                <h2 className="flex items-center gap-2.5 text-lg font-semibold text-slate-200">
                  <span className={`h-6 w-1.5 rounded-full ${RIVER_DOT[river] || 'bg-slate-500'}`} />
                  {river} River
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {obs.map(o => (
                    <Card key={o.id} className={`border-l-4 ${RIVER_ACCENT[river] || 'border-l-slate-500'}`}>
                      <CardBody>
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="font-semibold text-slate-100">{o.station_name}</h3>
                          <Badge tone={STATUS_BADGE_TONE[o.flood_status] || 'slate'}>
                            {o.flood_status.replace(/_/g, ' ')}
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-4 mb-3">
                          <div>
                            <div className="text-[11px] text-slate-500">Inflow</div>
                            <div className="text-lg font-bold text-slate-100">
                              {o.discharge_cusecs ? `${(o.discharge_cusecs / 1000).toFixed(1)}K` : '—'} <span className="text-[11px] text-slate-500">cusecs</span>
                            </div>
                          </div>
                          <div>
                            <div className="text-[11px] text-slate-500">Gauge Level</div>
                            <div className="text-lg font-bold text-slate-100">
                              {o.gauge_level_ft?.toFixed(1) || '—'} <span className="text-[11px] text-slate-500">ft</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>Trend: {o.forecast_trend}</span>
                          <span>{o.observed_at}</span>
                        </div>
                      </CardBody>
                    </Card>
                  ))}
                </div>
              </div>
            ))}

            {observations.length === 0 && (
              <EmptyState title="No FFD observations found" message='Click "Ingest Latest Bulletin" to fetch FFD data' />
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}
