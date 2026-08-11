// packages/dashboard/src/app/system/audit/page.tsx
// AquaVision Audit Log - sample action trail for the command center.
'use client'

import { ScrollText, ShieldCheck, ClipboardList } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fmtDateTime } from '@/lib/format'

const AMBER = 'bg-amber-500/10 text-amber-300'

type AuditEntry = {
  id: number
  timestamp: string
  actor: string
  action: string
  module: string
  detail: string
}

const ACTION_TONE: Record<string, 'emerald' | 'sky' | 'amber' | 'red' | 'violet' | 'slate'> = {
  ACKNOWLEDGE_ALERT: 'sky',
  RESOLVE_ALERT: 'emerald',
  GENERATE_REPORT: 'violet',
  UPDATE_THRESHOLD: 'amber',
  SYSTEM_SETTING: 'slate',
  LOGIN: 'slate',
  LOGOUT: 'slate',
}

const AUDIT_TRAIL: AuditEntry[] = [
  { id: 1, timestamp: '2026-08-06T18:11:09Z', actor: 'admin-1', action: 'UPDATE_THRESHOLD', module: 'aquavision', detail: 'Rainfall anomaly threshold raised 25% → 30%' },
  { id: 2, timestamp: '2026-08-06T17:58:42Z', actor: 'operator-1', action: 'ACKNOWLEDGE_ALERT', module: 'aquavision', detail: 'Alert #25 acknowledged — investigating region 07' },
  { id: 3, timestamp: '2026-08-06T17:12:03Z', actor: 'operator-2', action: 'GENERATE_REPORT', module: 'reports', detail: 'Generated provincial WAI summary for Limpopo Q3' },
  { id: 4, timestamp: '2026-08-06T15:44:51Z', actor: 'system', action: 'SYSTEM_SETTING', module: 'platform', detail: 'Data freshness window changed to 5 minutes' },
  { id: 5, timestamp: '2026-08-06T14:30:27Z', actor: 'operator-1', action: 'RESOLVE_ALERT', module: 'aquavision', detail: 'Alert #19 resolved — rainfall normalized' },
  { id: 6, timestamp: '2026-08-06T11:05:18Z', actor: 'admin-1', action: 'LOGIN', module: 'auth', detail: 'Admin session started from 10.0.0.7' },
  { id: 7, timestamp: '2026-08-05T20:22:36Z', actor: 'operator-3', action: 'ACKNOWLEDGE_ALERT', module: 'aquavision', detail: 'Alert #21 acknowledged — region 03' },
  { id: 8, timestamp: '2026-08-05T17:49:58Z', actor: 'system', action: 'GENERATE_REPORT', module: 'reports', detail: 'Scheduled district report batch completed (9 files)' },
  { id: 9, timestamp: '2026-08-05T16:07:12Z', actor: 'operator-2', action: 'UPDATE_THRESHOLD', module: 'aquavision', detail: 'Severity escalation bound shifted for WAI' },
  { id: 10, timestamp: '2026-08-05T13:31:45Z', actor: 'operator-1', action: 'ACKNOWLEDGE_ALERT', module: 'aquavision', detail: 'Alert #18 acknowledged — monitor ongoing' },
  { id: 11, timestamp: '2026-08-05T09:54:20Z', actor: 'admin-1', action: 'LOGOUT', module: 'auth', detail: 'Session closed normally' },
  { id: 12, timestamp: '2026-08-05T08:12:37Z', actor: 'system', action: 'SYSTEM_SETTING', module: 'platform', detail: 'Ingestion retry policy updated to backoff 30s' },
]

export default function AuditLogPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Audit Log"
          description="Every actor, action, and module change across the command center."
          icon={<ScrollText className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">Sample trail · {AUDIT_TRAIL.length} events</Badge>}
          updatedAt={AUDIT_TRAIL[0].timestamp}
        />

        <Card>
          <CardHeader
            title="Action Trail"
            subtitle="Newest first — this is a representative sample, not live history."
            icon={<ClipboardList className="h-5 w-5" />}
            accent={AMBER}
            action={<Badge tone="slate">{AUDIT_TRAIL.length} entries</Badge>}
          />
          <CardBody className="max-h-[600px] overflow-y-auto p-0">
            <div className="divide-y divide-slate-800/70">
              {AUDIT_TRAIL.map((entry) => (
                <div
                  key={entry.id}
                  className="grid grid-cols-1 gap-2 px-5 py-3 transition-colors hover:bg-slate-800/20 lg:grid-cols-[auto_auto_auto_1fr] lg:items-center lg:gap-6"
                >
                  <span className="w-40 shrink-0 font-mono text-xs text-slate-500">
                    {fmtDateTime(entry.timestamp)}
                  </span>
                  <span className="w-28 shrink-0 truncate font-mono text-xs text-slate-300">
                    {entry.actor}
                  </span>
                  <span className="shrink-0">
                    <Badge tone={ACTION_TONE[entry.action] ?? 'slate'}>{entry.action}</Badge>
                  </span>
                  <span className="min-w-0">
                    <span className="mb-1 inline-block"><Badge tone="slate">{entry.module}</Badge></span>
                    <p className="text-xs text-slate-400">{entry.detail}</p>
                  </span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}