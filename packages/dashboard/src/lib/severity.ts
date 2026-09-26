// packages/dashboard/src/lib/severity.ts
// Central severity model shared across AquaVision, Crop, and Geo modules.
// Classes reference design tokens (see src/app/globals.css) so the ramp stays
// consistent everywhere and can be retuned in one place.

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
  /** Hex for map fills and chart series — same value as the token. */
  fill: string
}

export const SEVERITY_STYLES: Record<SeverityLevel, SeverityStyle> = {
  Normal: {
    label: 'Normal',
    text: 'text-sev-normal',
    bg: 'bg-sev-normal-soft',
    border: 'border-sev-normal/25',
    dot: 'bg-sev-normal',
    fill: '#15693C',
  },
  Moderate: {
    label: 'Moderate',
    text: 'text-sev-moderate',
    bg: 'bg-sev-moderate-soft',
    border: 'border-sev-moderate/25',
    dot: 'bg-sev-moderate',
    fill: '#4D7C0F',
  },
  Stressed: {
    label: 'Stressed',
    text: 'text-sev-stressed',
    bg: 'bg-sev-stressed-soft',
    border: 'border-sev-stressed/25',
    dot: 'bg-sev-stressed',
    fill: '#876500',
  },
  Warning: {
    label: 'Warning',
    text: 'text-sev-warning',
    bg: 'bg-sev-warning-soft',
    border: 'border-sev-warning/25',
    dot: 'bg-sev-warning',
    fill: '#9A5B06',
  },
  Severe: {
    label: 'Severe',
    text: 'text-sev-severe',
    bg: 'bg-sev-severe-soft',
    border: 'border-sev-severe/25',
    dot: 'bg-sev-severe',
    fill: '#A8470E',
  },
  Critical: {
    label: 'Critical',
    text: 'text-sev-critical',
    bg: 'bg-sev-critical-soft',
    border: 'border-sev-critical/25',
    dot: 'bg-sev-critical',
    fill: '#A81E1E',
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
