'use client'

import { useEffect, useState } from 'react'
import { Radio, Send, ExternalLink } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { KpiCard } from '@/components/ui/kpi'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState, ErrorState } from '@/components/ui/state'
import { fmtDateTime } from '@/lib/format'

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

export default function SensorsPage() {
  const [status, setStatus] = useState<SensorStatus | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    Promise.all([
      fetch(`${API}/water/sensors/status`).then(r => r.json()),
      fetch(`${API}/water/sensors/assets`).then(r => r.json()),
    ]).then(([s, a]) => {
      setStatus(s)
      setAssets(a)
      setLoading(false)
    }).catch(e => {
      setError(e.message)
      setLoading(false)
    })
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
    } catch {
      setTestResult('Error: Failed to send test reading')
    }
    setSending(false)
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Real-Time Sensors"
          description="Monitor live sensor data from IoT devices pushing to the ingestion API"
          icon={<Radio className="h-6 w-6" />}
          accent="bg-emerald-500/10 text-emerald-300"
        />

        {loading ? (
          <Spinner label="Loading sensor data" />
        ) : error ? (
          <ErrorState title="Failed to load sensor data" message={error} onRetry={() => window.location.reload()} />
        ) : (
          <>
            {/* Status KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
              <KpiCard
                label="API Status"
                value={status?.status || 'UNKNOWN'}
                icon={Radio}
                accent={status?.status === 'OPERATIONAL' ? 'bg-emerald-500/10 text-emerald-300' : 'bg-amber-500/10 text-amber-300'}
              />
              <KpiCard
                label="Total Readings"
                value={status?.total_readings || 0}
                icon={ExternalLink}
                accent="bg-sky-500/10 text-sky-300"
              />
              <KpiCard
                label="Latest Reading"
                value={status?.latest_reading ? fmtDateTime(status.latest_reading) : 'No readings yet'}
                icon={Radio}
              />
            </div>

            {/* Test Ingestion */}
            <Card>
              <CardHeader
                title="Test Sensor Ingestion"
                subtitle="Send a test reading to verify the API endpoint is working"
                icon={<Send className="h-5 w-5" />}
                accent="bg-sky-500/10 text-sky-300"
              />
              <CardBody>
                <div className="flex items-center gap-3">
                  <button
                    onClick={sendTestReading}
                    disabled={sending}
                    className="inline-flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-300 transition-colors hover:bg-sky-500/20 disabled:opacity-50"
                  >
                    <Send className="h-4 w-4" />
                    {sending ? 'Sending...' : 'Send Test Reading'}
                  </button>
                  {testResult && (
                    <Badge tone={testResult.includes('Error') ? 'red' : 'emerald'}>
                      {testResult}
                    </Badge>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Monitored Assets */}
            <Card>
              <CardHeader
                title={`Monitored Assets (${assets.length})`}
                icon={<Radio className="h-5 w-5" />}
              />
              <CardBody className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                        <th className="px-6 py-3 text-left font-semibold">ID</th>
                        <th className="px-6 py-3 text-left font-semibold">Asset</th>
                        <th className="px-6 py-3 text-left font-semibold">Type</th>
                        <th className="px-6 py-3 text-left font-semibold">River</th>
                        <th className="px-6 py-3 text-left font-semibold">Province</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                      {assets.map(asset => (
                        <tr key={asset.id} className="hover:bg-slate-800/30 transition-colors">
                          <td className="px-6 py-3 text-slate-400">{asset.id}</td>
                          <td className="px-6 py-3 font-medium text-slate-200">{asset.canonical_name}</td>
                          <td className="px-6 py-3 text-slate-400">{asset.asset_type}</td>
                          <td className="px-6 py-3 text-slate-400">{asset.river}</td>
                          <td className="px-6 py-3 text-slate-400">{asset.province}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardBody>
            </Card>

            {/* API Documentation */}
            <Card>
              <CardHeader
                title="API Endpoint"
                icon={<ExternalLink className="h-5 w-5" />}
              />
              <CardBody>
                <div className="rounded-xl bg-slate-950/50 p-4 font-mono text-xs">
                  <div className="text-emerald-400 font-semibold">POST</div>
                  <div className="mt-1 text-slate-300">{API}/water/sensors/ingest</div>
                  <div className="mt-2 text-slate-600">{'{ "readings": [...], "source": "SENSOR_API" }'}</div>
                </div>
                <div className="mt-3 text-xs text-slate-500 space-y-1">
                  <p>Fields: asset_id (required), timestamp (required), water_level_ft, inflow_cusecs, outflow_cusecs, discharge_cusecs, sensor_id</p>
                  <p>Max batch size: 100 readings per request</p>
                </div>
              </CardBody>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  )
}
