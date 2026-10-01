// packages/dashboard/src/app/admin/pipelines/page.tsx
// Pipeline Status Viewer - shows IRSA and FFD pipeline health details.
'use client'

import { Server, RefreshCw, Clock, CheckCircle2, AlertTriangle, History } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { usePipelineHealth } from '@/features/water/hooks'
import { timeAgo } from '@/lib/format'

const AMBER = 'bg-warn-soft text-warn'

function statusTone(status: string | null | undefined): 'emerald' | 'amber' | 'red' | 'slate' {
  switch (status) {
    case 'SUCCESS':
    case 'ready':
    case 'running':
    case 'RUNNING':
      return 'emerald'
    case 'PARTIAL_SUCCESS':
    case 'delayed':
      return 'amber'
    case 'FAILED':
    case 'not_ready':
    case 'unhealthy':
      return 'red'
    default:
      return 'slate'
  }
}

function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'SUCCESS': return 'Success'
    case 'PARTIAL_SUCCESS': return 'Partial'
    case 'FAILED': return 'Failed'
    case 'RUNNING': return 'Running'
    case 'QUEUED': return 'Queued'
    case 'SKIPPED': return 'Skipped'
    case 'CANCELLED': return 'Cancelled'
    case 'ready': return 'Ready'
    case 'not_ready': return 'Not Ready'
    case 'running': return 'Running'
    case 'delayed': return 'Delayed'
    case 'unhealthy': return 'Unhealthy'
    default: return status ?? 'Unknown'
  }
}

