// packages/dashboard/src/lib/severity.ts
// Central severity model shared across AquaVision, Crop, and Geo modules.

export type SeverityLevel =
  | 'Normal'
  | 'Moderate'
  | 'Stressed'
  | 'Warning'
  | 'Severe'
  | 'Critical'

export interface SeverityStyle {
  label: string
  text: string
  bg: string
  border: string
  dot: string
  /** Tailwind ring/glow for map fills */
  fill: string
}

export const SEVERITY_STYLES: Record<SeverityLevel, SeverityStyle> = {
  Normal: {
    label: 'Normal',
    text: 'text-emerald-300',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    dot: 'bg-emerald-400',
    fill: '#34d399',
  },
  Moderate: {
    label: 'Moderate',
    text: 'text-lime-300',
    bg: 'bg-lime-500/10',
    border: 'border-lime-500/30',
    dot: 'bg-lime-400',
    fill: '#a3e635',
  },
  Stressed: {
    label: 'Stressed',
    text: 'text-yellow-300',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    dot: 'bg-yellow-400',
    fill: '#facc15',
  },
  Warning: {
    label: 'Warning',
    text: 'text-amber-300',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    dot: 'bg-amber-400',
    fill: '#f59e0b',
  },
  Severe: {
    label: 'Severe',
    text: 'text-orange-300',
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/30',
    dot: 'bg-orange-400',
    fill: '#f97316',
  },
  Critical: {
    label: 'Critical',
    text: 'text-red-300',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    dot: 'bg-red-400',
    fill: '#ef4444',
  },
}

/** Unordered severity ranking for "worst of" computations. */
export const SEVERITY_RANK: Record<SeverityLevel, number> = {
  Normal: 0,
  Moderate: 1,
  Stressed: 2,
  Warning: 3,
  Severe: 4,
  Critical: 5,
}

export function worstOf(levels: Array<SeverityLevel | null | undefined>): SeverityLevel {
  let worst: SeverityLevel = 'Normal'
  for (const level of levels) {
    if (!level) continue
    if (SEVERITY_RANK[level] > SEVERITY_RANK[worst]) worst = level
  }
  return worst
}

export function isSeverityLevel(value: string | null | undefined): value is SeverityLevel {
  return !!value && value in SEVERITY_STYLES
}

export function normalizeSeverity(value: string | null | undefined): SeverityLevel {
  if (isSeverityLevel(value)) return value
  if (!value) return 'Normal'
  const lower = value.toLowerCase()
  if (lower.includes('crit')) return 'Critical'
  if (lower.includes('sever')) return 'Severe'
  if (lower.includes('warn')) return 'Warning'
  if (lower.includes('stress')) return 'Stressed'
  if (lower.includes('moderate') || lower.includes('mod')) return 'Moderate'
  return 'Normal'
}

export const SEVERITY_ORDER: SeverityLevel[] = [
  'Normal',
  'Moderate',
  'Stressed',
  'Warning',
  'Severe',
  'Critical',
]
