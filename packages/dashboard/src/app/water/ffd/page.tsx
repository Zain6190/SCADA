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
  Indus: 'border-l-[#15467E]',
  Kabul: 'border-l-[#0E7490]',
  Jhelum: 'border-l-[#0F766E]',
  Chenab: 'border-l-[#15693C]',
  Ravi: 'border-l-[#9A5B06]',
  Sutlej: 'border-l-[#A8470E]',
}

const RIVER_DOT: Record<string, string> = {
  Indus: 'bg-brand',
  Kabul: 'bg-brand',
  Jhelum: 'bg-ok',
  Chenab: 'bg-ok',
  Ravi: 'bg-warn',
  Sutlej: 'bg-sev-severe',
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
          accent="bg-brand-soft text-brand"
          action={
            <button
              onClick={handleIngest}
              disabled={ingesting}
              className="inline-flex items-center gap-2 rounded-xl border border-brand/25 bg-brand-soft px-4 py-2.5 text-sm font-medium text-brand transition-colors hover:bg-brand-soft disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              {ingesting ? 'Ingesting...' : 'Ingest Latest Bulletin'}
            </button>
          }
        />

        {lastIngest && (
          <div className="rounded-xl border border-ok/25 bg-ok-soft p-4 text-sm text-ok">{lastIngest}</div>
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
                    emerald: 'bg-ok-soft text-ok',
                    sky: 'bg-brand-soft text-brand',
                    amber: 'bg-warn-soft text-warn',
                    violet: 'bg-brand-soft text-brand',
                    red: 'bg-crit-soft text-crit',
                    slate: 'bg-surface-sunken text-ink-muted',
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
                <h2 className="flex items-center gap-2.5 text-lg font-semibold text-ink">
                  <span className={`h-6 w-1.5 rounded-full ${RIVER_DOT[river] || 'bg-surface-sunken'}`} />
                  {river} River
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {obs.map(o => (
                    <Card key={o.id} className={`border-l-4 ${RIVER_ACCENT[river] || 'border-l-line-strong'}`}>
                      <CardBody>
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="font-semibold text-ink">{o.station_name}</h3>
                          <Badge tone={STATUS_BADGE_TONE[o.flood_status] || 'slate'}>
                            {o.flood_status.replace(/_/g, ' ')}
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-4 mb-3">
                          <div>
                            <div className="text-[11px] text-ink-subtle">Inflow</div>
                            <div className="text-lg font-bold text-ink">
                              {o.discharge_cusecs ? `${(o.discharge_cusecs / 1000).toFixed(1)}K` : '—'} <span className="text-[11px] text-ink-subtle">cusecs</span>
                            </div>
                          </div>
                          <div>
                            <div className="text-[11px] text-ink-subtle">Gauge Level</div>
                            <div className="text-lg font-bold text-ink">
                              {o.gauge_level_ft?.toFixed(1) || '—'} <span className="text-[11px] text-ink-subtle">ft</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-ink-subtle">
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
