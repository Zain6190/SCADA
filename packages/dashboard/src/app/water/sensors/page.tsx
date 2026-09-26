'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
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
  const [otDevices, setOtDevices] = useState<any[]>([])

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
    fetch(`${API}/water/ot/devices`).then(r => r.ok ? r.json() : []).then(setOtDevices).catch(() => setOtDevices([]))
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
          accent="bg-ok-soft text-ok"
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
                accent={status?.status === 'OPERATIONAL' ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn'}
              />
              <KpiCard
                label="Total Readings"
                value={status?.total_readings || 0}
                icon={ExternalLink}
                accent="bg-brand-soft text-brand"
              />
              <KpiCard
                label="Latest Reading"
                value={status?.latest_reading ? fmtDateTime(status.latest_reading) : 'No readings yet'}
                icon={Radio}
              />
            </div>

            <Card>
              <CardHeader
                title="Software PLC / RTU"
                subtitle="Live Soft OT devices replace one-off test POSTs. Setpoints stay in the simulator."
                icon={<Send className="h-5 w-5" />}
                accent="bg-amber-500/10 text-amber-300"
              />
              <CardBody className="flex flex-wrap items-center gap-3">
                <Link
                  href="/water/ot"
                  className="inline-flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm font-medium text-amber-200 hover:bg-amber-500/20"
                >
                  Open Soft OT runtime
                </Link>
                <div className="w-full overflow-x-auto">
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-slate-800/50">
                      {otDevices.map((device) => (
                        <tr key={device.id || device.device_code}>
                          <td className="py-2 pr-3 font-mono text-sky-300">
                            <Link href={`/water/ot/${device.id}`}>{device.device_code}</Link>
                          </td>
                          <td className="py-2 pr-3 text-slate-400">{device.kind}</td>
                          <td className="py-2 pr-3 text-slate-300">{device.asset_name}</td>
                          <td className="py-2 text-slate-400">{device.mode || device.live?.mode || 'TRACK'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {otDevices.length === 0 && <p className="text-xs text-slate-500">OT devices appear when the API is up.</p>}
                </div>
                <button
                  onClick={sendTestReading}
                  disabled={sending}
                  className="inline-flex items-center gap-2 rounded-xl border border-brand/25 bg-brand-soft px-4 py-2.5 text-sm font-medium text-brand transition-colors hover:bg-brand-soft disabled:opacity-50"
                >
                  <Send className="h-4 w-4" />
                  {sending ? 'Sending...' : 'Send Test Reading'}
                </button>
                <button
                  onClick={sendTestReading}
                  disabled={sending}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  {sending ? 'Sending...' : 'Legacy SENSOR_API ping'}
                </button>
                {testResult && (
                  <Badge tone={testResult.includes('Error') ? 'red' : 'emerald'}>
                    {testResult}
                  </Badge>
                )}
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
                      <tr className="border-b border-line text-[11px] uppercase tracking-wider text-ink-subtle">
                        <th className="px-6 py-3 text-left font-semibold">ID</th>
                        <th className="px-6 py-3 text-left font-semibold">Asset</th>
                        <th className="px-6 py-3 text-left font-semibold">Type</th>
                        <th className="px-6 py-3 text-left font-semibold">River</th>
                        <th className="px-6 py-3 text-left font-semibold">Province</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {assets.map(asset => (
                        <tr key={asset.id} className="hover:bg-surface-alt transition-colors">
                          <td className="px-6 py-3 text-ink-muted">{asset.id}</td>
                          <td className="px-6 py-3 font-medium text-ink">{asset.canonical_name}</td>
                          <td className="px-6 py-3 text-ink-muted">{asset.asset_type}</td>
                          <td className="px-6 py-3 text-ink-muted">{asset.river}</td>
                          <td className="px-6 py-3 text-ink-muted">{asset.province}</td>
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
                <div className="rounded-xl bg-canvas p-4 font-mono text-xs">
                  <div className="text-ok font-semibold">POST</div>
                  <div className="mt-1 text-ink-muted">{API}/water/sensors/ingest</div>
                  <div className="mt-2 text-ink-subtle">{'{ "readings": [...], "source": "SENSOR_API" }'}</div>
                </div>
                <div className="mt-3 text-xs text-ink-subtle space-y-1">
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
