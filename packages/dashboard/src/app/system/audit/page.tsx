// packages/dashboard/src/app/system/audit/page.tsx
// AquaVision Audit Log - live action trail from system.audit_logs (admin).
'use client'

import { ScrollText, ClipboardList } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useAuditLog } from '@/features/admin/hooks'
import { fmtDateTime } from '@/lib/format'
import type { AuditEntry } from '@/features/admin/api'

const AMBER = 'bg-warn-soft text-warn'

const ACTION_TONE: Record<string, 'emerald' | 'sky' | 'amber' | 'red' | 'violet' | 'slate'> = {
  LOGIN_SUCCESS: 'slate',
  AUTH_FAILED_LOGIN: 'red',
  AUTH_FAILED_ACCOUNT_DISABLED: 'red',
  AUTH_FAILED_ACCESS_PENDING: 'red',
  ACCESS_DENIED: 'red',
  USER_CREATED: 'sky',
  USER_UPDATED: 'amber',
  ALERT_ACKNOWLEDGED: 'sky',
  ALERT_RESOLVED: 'emerald',
  THRESHOLD_UPDATED: 'amber',
}

function entryDetail(entry: AuditEntry): string {
  if (entry.details) {
    const parts = Object.entries(entry.details)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    if (parts.length > 0) return parts.join(' · ')
  }
  if (entry.resource_type) {
    return `${entry.resource_type}${entry.resource_id ? ` #${entry.resource_id}` : ''}`
  }
  if (entry.ip_address) return `from ${entry.ip_address}`
  return entry.result ?? ''
}

export default function AuditLogPage() {
  const auditQuery = useAuditLog()
  const entries = auditQuery.data ?? []

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Audit Log"
          description="Every actor, action, and module change across the command center."
          icon={<ScrollText className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">{entries.length} events</Badge>}
          updatedAt={entries[0]?.timestamp}
        />

        <Card>
          <CardHeader
            title="Action Trail"
            subtitle="Newest first — auth, user administration, thresholds, and alert acknowledgements."
            icon={<ClipboardList className="h-5 w-5" />}
            accent={AMBER}
            action={<Badge tone="slate">{entries.length} entries</Badge>}
          />
          <CardBody className="max-h-[600px] overflow-y-auto p-0">
            {auditQuery.isLoading ? (
              <div className="flex justify-center py-12">
                <Spinner />
              </div>
            ) : auditQuery.isError ? (
              <ErrorState message="Could not load the audit trail." />
            ) : entries.length === 0 ? (
              <EmptyState message="No audit events recorded yet." />
            ) : (
              <div className="divide-y divide-line">
                {entries.map((entry) => (
                  <div
                    key={entry.id}
                    className="grid grid-cols-1 gap-2 px-5 py-3 transition-colors hover:bg-surface-alt lg:grid-cols-[auto_auto_auto_1fr] lg:items-center lg:gap-6"
                  >
                    <span className="w-40 shrink-0 font-mono text-xs text-ink-subtle">
                      {fmtDateTime(entry.timestamp)}
                    </span>
                    <span className="w-40 shrink-0 truncate font-mono text-xs text-ink-muted">
                      {entry.actor ?? `user#${entry.user_id ?? '?'}`}
                    </span>
                    <span className="shrink-0">
                      <Badge tone={ACTION_TONE[entry.action] ?? 'slate'}>{entry.action}</Badge>
                    </span>
                    <span className="min-w-0">
                      <span className="mb-1 inline-block">
                        <Badge tone="slate">{entry.module ?? 'system'}</Badge>
                      </span>
                      <p className="text-xs text-ink-muted">{entryDetail(entry)}</p>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}
