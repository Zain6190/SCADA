'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip as RTooltip,
  CartesianGrid, ReferenceLine, Legend,
} from 'recharts'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useAssetNotes, useAddAssetNote } from '@/features/water/hooks'
import { fmtNumber, timeAgo } from '@/lib/format'
import type { OperationalAsset, OperationalObservation, OperationalAlert } from '@/features/water/types'

const AQUA = 'bg-sky-500/10 text-sky-300'

function LevelGauge({ level, warning, danger, critical }: { level: number; warning?: number; danger?: number; critical?: number }) {
  const max = critical ? critical * 1.05 : (danger ? danger * 1.1 : (warning ? warning * 1.2 : level * 1.3))
  const pct = Math.min((level / max) * 100, 100)
  let color = 'bg-emerald-500'
  if (critical && level >= critical) color = 'bg-red-500'
  else if (danger && level >= danger) color = 'bg-red-400'
  else if (warning && level >= warning) color = 'bg-amber-500'

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-baseline">
        <span className="text-sm font-medium text-slate-400">Reservoir Level</span>
        <span className="font-mono text-2xl font-bold text-white">{level.toFixed(2)} <span className="text-sm font-normal text-slate-500">ft</span></span>
      </div>
      <div className="relative h-3 rounded-full bg-slate-800 overflow-hidden">
        <div className={`absolute left-0 top-0 h-full ${color} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex gap-4 text-[11px]">
        {warning && <span className="text-amber-400">W: {warning} ft</span>}
        {danger && <span className="text-red-400">D: {danger} ft</span>}
        {critical && <span className="text-red-500">C: {critical} ft</span>}
      </div>
    </div>
  )
}

function TelemetryCard({ label, value, unit, accent }: { label: string; value: number | null; unit: string; accent?: string }) {
  return (
    <Card className="p-4">
      <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`text-xl font-bold font-mono mt-1 ${accent ?? 'text-white'}`}>
        {value != null ? fmtNumber(value) : '\u2014'}
      </p>
      <p className="text-[11px] text-slate-500">{unit}</p>
    </Card>
  )
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-slate-400">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }} className="font-mono">
          {p.name}: {fmtNumber(p.value)}
        </p>
      ))}
    </div>
  )
}

export function AssetDetailClient() {
  const params = useParams()
  const assetId = Number(params.id)

  const [asset, setAsset] = useState<OperationalAsset | null>(null)
  const [observations, setObservations] = useState<OperationalObservation[]>([])
  const [alerts, setAlerts] = useState<OperationalAlert[]>([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [noteText, setNoteText] = useState('')

  const notesQuery = useAssetNotes(assetId)
  const addNote = useAddAssetNote()

  useEffect(() => {
    if (!assetId) return
    setLoading(true)
    Promise.all([
      waterApi.getOperationalAsset(assetId),
      waterApi.getOperationalObservations(assetId, days),
      waterApi.getOperationalAlerts({ asset_id: assetId, limit: 20 }),
    ])
      .then(([a, o, al]) => { setAsset(a); setObservations(o); setAlerts(al) })
      .finally(() => setLoading(false))
  }, [assetId, days])

  const chartData = [...observations].reverse().map((obs) => ({
    date: new Date(obs.observed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    Level: obs.water_level_ft ?? null,
    Inflow: obs.inflow_cusecs ? Math.round(obs.inflow_cusecs) : null,
    Discharge: obs.discharge_cusecs ? Math.round(obs.discharge_cusecs) : null,
  }))

  const activeAlerts = alerts.filter((a) => a.status !== 'RESOLVED')
  const latestFlood = alerts.find((a) => a.flood_severity)

  const submitNote = (e: React.FormEvent) => {
    e.preventDefault()
    if (!noteText.trim()) return
    addNote.mutate(
      { assetId, note: noteText.trim() },
      { onSuccess: () => setNoteText('') }
    )
  }

  if (loading) {
    return (
      <AppShell>
        <div className="flex h-64 items-center justify-center"><Spinner label="Loading asset" /></div>
      </AppShell>
    )
  }

  if (!asset) {
    return (
      <AppShell>
        <EmptyState title="Asset not found" message="The requested asset could not be loaded." />
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title={asset.canonical_name}
          description={`${asset.asset_type.replace('_', ' ')} \u00b7 ${asset.river || '\u2014'} \u00b7 ${asset.province || '\u2014'}`}
          icon={<span className="text-lg">{asset.asset_type === 'dam' ? '\u{1F3D7}' : '\u{26F0}'}</span>}
          badge={
            activeAlerts.length > 0 ? (
              <Badge tone="amber">{activeAlerts.length} active alert(s)</Badge>
            ) : (
              <Badge tone="emerald">Normal</Badge>
            )
          }
          action={
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-500">Updated {timeAgo(asset.last_observed_at)}</span>
              <Link href="/water/command-center" className="text-xs text-sky-400 hover:text-sky-300">Back to Command Center</Link>
            </div>
          }
        />

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <TelemetryCard label="Water Level" value={asset.current_level_ft} unit="ft" accent="text-sky-400" />
          <TelemetryCard label="Inflow" value={asset.current_inflow} unit="cusecs" accent="text-emerald-400" />
          <TelemetryCard label="Outflow" value={asset.current_outflow} unit="cusecs" accent="text-amber-400" />
          <TelemetryCard label="Discharge" value={asset.current_discharge} unit="cusecs" accent="text-violet-400" />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader
              title="Level & Flow History"
              subtitle={`Last ${days} days \u00b7 ${observations.length} observations`}
              icon={<span className="text-lg">{'\u{1F4C8}'}</span>}
              accent={AQUA}
              action={
                <div className="flex gap-1">
                  {[7, 14, 30, 90].map((d) => (
                    <button
                      key={d}
                      onClick={() => setDays(d)}
                      className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors ${
                        days === d
                          ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                          : 'text-slate-500 hover:text-slate-300 border border-transparent'
                      }`}
                    >
                      {d}d
                    </button>
                  ))}
                </div>
              }
            />
            <CardBody className="p-3">
              {chartData.length < 2 ? (
                <div className="flex h-48 items-center justify-center text-sm text-slate-500">Not enough data for chart</div>
              ) : (
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="levelGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="inflowGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#64748b' }} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#64748b' }} />
                      <RTooltip content={<ChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                      {asset.warning_level_ft && (
                        <ReferenceLine yAxisId="left" y={asset.warning_level_ft} stroke="#f59e0b" strokeDasharray="5 5" strokeOpacity={0.5} />
                      )}
                      {asset.critical_level_ft && (
                        <ReferenceLine yAxisId="left" y={asset.critical_level_ft} stroke="#ef4444" strokeDasharray="5 5" strokeOpacity={0.5} />
                      )}
                      <Area yAxisId="left" type="monotone" dataKey="Level" stroke="#38bdf8" strokeWidth={2} fill="url(#levelGrad)" name="Level (ft)" />
                      <Area yAxisId="right" type="monotone" dataKey="Inflow" stroke="#34d399" strokeWidth={1.5} fill="url(#inflowGrad)" name="Inflow (cusecs)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardBody>
          </Card>

          <div className="space-y-6">
            <Card>
              <CardHeader
                title="Level Status"
                icon={<span className="text-lg">{'\u{1F4A1}'}</span>}
                accent={AQUA}
              />
              <CardBody>
                {asset.current_level_ft ? (
                  <LevelGauge
                    level={asset.current_level_ft}
                    warning={asset.warning_level_ft ?? undefined}
                    danger={asset.critical_level_ft ? asset.critical_level_ft - 3 : undefined}
                    critical={asset.critical_level_ft ?? undefined}
                  />
                ) : (
                  <p className="text-sm text-slate-500">No level reading available</p>
                )}
              </CardBody>
            </Card>

            {latestFlood && (
              <Card>
                <CardHeader title="Flood Classification" icon={<span className="text-lg">{'\u{26A0}'}</span>} accent="bg-red-500/10 text-red-300" />
                <CardBody className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">Severity</span>
                    <Badge tone={latestFlood.flood_severity === 'Critical' ? 'red' : 'amber'}>{latestFlood.flood_severity}</Badge>
                  </div>
                  {latestFlood.flood_probability != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-400">Probability</span>
                      <span className="text-sm font-semibold text-white">{(latestFlood.flood_probability * 100).toFixed(0)}%</span>
                    </div>
                  )}
                  {latestFlood.flood_recommendation && (
                    <div>
                      <span className="text-[11px] text-slate-500">Recommendation</span>
                      <p className="text-xs text-slate-300 mt-1">{latestFlood.flood_recommendation}</p>
                    </div>
                  )}
                </CardBody>
              </Card>
            )}

            <Card>
              <CardHeader title="Operational Notes" icon={<span className="text-lg">{'\u{1F4DD}'}</span>} accent="bg-emerald-500/10 text-emerald-300" />
              <CardBody>
                <form onSubmit={submitNote} className="mb-3 flex gap-2">
                  <input
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    placeholder="Add a note..."
                    className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={!noteText.trim() || addNote.isPending}
                    className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    Log
                  </button>
                </form>
                {notesQuery.data?.length ? (
                  <div className="space-y-2 max-h-[200px] overflow-y-auto">
                    {notesQuery.data.slice().reverse().map((n) => (
                      <div key={n.id} className="rounded-lg border border-slate-800/70 bg-slate-950/40 p-2.5">
                        <p className="text-xs text-slate-300">{n.note}</p>
                        <p className="mt-1 text-[10px] text-slate-600">{timeAgo(n.createdAt)}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-600">No notes yet</p>
                )}
              </CardBody>
            </Card>
          </div>
        </div>

        {activeAlerts.length > 0 && (
          <Card>
            <CardHeader
              title="Active Alerts"
              subtitle={`${activeAlerts.length} alert(s) for this asset`}
              icon={<span className="text-lg">{'\u{1F514}'}</span>}
              accent="bg-amber-500/10 text-amber-300"
            />
            <CardBody className="p-0">
              <div className="divide-y divide-slate-800/70">
                {activeAlerts.map((alert) => (
                  <div key={alert.id} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <Badge tone={alert.severity === 'Critical' ? 'red' : alert.severity === 'Danger' ? 'amber' : 'sky'}>{alert.severity}</Badge>
                          <span className="text-sm font-medium text-slate-200">{alert.alert_type.replace(/_/g, ' ')}</span>
                          {alert.alert_source && <Badge tone="slate">{alert.alert_source}</Badge>}
                        </div>
                        <p className="text-xs text-slate-400">{alert.message}</p>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                          {alert.triggered_value != null && <span>Triggered: <span className="text-slate-300 font-mono">{fmtNumber(alert.triggered_value)}</span></span>}
                          {alert.downstream_population_exposed != null && alert.downstream_population_exposed > 0 && (
                            <span className="text-amber-400">Pop. exposed: {fmtNumber(alert.downstream_population_exposed)}</span>
                          )}
                        </div>
                      </div>
                      <span className="text-[11px] text-slate-600 shrink-0">{timeAgo(alert.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader title="Observation History" icon={<span className="text-lg">{'\u{1F4CA}'}</span>} accent={AQUA} />
          <CardBody className="p-0">
            {observations.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500">No observations found</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-4 py-2.5 text-left font-medium">Date</th>
                      <th className="px-4 py-2.5 text-right font-medium">Level (ft)</th>
                      <th className="px-4 py-2.5 text-right font-medium">Inflow</th>
                      <th className="px-4 py-2.5 text-right font-medium">Outflow</th>
                      <th className="px-4 py-2.5 text-right font-medium">Discharge</th>
                      <th className="px-4 py-2.5 text-center font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {observations.map((obs) => (
                      <tr key={obs.id} className="hover:bg-slate-800/20 transition-colors">
                        <td className="px-4 py-2.5 font-medium text-slate-300">{new Date(obs.observed_at).toLocaleDateString()}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-white">{fmtNumber(obs.water_level_ft, 2)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-white">{fmtNumber(obs.inflow_cusecs)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-white">{fmtNumber(obs.outflow_cusecs)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-white">{fmtNumber(obs.discharge_cusecs)}</td>
                        <td className="px-4 py-2.5 text-center">
                          <Badge tone={obs.data_status === 'Actual' ? 'emerald' : 'amber'}>{obs.data_status}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}
