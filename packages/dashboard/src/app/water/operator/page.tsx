// packages/dashboard/src/app/water/operator/page.tsx
// Water Operations Console - the WATER_OPERATOR surface.
// Assigned assets (scoped), live reservoir/flow telemetry, scoped alert queue
// with acknowledge/resolve, and an operational notes logbook per asset.
'use client'

import { useState } from 'react'
import {
  Warehouse,
  Droplets,
  Waves,
  ScrollText,
  Bell,
  CheckCircle2,
  ShieldCheck,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { KpiCard } from '@/components/ui/kpi'
import { SeverityBadge, Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import {
  useWaterAssets,
  useAssetReadings,
  useAssetNotes,
  useAddAssetNote,
  useOperationalAlerts,
  useAckOperationalAlert,
  useResolveOperationalAlert,
} from '@/features/water/hooks'
import { fmtNumber, fmtPct, fmtDateTime, timeAgo } from '@/lib/format'
import { useAuth } from '@/context/AuthContext'
import { PERMISSIONS } from '@/lib/permissions'
import type {
  AssetSummaryVM,
  AssetTelemetryVM,
  OperationalAlert,
} from '@/features/water/types'

const AQUA = 'bg-sky-500/10 text-sky-300'

const ASSET_TYPE_LABEL: Record<string, string> = {
  dam: 'Dam',
  barrage: 'Barrage',
  reservoir: 'Reservoir',
  river: 'River',
  canal: 'Channel',
}

type BadgeTone = 'slate' | 'sky' | 'emerald' | 'amber' | 'violet' | 'red'

function dataTone(status?: string | null): BadgeTone {
  switch (status) {
    case 'Missing':
      return 'red'
    case 'Estimate':
      return 'amber'
    case 'Calibrated':
      return 'sky'
    default:
      return 'emerald'
  }
}

export default function WaterOperatorPage() {
  const { user, hasPermission } = useAuth()
  const assetsQuery = useWaterAssets()
  const alertsQuery = useOperationalAlerts()
  const ack = useAckOperationalAlert()
  const resolve = useResolveOperationalAlert()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [noteText, setNoteText] = useState('')

  const assets = assetsQuery.data ?? []
  const selected = assets.find((a) => a.id === selectedId) ?? assets[0] ?? null
  const activeId = selected?.id ?? null

  const readingsQuery = useAssetReadings(activeId)
  const notesQuery = useAssetNotes(activeId)
  const addNote = useAddAssetNote()

  const alerts = (alertsQuery.data ?? []).filter((a) => a.status !== 'RESOLVED')
  const canOperate = hasPermission(PERMISSIONS.AQUAVISION_ACKNOWLEDGE_ALERT)
  const canNote = hasPermission(PERMISSIONS.AQUAVISION_ADD_NOTE)

  const latest = selected?.latest

  const submitNote = (e: React.FormEvent) => {
    e.preventDefault()
    if (!noteText.trim() || !activeId) return
    addNote.mutate(
      { assetId: activeId, note: noteText.trim() },
      { onSuccess: () => setNoteText('') }
    )
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Operations Console"
          description="Assigned infrastructure, live reservoir flows, scoped alert queue and the operational logbook."
          icon={<Waves className="h-6 w-6" />}
          badge={
            alerts.length ? (
              <Badge tone="amber">
                <Bell className="h-3 w-3" />
                {alerts.filter((a) => a.status === 'NEW').length} new alert(s)
              </Badge>
            ) : (
              <Badge tone="emerald">All clear</Badge>
            )
          }
        />

        {/* KPI strip */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Assigned Assets"
            value={assets.length}
            detail="Water infrastructure in your scope"
            icon={Warehouse}
            accent={AQUA}
          />
          <KpiCard
            label="Open Alerts"
            value={alerts.length}
            detail={`${alerts.filter((a) => a.status === 'NEW').length} New awaiting ack`}
            icon={Bell}
            accent="bg-amber-500/10 text-amber-300"
          />
          <KpiCard
            label="Selected Level"
            value={latest?.reservoirLevelM != null ? `${fmtNumber(latest.reservoirLevelM)} m` : '—'}
            detail={latest?.storagePct != null ? `${fmtPct(latest.storagePct)} storage` : 'Level telemetry'}
            icon={Droplets}
            accent="bg-cyan-500/10 text-cyan-300"
          />
          <KpiCard
            label="Selected Discharge"
            value={latest?.dischargeCumecs != null ? `${fmtNumber(latest.dischargeCumecs)} m³/s` : '—'}
            detail={timeAgo(latest?.recordedAt)}
            icon={Waves}
            accent="bg-violet-500/10 text-violet-300"
          />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Assets + telemetry */}
          <Card className="lg:col-span-2">
            <CardHeader
              title="Assigned Assets"
              subtitle="Reservoir level · storage · inflow · outflow · discharge (m³/s)"
              icon={<Warehouse className="h-5 w-5" />}
              accent={AQUA}
              action={<Badge tone="sky">{assets.length} in scope</Badge>}
            />
            <CardBody className="p-3">
              {assetsQuery.isPending ? (
                <div className="p-6">
                  <Spinner label="Loading assets" />
                </div>
              ) : assets.length === 0 ? (
                <div className="p-6">
                  <EmptyState title="No assets in scope" message="No infrastructure assigned to your region." />
                </div>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {assets.map((asset) => (
                    <AssetCell
                      key={asset.id}
                      asset={asset}
                      active={asset.id === activeId}
                      onAny={() => setSelectedId(asset.id)}
                    />
                  ))}
                </div>
              )}

              {selected && (
                <div className="mt-4">
                  <div className="flex flex-col gap-2 border-t border-slate-800/70 p-3 lg:flex-row">
                    <TelemetryStrip title="Level" value={latest?.reservoirLevelM} unit="m" />
                    <TelemetryStrip title="Storage" value={latest?.storagePct} unit="%" />
                    <TelemetryStrip title="Inflow" value={latest?.inflowCumecs} unit="m³/s" />
                    <TelemetryStrip title="Outflow" value={latest?.outflowCumecs} unit="m³/s" />
                    <TelemetryStrip title="Discharge" value={latest?.dischargeCumecs} unit="m³/s" />
                  </div>
                  <div className="flex items-center justify-between px-3 pb-2">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">
                      Freshness: {timeAgo(latest?.recordedAt)}
                    </p>
                    <Badge tone={dataTone(latest?.dataStatus)}>{latest?.dataStatus ?? 'Actual'}</Badge>
                  </div>
                </div>
              )}

              {!readingsQuery.isPending && readingsQuery.data?.length ? (
                <SeriesSparkline readings={readingsQuery.data} />
              ) : null}
              {readingsQuery.isError ? (
                <p className="px-3 pb-3 text-[11px] text-slate-500">
                  Telemetry history unavailable.
                </p>
              ) : null}
            </CardBody>
          </Card>

          {/* Operational logbook */}
          <Card>
            <CardHeader
              title="Operational Notes"
              subtitle={selected ? `Logbook · ${selected.name}` : 'Select an asset'}
              icon={<ScrollText className="h-5 w-5" />}
              accent="bg-emerald-500/10 text-emerald-300"
            />
            <CardBody>
              {canNote && selected && (
                <form onSubmit={submitNote} className="mb-4 flex gap-2">
                  <input
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    placeholder="Note for this asset…"
                    className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={!noteText.trim() || addNote.isPending}
                    className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
                  >
                    Log
                  </button>
                </form>
              )}
              {!selected ? (
                <EmptyState title="No asset selected" message="Pick an asset to view its logbook." />
              ) : notesQuery.isPending ? (
                <Spinner />
              ) : notesQuery.data?.length ? (
                <div className="space-y-2">
                  {notesQuery.data.slice().reverse().map((n) => (
                    <div key={n.id} className="rounded-lg border border-slate-800/70 bg-slate-950/40 p-3">
                      <p className="text-xs leading-5 text-slate-300">{n.note}</p>
                      <p className="mt-1 text-[10px] text-slate-600">
                        by user #{n.createdByUserId} · {fmtDateTime(n.createdAt)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No notes yet" message="Operators can annotate infrastructure here." />
              )}
            </CardBody>
          </Card>
        </div>

        {/* Scoped alert queue */}
        <Card>
          <CardHeader
            title="Scoped Alert Queue"
            subtitle="Early-warning events in your region; acknowledge once handled."
            icon={<Bell className="h-5 w-5" />}
            accent="bg-amber-500/10 text-amber-300"
            action={
              <div className="flex items-center gap-2">
                {canOperate && (
                  <Badge tone="sky">
                    <ShieldCheck className="h-3 w-3" /> Operate
                  </Badge>
                )}
                <Badge tone="slate">{alerts.length} open</Badge>
              </div>
            }
          />
          <CardBody className="p-0">
            {alertsQuery.isPending ? (
              <div className="p-8">
                <Spinner />
              </div>
            ) : alerts.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No open alerts" message="Your region is nominal." />
              </div>
            ) : (
              <div className="divide-y divide-slate-800/70">
                {alerts.map((a) => (
                  <OperationalAlertRow
                    key={a.id}
                    alert={a}
                    canOperate={canOperate}
                    busy={ack.isPending || resolve.isPending}
                    onAck={() => ack.mutate({ alertId: a.id })}
                    onResolve={() => resolve.mutate({ alertId: a.id })}
                  />
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}

function AssetCell({
  asset,
  active,
  onAny,
}: {
  asset: AssetSummaryVM
  active: boolean
  onAny: () => void
}) {
  const latest = asset.latest
  return (
    <button
      type="button"
      onClick={onAny}
      className={`rounded-xl border p-4 text-left transition-colors ${
        active
          ? 'border-sky-500/50 bg-sky-500/10'
          : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-semibold text-slate-100">{asset.name}</p>
        <Badge tone="slate">{ASSET_TYPE_LABEL[asset.assetType] ?? asset.assetType}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
        <span className="text-slate-500">Level</span>
        <span className="text-right font-medium text-slate-200">
          {latest?.reservoirLevelM != null ? `${fmtNumber(latest.reservoirLevelM)} m` : '—'}
        </span>
        <span className="text-slate-500">Storage</span>
        <span className="text-right font-medium text-slate-200">
          {latest?.storagePct != null ? `${fmtPct(latest.storagePct)}` : '—'}
        </span>
        <span className="text-slate-500">Inflow</span>
        <span className="text-right font-medium text-slate-200">
          {latest?.inflowCumecs != null ? `${fmtNumber(latest.inflowCumecs)} m³/s` : '—'}
        </span>
        <span className="text-slate-500">Discharge</span>
        <span className="text-right font-medium text-slate-200">
          {latest?.dischargeCumecs != null ? `${fmtNumber(latest.dischargeCumecs)} m³/s` : '—'}
        </span>
      </div>
    </button>
  )
}

function TelemetryStrip({
  title,
  value,
  unit,
}: {
  title: string
  value?: number | null
  unit: string
}) {
  return (
    <div className="flex flex-1 items-center justify-between rounded-lg border border-slate-800/70 bg-slate-950/40 px-3 py-2">
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{title}</span>
      <span className="text-sm font-semibold text-slate-100">
        {value != null ? `${fmtNumber(value)} ${unit}` : '—'}
      </span>
    </div>
  )
}

/** Minimal 24-point level sparkline using divs (no chart lib dependency). */
function SeriesSparkline({ readings }: { readings: AssetTelemetryVM[] }) {
  const values = readings
    .filter((r) => r.reservoirLevelM != null)
    .map((r) => r.reservoirLevelM as number)
  if (values.length < 2) return null
  const max = Math.max(...values)
  const min = Math.min(...values)
  const span = max - min || 1
  return (
    <div className="px-3 pb-3">
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
        Reservoir level · last {values.length} readings
      </p>
      <div className="flex h-16 items-end gap-0.5">
        {values.slice(-40).map((v, i) => (
          <div
            key={i}
            className="flex-1 rounded-t bg-sky-500/40"
            style={{ height: `${Math.max(6, ((v - min) / span) * 100)}%` }}
            title={`${fmtNumber(v)} m`}
          />
        ))}
      </div>
    </div>
  )
}

function OperationalAlertRow({
  alert,
  canOperate,
  busy,
  onAck,
  onResolve,
}: {
  alert: OperationalAlert
  canOperate: boolean
  busy: boolean
  onAck: () => void
  onResolve: () => void
}) {
  const statusTone = alert.status === 'NEW' ? 'amber' : alert.status === 'RESOLVED' ? 'emerald' : 'sky'
  return (
    <div className="p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-xs text-slate-500">#{alert.id}</p>
            <SeverityBadge severity={alert.severity} />
            <Badge tone={statusTone}>{alert.status}</Badge>
            {alert.alert_source && <Badge tone="slate">{alert.alert_source}</Badge>}
          </div>
          <h3 className="mt-2 text-base font-semibold text-slate-100">
            {alert.asset_name ? `${alert.asset_name} · ` : ''}{alert.alert_type}
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">{alert.message}</p>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
            {alert.triggered_value != null && <Metric label="Triggered" value={fmtNumber(alert.triggered_value)} />}
            {alert.threshold_value != null && <Metric label="Threshold" value={fmtNumber(alert.threshold_value)} />}
            {alert.reading_level_ft != null && <Metric label="Level" value={`${fmtNumber(alert.reading_level_ft)} ft`} />}
            {alert.reading_inflow_cusecs != null && <Metric label="Inflow" value={`${fmtNumber(alert.reading_inflow_cusecs)} cusecs`} />}
          </div>
          {alert.downstream_population_exposed != null && alert.downstream_population_exposed > 0 && (
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
              <span className="text-amber-400 font-medium">Downstream:</span>
              <Metric label="Pop. exposed" value={`${fmtNumber(alert.downstream_population_exposed)}`} />
              {alert.downstream_bridges_at_risk != null && <Metric label="Bridges" value={`${alert.downstream_bridges_at_risk}`} />}
              {alert.downstream_hospitals_at_risk != null && <Metric label="Hospitals" value={`${alert.downstream_hospitals_at_risk}`} />}
            </div>
          )}
          {alert.flood_severity && (
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
              <span className="text-red-400 font-medium">Flood:</span>
              <Metric label="Severity" value={alert.flood_severity} />
              {alert.flood_probability != null && <Metric label="Probability" value={`${(alert.flood_probability * 100).toFixed(0)}%`} />}
              {alert.flood_recommendation && <span className="text-slate-300">{alert.flood_recommendation}</span>}
            </div>
          )}
        </div>
        {canOperate && (
          <div className="flex shrink-0 flex-col gap-2">
            <button
              type="button"
              onClick={onAck}
              disabled={busy || alert.status !== 'NEW'}
              className="flex items-center justify-center gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs font-medium text-sky-300 transition-colors hover:bg-sky-500/20 disabled:opacity-50"
            >
              <CheckCircle2 className="h-4 w-4" /> Acknowledge
            </button>
            <button
              type="button"
              onClick={onResolve}
              disabled={busy}
              className="flex items-center justify-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
            >
              <CheckCircle2 className="h-4 w-4" /> Resolve
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="text-slate-600">{label}: </span>
      <span className="font-semibold text-slate-200">{value}</span>
    </span>
  )
}