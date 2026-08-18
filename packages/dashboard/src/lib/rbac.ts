// packages/dashboard/src/lib/rbac.ts
// Permission-first portal access. The backend sets the authoritative
// permissions; this module maps a user's permission set to the portal
// modules they can open and the home route they land on after login.
import type { NavSectionId } from '@/lib/navigation'
import { PERMISSIONS } from '@/lib/permissions'

export const ALL_MODULES: NavSectionId[] = ['command', 'aqua', 'crop', 'geo', 'system', 'admin']

// Permissions that unlock each portal module (admin's SYSTEM_ADMIN unlocks all
// unavailable portals so the Command Center can surface them).
export const MODULE_PERMISSIONS: Record<Exclude<NavSectionId, 'command'>, string[]> = {
  aqua: [PERMISSIONS.AQUAVISION_READ],
  crop: [PERMISSIONS.CROP_READ],
  geo: [PERMISSIONS.GEOVISION_READ],
  system: [PERMISSIONS.SYSTEM_ADMIN],
  admin: [PERMISSIONS.SYSTEM_ADMIN],
}

// Maintenance back-compat role map kept for callers that still pass a role.
const ROLE_MODULES: Record<string, NavSectionId[]> = {
  SYSTEM_ADMIN: ALL_MODULES,
  ADMIN: ALL_MODULES,
  WATER_OPS: ['command', 'aqua'],
  IRRIGATION_OPS: ['command', 'aqua'],
  AGRICULTURE: ['command', 'crop'],
  CROP_ANALYST: ['command', 'crop'],
  REMOTE_SENSING: ['command', 'geo'],
  GEOVISION: ['command', 'geo'],
  OPERATOR: ['command', 'aqua'],
  VIEWER: ['command', 'aqua'],
  AQUAVISION_ANALYST: ['command', 'aqua'],
  FIELD_OFFICER: ['command', 'aqua'],
}

const DEFAULT_ROLE = 'VIEWER'
const DEFAULT_MODULES = ROLE_MODULES[DEFAULT_ROLE] ?? ['command', 'aqua']

export function normalizeRole(role?: string | null): string {
  if (!role) return DEFAULT_ROLE
  return role.trim().toUpperCase().replace(/[\s-]+/g, '_')
}

export function allowedModules(role?: string | null): NavSectionId[] {
  return ROLE_MODULES[normalizeRole(role)] ?? DEFAULT_MODULES
}

export interface PortalUserLike {
  permissions?: string[] | null
  roles?: string[] | null
  role?: string | null
}

function permissionSet(user: PortalUserLike): Set<string> {
  return new Set(user.permissions ?? [])
}

/** The portal modules a user may access, derived from their permissions. */
export function modulesForUser(user: PortalUserLike): NavSectionId[] {
  if (!user) return []
  const perms = permissionSet(user)
  const modules: NavSectionId[] = ['command']
  if (perms.has(PERMISSIONS.AQUAVISION_READ)) modules.push('aqua')
  if (perms.has(PERMISSIONS.CROP_READ)) modules.push('crop')
  if (perms.has(PERMISSIONS.GEOVISION_READ)) modules.push('geo')
  if (perms.has(PERMISSIONS.SYSTEM_ADMIN)) {
    modules.push('system')
    modules.push('admin')
    // Admins see every portal in the Command Center even when a specific READ
    // permission is absent for a partner module.
    for (const m of ['aqua', 'crop', 'geo'] as const) {
      if (!modules.includes(m)) modules.push(m)
    }
  }
  // Guard: the role is authoritative when permissions are absent (tokens/roles
  // issued before permissions existed still reach their home portal).
  if (modules.length === 1 && (user.roles ?? []).length) {
    return allowedModules(user.role ?? user.roles?.[0])
  }
  return modules
}

export function canAccess(section: NavSectionId, role?: string | null): boolean {
  if (section === 'command') return true
  return allowedModules(role).includes(section)
}

export function filterSections<T extends { id: NavSectionId }>(items: T[], role?: string | null): T[] {
  return items.filter((item) => canAccess(item.id, role))
}