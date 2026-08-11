// packages/dashboard/src/lib/permissions.ts
// Canonical permission identifiers (must match shared.permissions in the DB).
export const PERMISSIONS = {
  AQUAVISION_READ: 'AQUAVISION_READ',
  AQUAVISION_ANALYZE: 'AQUAVISION_ANALYZE',
  AQUAVISION_EXPORT: 'AQUAVISION_EXPORT',
  AQUAVISION_ACKNOWLEDGE_ALERT: 'AQUAVISION_ACKNOWLEDGE_ALERT',
  AQUAVISION_ADD_NOTE: 'AQUAVISION_ADD_NOTE',
  AQUAVISION_APPROVE_REPORT: 'AQUAVISION_APPROVE_REPORT',
  AQUAVISION_MANAGE_DATA: 'AQUAVISION_MANAGE_DATA',
  AQUAVISION_CONFIGURE: 'AQUAVISION_CONFIGURE',
  AQUAVISION_MANAGE_USERS: 'AQUAVISION_MANAGE_USERS',
  CROP_READ: 'CROP_READ',
  CROP_TRAIN_MODEL: 'CROP_TRAIN_MODEL',
  GEOVISION_READ: 'GEOVISION_READ',
  SYSTEM_ADMIN: 'SYSTEM_ADMIN',
} as const

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS]

/**
 * Access level for role-based data visibility. Mirrors the backend's
 * `access_level()` in app/services/water_service.py. Analysis fields
 * (rainfall, anomalies, ET) are only served to ANALYST+.
 */
export type WaterAccessLevel = 'viewer' | 'analyst' | 'operator' | 'manager'

export function waterAccessLevel(permissions?: string[] | null): WaterAccessLevel {
  const perms = new Set(permissions ?? [])
  if (perms.has(PERMISSIONS.AQUAVISION_MANAGE_DATA)) return 'manager'
  if (perms.has(PERMISSIONS.AQUAVISION_ACKNOWLEDGE_ALERT) || perms.has(PERMISSIONS.AQUAVISION_ADD_NOTE))
    return 'operator'
  if (perms.has(PERMISSIONS.AQUAVISION_ANALYZE)) return 'analyst'
  return 'viewer'
}

export function canSeeAnalysis(permissions?: string[] | null): boolean {
  return waterAccessLevel(permissions) !== 'viewer'
}
