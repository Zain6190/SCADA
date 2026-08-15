'use client'

import { useState, useEffect } from 'react'
import { waterApi } from '@/features/water/api'
import type { FFDObservation } from '@/features/water/types'

const STATUS_COLORS: Record<string, string> = {
  NORMAL: 'bg-green-100 text-green-800',
  BELOW_LOW: 'bg-blue-100 text-blue-800',
  LOW: 'bg-yellow-100 text-yellow-800',
  MEDIUM: 'bg-orange-100 text-orange-800',
  HIGH: 'bg-red-100 text-red-800',
  VERY_HIGH: 'bg-red-200 text-red-900',
  EXCEPTIONALLY_HIGH: 'bg-red-300 text-red-900',
}

const RIVER_COLORS: Record<string, string> = {
  Indus: 'border-l-blue-500',
  Kabul: 'border-l-cyan-500',
  Jhelum: 'border-l-teal-500',
  Chenab: 'border-l-green-500',
  Ravi: 'border-l-amber-500',
  Sutlej: 'border-l-orange-500',
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

  useEffect(() => {
    fetchData()
  }, [])

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

  // Group by river
  const byRiver = observations.reduce((acc, obs) => {
    const river = obs.river_name || 'Unknown'
    if (!acc[river]) acc[river] = []
    acc[river].push(obs)
    return acc
  }, {} as Record<string, FFDObservation[]>)

  // Count by status
  const statusCounts = observations.reduce((acc, obs) => {
    acc[obs.flood_status] = (acc[obs.flood_status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">FFD Flood Bulletins</h1>
            <p className="text-slate-600 mt-1">Pakistan Meteorological Department - Flood Forecasting Division</p>
          </div>
          <button
            onClick={handleIngest}
            disabled={ingesting}
            className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {ingesting ? 'Ingesting...' : 'Ingest Latest Bulletin'}
          </button>
        </div>

        {lastIngest && (
          <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-xl text-green-800">
            {lastIngest}
          </div>
        )}

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-800">
            {error}
          </div>
        )}

        {/* Status Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {Object.entries(statusCounts).map(([status, count]) => (
            <div key={status} className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
              <div className="text-sm text-slate-500">Stations</div>
              <div className={`text-lg font-bold ${STATUS_COLORS[status]?.split(' ')[1] || 'text-slate-900'}`}>
                {status.replace(/_/g, ' ')}
              </div>
              <div className="text-2xl font-bold text-slate-900">{count}</div>
            </div>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="mt-4 text-slate-600">Loading FFD data...</p>
          </div>
        )}

        {/* River Groups */}
        {!loading && Object.entries(byRiver).map(([river, obs]) => (
          <div key={river} className="mb-8">
            <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
              <span className={`w-3 h-8 rounded ${RIVER_COLORS[river]?.replace('border-l-', 'bg-') || 'bg-slate-400'}`} />
              {river} River
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {obs.map((o) => (
                <div
                  key={o.id}
                  className={`bg-white rounded-2xl border border-slate-200 shadow-sm p-5 border-l-4 ${RIVER_COLORS[river] || 'border-l-slate-400'}`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-bold text-slate-900">{o.station_name}</h3>
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[o.flood_status] || 'bg-slate-100 text-slate-800'}`}>
                      {o.flood_status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 mb-3">
                    <div>
                      <div className="text-xs text-slate-500">Inflow</div>
                      <div className="text-lg font-bold text-slate-900">
                        {o.discharge_cusecs ? `${(o.discharge_cusecs / 1000).toFixed(1)}K` : '-'} <span className="text-xs text-slate-500">cusecs</span>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Gauge Level</div>
                      <div className="text-lg font-bold text-slate-900">
                        {o.gauge_level_ft?.toFixed(1) || '-'} <span className="text-xs text-slate-500">ft</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>Trend: {o.forecast_trend}</span>
                    <span>{o.observed_at}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {!loading && observations.length === 0 && (
          <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
            <p className="text-slate-500 text-lg">No FFD observations found</p>
            <p className="text-slate-400 mt-2">Click "Ingest Latest Bulletin" to fetch FFD data</p>
          </div>
        )}
      </div>
    </div>
  )
}
