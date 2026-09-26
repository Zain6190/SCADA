// packages/dashboard/src/app/admin/pipelines/page.tsx
// Pipeline Status Viewer - shows IRSA and FFD pipeline health details.
'use client'

import type { ReactNode } from 'react'
import { Server, RefreshCw, Clock, CheckCircle2, AlertTriangle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { usePipelineHealth } from '@/features/water/hooks'
import type { PipelineRunSummary } from '@/features/water/types'
import { timeAgo } from '@/lib/format'

const AMBER = 'bg-warn-soft text-warn'

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
    case 'SKIPPED': return 'Skipped'
    case 'ready': return 'Ready'
    case 'not_ready': return 'Not Ready'
    case 'running': return 'Running'
    case 'delayed': return 'Delayed'
    case 'unhealthy': return 'Unhealthy'
    default: return status ?? 'Unknown'
  }
}

function RunCard({
  title,
  subtitle,
  icon,
  accent,
  run,
  empty,
}: {
  title: string
  subtitle: string
  icon: ReactNode
  accent: string
  run: PipelineRunSummary | null | undefined
  empty: string
}) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} icon={icon} accent={accent} />
      <CardBody>
        {run ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-xs text-slate-500">Status</p>
                <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
              </div>
              <div>
                <p className="text-xs text-slate-500">Started</p>
                <p className="text-sm text-slate-300">{timeAgo(run.started_at)}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Completed</p>
                <p className="text-sm text-slate-300">{timeAgo(run.completed_at)}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Records stored</p>
                <p className="text-sm font-semibold text-slate-200">{run.records_stored ?? '—'}</p>
              </div>
            </div>
            {run.error_message ? (
              <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
                {run.error_message}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-slate-500">{empty}</div>
        )}
      </CardBody>
    </Card>
  )
}

export default function PipelinesPage() {
  const healthQuery = usePipelineHealth()
  const health = healthQuery.data

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Pipeline Status"
          description="Latest IRSA, FFD, and weekly water-index pipeline runs, with start time and error text."
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

            <RunCard
              title="IRSA Data Pipeline"
              subtitle="Daily PDF from pakirsa.gov.pk. Canal withdrawals stay on this feed."
              icon={<Server className="h-5 w-5" />}
              accent="bg-sky-500/10 text-sky-300"
              run={health?.last_irsa_run}
              empty="No IRSA pipeline runs recorded yet."
            />
            <RunCard
              title="FFD Bulletin Pipeline"
              subtitle="PMD/FFD flood bulletin stored beside the IRSA day."
              icon={<AlertTriangle className="h-5 w-5" />}
              accent="bg-amber-500/10 text-amber-300"
              run={health?.last_ffd_run}
              empty="No FFD pipeline runs recorded yet."
            />
            <RunCard
              title="Weekly water index"
              subtitle="Earth Engine rainfall, evapotranspiration, surface water, and NDVI."
              icon={<Clock className="h-5 w-5" />}
              accent="bg-violet-500/10 text-violet-300"
              run={health?.last_wai_run}
              empty="No weekly water-index run recorded yet."
            />
          </>
        )}
      </div>
    </AppShell>
  )
}
