// packages/dashboard/src/components/ui/progress.tsx
import { cn } from '@/lib/utils'
import { SEVERITY_STYLES, normalizeSeverity } from '@/lib/severity'

export function ProgressBar({
  value,
  max = 100,
  severity,
  color,
  className,
}: {
  value: number
  max?: number
  severity?: string | null
  color?: string
  className?: string
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const barColor = severity
    ? SEVERITY_STYLES[normalizeSeverity(severity)].dot
    : color || 'bg-sky-400'
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-slate-800', className)}>
      <div className={cn('h-full rounded-full transition-all duration-700', barColor)} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Gauge({
  value,
  max = 100,
  label,
  sublabel,
  severity,
}: {
  value: number
  max?: number
  label?: string
  sublabel?: string
  severity?: string | null
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const color = severity
    ? SEVERITY_STYLES[normalizeSeverity(severity)].dot
    : '#38bdf8'
  const circumference = 2 * Math.PI * 44
  const offset = circumference - (pct / 100) * circumference

  return (
    <div className="flex flex-col items-center">
      <div className="relative h-28 w-28">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle cx="50" cy="50" r="44" fill="none" stroke="rgba(30,41,59,0.8)" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r="44"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-1000"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-semibold text-slate-100">
            {Math.round(pct * 100) / 100}
          </span>
        </div>
      </div>
      {label && <p className="mt-2 text-xs font-medium text-slate-300">{label}</p>}
      {sublabel && <p className="mt-0.5 text-[11px] text-slate-500">{sublabel}</p>}
    </div>
  )
}
