// packages/dashboard/src/components/ui/timeline.tsx
// Alert audit timeline (events + instruction transitions), append-only source.
'use client'

import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/state'
import { fmtDateTime } from '@/lib/format'
import type { TimelineItem } from '@/features/water/types'

export function TimelinePanel({ loading, items }: { loading: boolean; items: TimelineItem[] }) {
  if (loading) return <div className="border-t border-line p-4"><Spinner label="Loading timeline" /></div>
  if (items.length === 0) return <div className="border-t border-line p-4 text-sm text-ink-subtle">No history yet.</div>
  return (
    <div className="border-t border-line p-4">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">Audit timeline (append-only)</p>
      <ol className="space-y-3">
        {items.map((it, i) => (
          <li key={i} className="flex gap-3">
            <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${it.kind === 'instruction' ? 'bg-brand' : it.action.includes('ESCALAT') ? 'bg-crit' : it.action.includes('RESOLV') ? 'bg-ok' : 'bg-warn'}`} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <strong className="text-ink">{it.action.replace(/_/g, ' ')}</strong>
                <span className="text-ink-muted">{it.actor}</span>
                {it.actor_role && <Badge tone="slate">{it.actor_role}</Badge>}
                {it.old_status && it.new_status && it.old_status !== it.new_status && (
                  <span className="text-ink-subtle">{it.old_status} → {it.new_status}</span>
                )}
                <span className="text-ink-subtle">{fmtDateTime(it.at)}</span>
              </div>
              {it.notes && <p className="mt-0.5 text-xs text-ink-muted">{it.notes}</p>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