function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`
}

const SUMMARY_ORDER = ['SUCCESS', 'PARTIAL_SUCCESS', 'FAILED', 'RUNNING', 'SKIPPED', 'CANCELLED']

export default function PipelinesPage() {
  const healthQuery = usePipelineHealth()
  const health = healthQuery.data

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Pipeline Status"
          description="Monitor IRSA and FFD data ingestion pipelines, scheduler health, and data freshness."
          icon={<Server className="h-6 w-6" />}
          accent={AMBER}
          action={
            <button
              onClick={() => healthQuery.refetch()}
              disabled={healthQuery.isPending}
              className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-xs font-medium text-ink-muted hover:bg-surface-alt transition disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${healthQuery.isPending ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          }
        />

        {healthQuery.isPending ? (
          <div className="flex items-center justify-center p-12">
            <Spinner label="Loading pipeline status..." />
          </div>
        ) : healthQuery.isError ? (
          <ErrorState title="Pipeline status unavailable" onRetry={() => healthQuery.refetch()} />
        ) : (
          <>
            {/* Scheduler Status */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Card>
                <CardBody className="flex items-center gap-4 p-4">
                  <div className={`rounded-xl p-3 ${statusTone(health?.scheduler_status) === 'emerald' ? 'bg-ok-soft' : statusTone(health?.scheduler_status) === 'amber' ? 'bg-warn-soft' : 'bg-crit-soft'}`}>
                    <Server className={`h-6 w-6 ${statusTone(health?.scheduler_status) === 'emerald' ? 'text-ok' : statusTone(health?.scheduler_status) === 'amber' ? 'text-warn' : 'text-crit'}`} />
                  </div>
                  <div>
                    <p className="text-xs text-ink-subtle">Scheduler</p>
                    <p className="text-lg font-semibold text-ink">{statusLabel(health?.scheduler_status)}</p>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="flex items-center gap-4 p-4">
                  <div className="rounded-xl bg-brand-soft p-3">
                    <CheckCircle2 className="h-6 w-6 text-brand" />
                  </div>
                  <div>
                    <p className="text-xs text-ink-subtle">API Status</p>
                    <p className="text-lg font-semibold text-ink">{statusLabel(health?.api_status)}</p>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="flex items-center gap-4 p-4">
                  <div className="rounded-xl bg-brand-soft p-3">
                    <Clock className="h-6 w-6 text-brand" />
                  </div>
                  <div>
                    <p className="text-xs text-ink-subtle">IRSA Freshness</p>
                    <p className="text-lg font-semibold text-ink">
                      {health?.data_freshness?.irsa_hours != null
                        ? `${health.data_freshness.irsa_hours.toFixed(1)}h ago`
                        : 'No data'}
                    </p>
                  </div>
                </CardBody>
              </Card>
            </div>

            {/* IRSA Pipeline */}
            <Card>
              <CardHeader
                title="IRSA Data Pipeline"
                subtitle="Ingests daily PDF from pakirsa.gov.pk, parses observations, stores to database"
                icon={<Server className="h-5 w-5" />}
                accent="bg-brand-soft text-brand"
              />
              <CardBody>
                {health?.last_irsa_run ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                      <div>
                        <p className="text-xs text-ink-subtle">Status</p>
                        <Badge tone={statusTone(health.last_irsa_run.status)}>
                          {statusLabel(health.last_irsa_run.status)}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-xs text-ink-subtle">Run ID</p>
                        <p className="font-mono text-sm text-ink-muted">{health.last_irsa_run.run_id ?? '—'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-ink-subtle">Last Completed</p>
                        <p className="text-sm text-ink-muted">{timeAgo(health.last_irsa_run.completed_at)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-ink-subtle">Records Stored</p>
                        <p className="text-sm font-semibold text-ink">{health.last_irsa_run.records_stored ?? '—'}</p>
                      </div>
                    </div>
                    {health.data_freshness.irsa_hours != null && (
                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="text-ink-subtle">Freshness</span>
                          <span className="text-ink-muted">{health.data_freshness.irsa_hours.toFixed(1)}h since last update</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-surface-alt">
                          <div
                            className="h-full rounded-full bg-brand transition-all"
                            style={{ width: `${Math.min(100, Math.max(5, 100 - health.data_freshness.irsa_hours * 4))}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center text-sm text-ink-subtle py-8">No IRSA pipeline runs recorded yet.</div>
                )}
              </CardBody>
            </Card>

            {/* FFD Pipeline */}
            <Card>
              <CardHeader
                title="FFD Bulletin Pipeline"
                subtitle="Scrapes PMD/FFD flood bulletin, parses status text, stores to database"
                icon={<AlertTriangle className="h-5 w-5" />}
                accent="bg-warn-soft text-warn"
              />
              <CardBody>
                {health?.last_ffd_run ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                      <div>
                        <p className="text-xs text-ink-subtle">Status</p>
                        <Badge tone={statusTone(health.last_ffd_run.status)}>
                          {statusLabel(health.last_ffd_run.status)}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-xs text-ink-subtle">Run ID</p>
                        <p className="font-mono text-sm text-ink-muted">{health.last_ffd_run.run_id ?? '—'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-ink-subtle">Last Completed</p>
                        <p className="text-sm text-ink-muted">{timeAgo(health.last_ffd_run.completed_at)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-ink-subtle">Records Stored</p>
                        <p className="text-sm font-semibold text-ink">{health.last_ffd_run.records_stored ?? '—'}</p>
                      </div>
                    </div>
                    {health.data_freshness.ffd_hours != null && (
                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="text-ink-subtle">Freshness</span>
                          <span className="text-ink-muted">{health.data_freshness.ffd_hours.toFixed(1)}h since last update</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-surface-alt">
                          <div
                            className="h-full rounded-full bg-warn transition-all"
                            style={{ width: `${Math.min(100, Math.max(5, 100 - health.data_freshness.ffd_hours * 4))}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center text-sm text-ink-subtle py-8">No FFD pipeline runs recorded yet.</div>
                )}
              </CardBody>
            </Card>

            {/* Run History */}
            <Card>
              <CardHeader
                title="Recent Pipeline Runs"
                subtitle="Last 20 scheduler runs across all pipelines, with status, duration and errors"
                icon={<History className="h-5 w-5" />}
                accent="bg-brand-soft text-brand"
                action={
                  <div className="flex flex-wrap items-center gap-2">
                    {SUMMARY_ORDER.filter((s) => (health?.summary?.[s] ?? 0) > 0).map((s) => (
                      <Badge key={s} tone={statusTone(s)}>
                        {statusLabel(s)} · {health?.summary?.[s]}
                      </Badge>
                    ))}
                    {health?.summary?.window_days != null && (
                      <span className="text-xs text-ink-subtle">
                        last {health.summary.window_days}d
                      </span>
                    )}
                  </div>
                }
              />
              <CardBody>
                {(health?.recent_runs?.length ?? 0) === 0 ? (
                  <div className="text-center text-sm text-ink-subtle py-8">No pipeline runs recorded yet.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-line text-left text-xs text-ink-subtle">
                          <th className="py-2 pr-4 font-medium">Started</th>
                          <th className="py-2 pr-4 font-medium">Pipeline</th>
                          <th className="py-2 pr-4 font-medium">Status</th>
                          <th className="py-2 pr-4 font-medium">Trigger</th>
                          <th className="py-2 pr-4 font-medium">Duration</th>
                          <th className="py-2 pr-4 font-medium">Run ID</th>
                          <th className="py-2 font-medium">Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {health?.recent_runs?.map((run) => (
                          <tr key={run.id} className="border-b border-line/60 last:border-0 hover:bg-surface-alt">
                            <td className="py-2.5 pr-4 whitespace-nowrap text-ink-muted" title={run.started_at ?? ''}>
                              {timeAgo(run.started_at)}
                            </td>
                            <td className="py-2.5 pr-4 font-medium text-ink">{run.pipeline_type}</td>
                            <td className="py-2.5 pr-4">
                              <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
                            </td>
                            <td className="py-2.5 pr-4 text-ink-muted">{run.trigger_type}</td>
                            <td className="py-2.5 pr-4 text-ink-muted">{fmtDuration(run.duration_seconds)}</td>
                            <td className="py-2.5 pr-4 font-mono text-xs text-ink-subtle">{run.run_id}</td>
                            <td className="max-w-[24ch] truncate py-2.5 text-ink-muted" title={run.error_message ?? ''}>
                              {run.error_message ?? '—'}
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
