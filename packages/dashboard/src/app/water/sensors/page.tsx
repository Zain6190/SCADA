'use client'

import { useEffect, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8100'

interface SensorStatus {
  status: string
  total_readings: number
  latest_reading: string | null
}

interface Asset {
  id: number
  canonical_name: string
  asset_type: string
  river: string
  province: string
  latitude: number | null
  longitude: number | null
}

interface SensorReading {
  asset_id: number
  timestamp: string
  water_level_ft?: number
  inflow_cusecs?: number
  outflow_cusecs?: number
  discharge_cusecs?: number
  sensor_id?: string
}

export default function SensorsPage() {
  const [status, setStatus] = useState<SensorStatus | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [recentReadings, setRecentReadings] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    Promise.all([
      fetch(`${API}/water/sensors/status`).then(r => r.json()),
      fetch(`${API}/water/sensors/assets`).then(r => r.json()),
      fetch(`${API}/water/observations?limit=10&source=SENSOR_API`).then(r => r.json()).catch(() => []),
    ]).then(([s, a, o]) => {
      setStatus(s)
      setAssets(a)
      setRecentReadings(Array.isArray(o) ? o : [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const sendTestReading = async () => {
    setSending(true)
    setTestResult(null)
    try {
      const resp = await fetch(`${API}/water/sensors/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          readings: [{
            asset_id: 1,
            timestamp: new Date().toISOString(),
            inflow_cusecs: 250000 + Math.floor(Math.random() * 50000),
            sensor_id: 'TEST-001',
          }],
          source: 'SENSOR_API',
        }),
      })
      const data = await resp.json()
      setTestResult(`Accepted: ${data.accepted}, Rejected: ${data.rejected}`)
    } catch (e) {
      setTestResult('Error: Failed to send test reading')
    }
    setSending(false)
  }

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-slate-400 text-sm">Loading sensor data...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Real-Time Sensors</h1>
        <p className="text-slate-400 text-sm mt-1">
          Monitor live sensor data from IoT devices pushing to the ingestion API.
        </p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <div className="text-slate-400 text-xs uppercase tracking-wider">API Status</div>
          <div className={`text-2xl font-bold mt-1 ${status?.status === 'OPERATIONAL' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {status?.status || 'UNKNOWN'}
          </div>
        </div>
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <div className="text-slate-400 text-xs uppercase tracking-wider">Total Readings</div>
          <div className="text-2xl font-bold text-sky-400 mt-1">{status?.total_readings || 0}</div>
        </div>
        <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
          <div className="text-slate-400 text-xs uppercase tracking-wider">Latest Reading</div>
          <div className="text-sm text-slate-200 mt-1">
            {status?.latest_reading ? new Date(status.latest_reading).toLocaleString() : 'No readings yet'}
          </div>
        </div>
      </div>

      {/* Test Ingestion */}
      <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-200 mb-3">Test Sensor Ingestion</h2>
        <p className="text-xs text-slate-400 mb-3">
          Send a test reading to verify the API endpoint is working.
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={sendTestReading}
            disabled={sending}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:bg-sky-800 text-white text-sm rounded-md transition-colors"
          >
            {sending ? 'Sending...' : 'Send Test Reading'}
          </button>
          {testResult && (
            <span className={`text-sm ${testResult.includes('Error') ? 'text-red-400' : 'text-emerald-400'}`}>
              {testResult}
            </span>
          )}
        </div>
      </div>

      {/* Monitored Assets */}
      <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-200 mb-3">Monitored Assets ({assets.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs uppercase tracking-wider border-b border-slate-700">
                <th className="text-left py-2 px-3">ID</th>
                <th className="text-left py-2 px-3">Asset</th>
                <th className="text-left py-2 px-3">Type</th>
                <th className="text-left py-2 px-3">River</th>
                <th className="text-left py-2 px-3">Province</th>
              </tr>
            </thead>
            <tbody>
              {assets.map(asset => (
                <tr key={asset.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="py-2 px-3 text-slate-300">{asset.id}</td>
                  <td className="py-2 px-3 text-slate-100 font-medium">{asset.canonical_name}</td>
                  <td className="py-2 px-3 text-slate-400">{asset.asset_type}</td>
                  <td className="py-2 px-3 text-slate-400">{asset.river}</td>
                  <td className="py-2 px-3 text-slate-400">{asset.province}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* API Documentation */}
      <div className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-200 mb-3">API Endpoint</h2>
        <div className="bg-slate-900 rounded-md p-3 font-mono text-xs text-slate-300">
          <div className="text-emerald-400">POST</div>
          <div className="mt-1">{API}/water/sensors/ingest</div>
          <div className="mt-2 text-slate-500">{'{ "readings": [...], "source": "SENSOR_API" }'}</div>
        </div>
        <div className="mt-3 text-xs text-slate-400">
          <p>Fields: asset_id (required), timestamp (required), water_level_ft, inflow_cusecs, outflow_cusecs, discharge_cusecs, sensor_id</p>
          <p className="mt-1">Max batch size: 100 readings per request</p>
        </div>
      </div>
    </div>
  )
}
