'use client'

import { useEffect, useState, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Radio, RefreshCw, AlertTriangle, Play } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { KpiCard } from '@/components/ui/kpi'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtNumber } from '@/lib/format'

const AMBER = 'bg-amber-500/10 text-amber-300'

export default function SoftOtPage() {
  return (
    <Suspense fallback={null}>
      <SoftOtContent />
    </Suspense>
  )
}

function SoftOtContent() {
  const search = useSearchParams()
  const focusAsset = Number(search.get('asset') || 0)
  const [status, setStatus] = useState<any>(null)
  const [devices, setDevices] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ticking, setTicking] = useState(false)

  const load = () => {
    Promise.all([waterApi.getOtStatus(), waterApi.getOtDevices()])
      .then(([s, d]) => {
        setStatus(s)
        setDevices(d)
        setError(null)
      })
      .catch((e) => setError(e?.message || 'Failed to load Soft OT'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  const runTick = async () => {
    setTicking(true)
    try {
      await waterApi.runOtTick()
      load()
    } finally {
      setTicking(false)
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Soft PLC / RTU Runtime"
          description="Software PLC/RTU twin. Track mode replays the official IRSA and FFD day. A setpoint switches that asset to scenario and never commands a real dam."
          icon={<Radio className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">SIMULATION — no hardware</Badge>}
          action={
            <button
              onClick={runTick}
              disabled={ticking}
              className="inline-flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-300 hover:bg-sky-500/20 disabled:opacity-50"
            >
              {ticking ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run tick
            </button>
          }
        />

        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          Track readings are an official replay at priority 4. Scenario readings stay on SOFT_OT. IRSA and FFD rows are never overwritten.
        </div>

        {status?.anchor_banner || status?.anchor?.banner ? (
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-200">
            {status.anchor_banner || status.anchor?.banner}
            {status?.coverage?.days ? (
              <span className="block mt-1 text-xs text-sky-300/80">
                {status.coverage.days} official days loaded
                {status.coverage.first ? `, ${status.coverage.first}` : ''}
                {status.coverage.last ? ` to ${status.coverage.last}` : ''}.
                Cursor {status.coverage.cursor || '—'}.
                {status.coverage.holding_latest ? ' Holding the latest day.' : ' Replaying the series.'}
              </span>
            ) : null}
          </div>
        ) : null}

        {loading ? (
          <Spinner label="Loading Soft OT devices" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard label="Devices" value={status?.devices ?? 0} icon={Radio} accent="bg-sky-500/10 text-sky-300" />
              <KpiCard label="Soft RTUs" value={status?.rtu ?? 0} detail="15 min store-and-forward" icon={Radio} accent="bg-emerald-500/10 text-emerald-300" />
              <KpiCard label="Soft PLCs" value={status?.plc ?? 0} detail="scan + gate interlocks" icon={Radio} accent="bg-violet-500/10 text-violet-300" />
              <KpiCard label="Official days" value={status?.coverage?.days ?? 0} detail={status?.coverage?.last ? `latest ${status.coverage.last}` : 'series not loaded'} icon={Radio} />
            </div>

            <Card>
              <CardHeader title="Field devices" subtitle="Click a device to open the Virtual HMI" />
              <CardBody className="p-0">
                {devices.length === 0 ? (
                  <EmptyState title="No OT devices" message="Apply migration 015 and restart the API so the catalog can seed." />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                          <th className="px-4 py-3 text-left">Device</th>
                          <th className="px-4 py-3 text-left">Kind</th>
                          <th className="px-4 py-3 text-left">Asset</th>
                          <th className="px-4 py-3 text-left">Level</th>
                          <th className="px-4 py-3 text-left">Discharge</th>
                          <th className="px-4 py-3 text-left">Gate</th>
                          <th className="px-4 py-3 text-left">Mode</th>
                          <th className="px-4 py-3 text-left">Comms</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {devices.map((d) => (
                          <tr key={d.id} className={`hover:bg-slate-800/30 ${focusAsset === d.asset_id ? 'bg-sky-500/10' : ''}`}>
                            <td className="px-4 py-3">
                              <Link href={`/water/ot/${d.id}`} className="font-mono text-sky-300 hover:underline">
                                {d.device_code}
                              </Link>
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={d.kind === 'PLC' ? 'violet' : 'emerald'}>{d.kind}</Badge>
                            </td>
                            <td className="px-4 py-3 text-slate-200">{d.asset_name}</td>
                            <td className="px-4 py-3 font-mono text-slate-300">
                              {d.live?.ai?.level_ft != null ? `${fmtNumber(d.live.ai.level_ft)} ft` : '—'}
                            </td>
                            <td className="px-4 py-3 font-mono text-slate-300">
                              {d.live?.ai?.discharge_cusecs != null ? fmtNumber(d.live.ai.discharge_cusecs) : '—'}
                            </td>
                            <td className="px-4 py-3 font-mono text-slate-300">
                              {d.kind === 'PLC' && d.live?.gate_pos_pct != null
                                ? `${fmtNumber(d.live.gate_pos_pct)}%`
                                : '—'}
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={d.mode === 'SCENARIO' || d.live?.mode === 'SCENARIO' ? 'amber' : 'sky'}>
                                {d.mode || d.live?.mode || 'TRACK'}
                              </Badge>
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={d.comms_ok ? 'emerald' : 'red'}>{d.comms_ok ? 'OK' : 'DOWN'}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardBody>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  )
}
