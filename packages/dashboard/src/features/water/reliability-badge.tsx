// packages/dashboard/src/features/water/reliability-badge.tsx
// Per-asset forecast reliability badge — label text always present, tone is
// semantic (neutral/info/ok/warn/crit) so weak models never read as validated.
import { Badge, type BadgeTone } from '@/components/ui/badge'
import type { V2AssetReliability } from '@/features/water/types'

const TONE: Record<string, BadgeTone> = {
  neutral: 'neutral',
  info: 'info',
  ok: 'ok',
  warn: 'warn',
  crit: 'crit',
}

function tooltip(r: V2AssetReliability): string {
  if (r.mape_pct == null) {
    return `${r.n} scored forecast${r.n === 1 ? '' : 's'} — not yet scored against REAL observations`
  }
  const window =
    r.first_scored && r.last_scored
      ? r.first_scored === r.last_scored
        ? r.first_scored
        : `${r.first_scored} → ${r.last_scored}`
      : 'window unknown'
  return `${r.n} scored forecast${r.n === 1 ? '' : 's'} · MAPE ${r.mape_pct}% · ${window} · REAL forecast errors only`
}

export function ReliabilityBadge({ r }: { r?: V2AssetReliability | null }) {
  if (!r) return null
  return (
    <span title={tooltip(r)}>
      <Badge tone={TONE[r.tone] ?? 'neutral'}>{r.label}</Badge>
    </span>
  )
}
