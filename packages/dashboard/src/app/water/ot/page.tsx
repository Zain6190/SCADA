'use client'

import { useCallback, useEffect, useState, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Radio, RefreshCw, AlertTriangle, Play } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { KpiCard } from '@/components/ui/kpi'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { fmtNumber } from '@/lib/format'

const AMBER = 'bg-warn-soft text-warn'

// Comfortably longer than the ~14s these endpoints take, so a cycle always
// settles before the next one is scheduled.
const POLL_INTERVAL_MS = 30_000

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

  // These two endpoints take 10-14s against the remote database. setInterval
  // started a new pair before the previous one returned, so requests piled
  // up, drained the connection pool and slowed every other page.
  const load = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([waterApi.getOtStatus(), waterApi.getOtDevices()])
      setStatus(s)
      setDevices(d)
      setError(null)
    } catch (e: any) {
      setError(e?.message || 'Failed to load Soft OT')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let running = false
    let timer: ReturnType<typeof setTimeout>

    // Each cycle waits for the previous load to settle before scheduling the
    // next, so two never overlap however slow the endpoints are.
    //
    // `force` covers the first load and the return from a hidden tab: the
    // page must fetch once even when it starts in the background, otherwise
    // it sits on its loading state until someone focuses it.
    const cycle = async (force = false) => {
      if (cancelled || running) return
      if (force || document.visibilityState === 'visible') {
        running = true
        try {
          await load()
        } finally {
          running = false
        }
      }
      if (!cancelled) timer = setTimeout(() => cycle(), POLL_INTERVAL_MS)
    }

    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return
      clearTimeout(timer)
      cycle(true)
    }

    cycle(true)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [load])

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
            <Button variant="secondary" size="sm" onClick={runTick} loading={ticking}>
              {!ticking && <Play className="h-3.5 w-3.5" />}
              Run tick
            </Button>
          }
        />

        <div className="flex items-start gap-2 rounded-lg border border-warn/25 bg-warn-soft px-4 py-3 text-sm text-warn">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          Track readings are an official replay at priority 4. Scenario readings stay on SOFT_OT. IRSA and FFD rows are never overwritten.
        </div>

        {status?.anchor_banner || status?.anchor?.banner ? (
          <div className="rounded-lg border border-info/25 bg-info-soft px-4 py-3 text-sm text-info">
            {status.anchor_banner || status.anchor?.banner}
            {status?.coverage?.days ? (
              <span className="mt-1 block text-caption text-info/80">
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
              <KpiCard label="Devices" value={status?.devices ?? 0} icon={Radio} accent="bg-brand-soft text-brand" />
              <KpiCard label="Soft RTUs" value={status?.rtu ?? 0} detail="15 min store-and-forward" icon={Radio} accent="bg-ok-soft text-ok" />
              <KpiCard label="Soft PLCs" value={status?.plc ?? 0} detail="scan + gate interlocks" icon={Radio} accent="bg-brand-soft text-brand" />
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
                        <tr className="border-b border-line text-micro uppercase text-ink-subtle">
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
                      <tbody className="divide-y divide-line">
                        {devices.map((d) => (
                          <tr key={d.id} className={`hover:bg-surface-alt ${focusAsset === d.asset_id ? 'bg-brand-soft' : ''}`}>
                            <td className="px-4 py-3">
                              <Link href={`/water/ot/${d.id}`} className="font-mono text-brand hover:underline">
                                {d.device_code}
                              </Link>
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={d.kind === 'PLC' ? 'violet' : 'emerald'}>{d.kind}</Badge>
                            </td>
                            <td className="px-4 py-3 text-ink">{d.asset_name}</td>
                            <td className="px-4 py-3 font-mono tabular-nums text-ink-muted">
                              {d.live?.ai?.level_ft != null ? `${fmtNumber(d.live.ai.level_ft)} ft` : '—'}
                            </td>
                            <td className="px-4 py-3 font-mono tabular-nums text-ink-muted">
                              {d.live?.ai?.discharge_cusecs != null ? fmtNumber(d.live.ai.discharge_cusecs) : '—'}
                            </td>
                            <td className="px-4 py-3 font-mono tabular-nums text-ink-muted">
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
