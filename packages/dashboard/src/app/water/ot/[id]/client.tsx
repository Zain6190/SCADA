'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { Radio, AlertTriangle, SlidersHorizontal } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtNumber, fmtDateTime } from '@/lib/format'

const FAULTS = [
  { id: 'comms_down', label: 'Comms down' },
  { id: 'sensor_stuck', label: 'Sensor stuck' },
  { id: 'actuator_jam', label: 'Actuator jam' },
  { id: 'inflow_surge', label: 'Inflow surge' },
  { id: 'clear', label: 'Clear faults' },
]

export function OtDeviceClient() {
  const params = useParams()
  const id = Number(params.id)
  const [device, setDevice] = useState<any>(null)
  const [status, setStatus] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [gate, setGate] = useState(40)
  const [busy, setBusy] = useState(false)
  const [banner, setBanner] = useState<string | null>(null)

  const load = () => {
    Promise.all([waterApi.getOtDevice(id), waterApi.getOtStatus().catch(() => null)])
      .then(([d, s]) => {
        setDevice(d)
        setStatus(s)
        if (d.live?.gate_cmd_pct != null) setGate(d.live.gate_cmd_pct)
        setError(null)
      })
      .catch((e) => setError(e?.message || 'Failed to load device'))
  }

  useEffect(() => {
    if (!id) return
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [id])

  const sendSetpoint = async () => {
    if (!device) return
    setBusy(true)
    try {
      const res = await waterApi.otSetpoint(device.asset_id, gate)
      setBanner(res.banner || 'Setpoint applied to simulator only')
      load()
    } catch (e: any) {
      setBanner(e?.response?.data?.detail || e?.message || 'Setpoint failed')
    } finally {
      setBusy(false)
    }
  }

  const sendFault = async (kind: string) => {
    if (!device) return
    setBusy(true)
    try {
      const res = await waterApi.otFault(device.asset_id, kind)
      setBanner(res.banner || `Fault ${kind} injected`)
      load()
    } catch (e: any) {
      setBanner(e?.response?.data?.detail || e?.message || 'Fault failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title={device?.device_code || 'OT device'}
          description={device ? `${device.kind} on ${device.asset_name}` : 'Software field device'}
          icon={<Radio className="h-6 w-6" />}
          badge={
            <div className="flex items-center gap-2">
              <Badge tone={device?.mode === 'SCENARIO' || device?.live?.mode === 'SCENARIO' ? 'amber' : 'sky'}>
                {device?.mode || device?.live?.mode || 'TRACK'}
              </Badge>
              <Link href="/water/ot"><Badge tone="slate">All devices</Badge></Link>
            </div>
          }
        />

        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          SIMULATION — Virtual HMI commands stay inside the Soft PLC/RTU. They do not control real infrastructure.
        </div>
        {(status?.anchor_banner || status?.anchor?.banner) && (
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-200">
            {status.anchor_banner || status.anchor?.banner}
          </div>
        )}

        {banner && (
          <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm text-sky-200">{banner}</div>
        )}

        {!device && !error ? (
          <Spinner label="Loading device" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : (
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Live tags" subtitle="AO/DO stay in the simulator; AI/DI are published" />
              <CardBody className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-4 py-2 text-left">Tag</th>
                      <th className="px-4 py-2 text-left">Class</th>
                      <th className="px-4 py-2 text-left">Value</th>
                      <th className="px-4 py-2 text-left">To AquaVision</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {(device.tags || []).map((t: any) => (
                      <tr key={t.name}>
                        <td className="px-4 py-2 font-mono text-slate-200">{t.name}</td>
                        <td className="px-4 py-2"><Badge tone="slate">{t.tag_class}</Badge></td>
                        <td className="px-4 py-2 font-mono text-slate-300">
                          {t.value == null ? '—' : fmtNumber(t.value)} {t.unit || ''}
                        </td>
                        <td className="px-4 py-2 text-slate-400">{t.published_to_aquavision ? 'AI/DI publish' : 'HMI / internal'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardBody>
            </Card>

            <div className="space-y-6">
              {device.kind === 'PLC' && (
                <Card>
                  <CardHeader title="Virtual HMI" subtitle="Gate setpoint 0–100%" icon={<SlidersHorizontal className="h-5 w-5" />} accent="bg-amber-500/10 text-amber-300" />
                  <CardBody className="space-y-4">
                    <div>
                      <div className="flex justify-between text-xs text-slate-400 mb-2">
                        <span>AO.gate_cmd_pct</span>
                        <span className="font-mono text-slate-200">{gate.toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={gate}
                        onChange={(e) => setGate(Number(e.target.value))}
                        className="w-full"
                      />
                    </div>
                    <button
                      onClick={sendSetpoint}
                      disabled={busy}
                      className="w-full rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm font-medium text-amber-200 hover:bg-amber-500/20 disabled:opacity-50"
                    >
                      Apply setpoint to simulator
                    </button>
                    <p className="text-[11px] text-slate-500">
                      Feedback {device.live?.gate_pos_pct != null ? `${fmtNumber(device.live.gate_pos_pct)}%` : '—'} ·
                      command {device.live?.gate_cmd_pct != null ? `${fmtNumber(device.live.gate_cmd_pct)}%` : '—'}
                    </p>
                  </CardBody>
                </Card>
              )}

              <Card>
                <CardHeader title="Fault injection" subtitle="Demo only" />
                <CardBody className="flex flex-wrap gap-2">
                  {FAULTS.filter((f) => device.kind === 'PLC' || f.id !== 'actuator_jam').map((f) => (
                    <button
                      key={f.id}
                      onClick={() => sendFault(f.id)}
                      disabled={busy}
                      className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                    >
                      {f.label}
                    </button>
                  ))}
                </CardBody>
              </Card>
            </div>

            <Card className="lg:col-span-3">
              <CardHeader title="HMI audit" subtitle="Setpoints never write water_observations" />
              <CardBody className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-4 py-2 text-left">When</th>
                      <th className="px-4 py-2 text-left">Action</th>
                      <th className="px-4 py-2 text-left">Tag</th>
                      <th className="px-4 py-2 text-left">Value</th>
                      <th className="px-4 py-2 text-left">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {(device.commands || []).map((c: any) => (
                      <tr key={c.id}>
                        <td className="px-4 py-2 text-slate-400">{fmtDateTime(c.created_at)}</td>
                        <td className="px-4 py-2"><Badge tone="slate">{c.action}</Badge></td>
                        <td className="px-4 py-2 font-mono text-slate-300">{c.tag_name}</td>
                        <td className="px-4 py-2 font-mono">{c.value ?? '—'}</td>
                        <td className="px-4 py-2 text-slate-500">{c.notes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardBody>
            </Card>
          </div>
        )}
      </div>
    </AppShell>
  )
}
