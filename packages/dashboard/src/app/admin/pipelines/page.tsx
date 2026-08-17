// packages/dashboard/src/app/admin/pipelines/page.tsx
// Pipeline Status Viewer - shows IRSA and FFD pipeline health details.
'use client'

import { Server, RefreshCw, Clock, CheckCircle2, AlertTriangle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { usePipelineHealth } from '@/features/water/hooks'
import { timeAgo } from '@/lib/format'

const AMBER = 'bg-amber-500/10 text-amber-300'

function statusTone(status: string | null | undefined): 'emerald' | 'amber' | 'red' | 'slate' {
  switch (status) {
    case 'SUCCESS':
    case 'ready':
    case 'running':
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
    case 'ready': return 'Ready'
    case 'not_ready': return 'Not Ready'
    case 'running': return 'Running'
    case 'delayed': return 'Delayed'
    case 'unhealthy': return 'Unhealthy'
    default: return status ?? 'Unknown'
  }
}

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
              className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 transition disabled:opacity-50"
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
                  <div className={`rounded-xl p-3 ${statusTone(health?.scheduler_status) === 'emerald' ? 'bg-emerald-500/10' : statusTone(health?.scheduler_status) === 'amber' ? 'bg-amber-500/10' : 'bg-red-500/10'}`}>
                    <Server className={`h-6 w-6 ${statusTone(health?.scheduler_status) === 'emerald' ? 'text-emerald-400' : statusTone(health?.scheduler_status) === 'amber' ? 'text-amber-400' : 'text-red-400'}`} />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Scheduler</p>
                    <p className="text-lg font-semibold text-slate-100">{statusLabel(health?.scheduler_status)}</p>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="flex items-center gap-4 p-4">
                  <div className="rounded-xl bg-sky-500/10 p-3">
                    <CheckCircle2 className="h-6 w-6 text-sky-400" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">API Status</p>
                    <p className="text-lg font-semibold text-slate-100">{statusLabel(health?.api_status)}</p>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="flex items-center gap-4 p-4">
                  <div className="rounded-xl bg-violet-500/10 p-3">
                    <Clock className="h-6 w-6 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">IRSA Freshness</p>
                    <p className="text-lg font-semibold text-slate-100">
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
                accent="bg-sky-500/10 text-sky-300"
              />
              <CardBody>
                {health?.last_irsa_run ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                      <div>
                        <p className="text-xs text-slate-500">Status</p>
                        <Badge tone={statusTone(health.last_irsa_run.status)}>
                          {statusLabel(health.last_irsa_run.status)}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Run ID</p>
                        <p className="font-mono text-sm text-slate-300">{health.last_irsa_run.run_id ?? '—'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Last Completed</p>
                        <p className="text-sm text-slate-300">{timeAgo(health.last_irsa_run.completed_at)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Records Stored</p>
                        <p className="text-sm font-semibold text-slate-200">{health.last_irsa_run.records_stored ?? '—'}</p>
                      </div>
                    </div>
                    {health.data_freshness.irsa_hours != null && (
                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="text-slate-500">Freshness</span>
                          <span className="text-slate-400">{health.data_freshness.irsa_hours.toFixed(1)}h since last update</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                          <div
                            className="h-full rounded-full bg-sky-500 transition-all"
                            style={{ width: `${Math.min(100, Math.max(5, 100 - health.data_freshness.irsa_hours * 4))}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center text-sm text-slate-500 py-8">No IRSA pipeline runs recorded yet.</div>
                )}
              </CardBody>
            </Card>

            {/* FFD Pipeline */}
            <Card>
              <CardHeader
                title="FFD Bulletin Pipeline"
                subtitle="Scrapes PMD/FFD flood bulletin, parses status text, stores to database"
                icon={<AlertTriangle className="h-5 w-5" />}
                accent="bg-amber-500/10 text-amber-300"
              />
              <CardBody>
                {health?.last_ffd_run ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                      <div>
                        <p className="text-xs text-slate-500">Status</p>
                        <Badge tone={statusTone(health.last_ffd_run.status)}>
                          {statusLabel(health.last_ffd_run.status)}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Run ID</p>
                        <p className="font-mono text-sm text-slate-300">{health.last_ffd_run.run_id ?? '—'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Last Completed</p>
                        <p className="text-sm text-slate-300">{timeAgo(health.last_ffd_run.completed_at)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Records Stored</p>
                        <p className="text-sm font-semibold text-slate-200">{health.last_ffd_run.records_stored ?? '—'}</p>
                      </div>
                    </div>
                    {health.data_freshness.ffd_hours != null && (
                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="text-slate-500">Freshness</span>
                          <span className="text-slate-400">{health.data_freshness.ffd_hours.toFixed(1)}h since last update</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                          <div
                            className="h-full rounded-full bg-amber-500 transition-all"
                            style={{ width: `${Math.min(100, Math.max(5, 100 - health.data_freshness.ffd_hours * 4))}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center text-sm text-slate-500 py-8">No FFD pipeline runs recorded yet.</div>
                )}
              </CardBody>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  )
}
