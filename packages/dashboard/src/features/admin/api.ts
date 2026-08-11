// packages/dashboard/src/features/admin/api.ts
// Typed HTTP client for admin user provisioning (/auth/users* endpoints).
import axios from 'axios'
import { API_BASE_URL } from '@/lib/config'

export interface RegionScope {
  access: boolean
  has_scope: boolean
  scope_type: string | null
  region_ids: number[] | null
  restricted: boolean
}

export interface AdminUser {
  id: number
  username: string
  email: string
  full_name: string
  role: string
  roles: string[]
  team: string | null
  is_active: boolean
  access_status: 'ACTIVE' | 'APPROVED' | 'PENDING' | 'REJECTED' | 'SUSPENDED' | 'REVOKED'
  access_requested_at: string | null
  last_login_at: string | null
  permissions: string[]
  region_ids: number[] | null
  region_scope: RegionScope
}

export interface AdminRole {
  name: string
  description: string | null
  permissions: string[]
}

export interface RegionOption {
  id: number
  name: string
  code: string | null
  type: string
  parent_region_id: number | null
}

export interface AssetOption {
  id: number
  name: string
  asset_type: string
  region_id: number | null
}

export interface UserPatch {
  role?: string
  is_active?: boolean
  access_status?: string
  scope?: { scope_type: string; region_id?: number | null; asset_id?: number | null } | null
}

export interface UserCreate {
  full_name: string
  email: string
  password: string
  role: string
  access_status: string
  scope?: { scope_type: string; region_id?: number | null } | null
  asset_ids?: number[]
}

export interface OperatorCreate {
  full_name: string
  email: string
  password: string
  role: string
  access_status: string
  region_id: number
}

export interface OperatorPatch {
  role?: string
  is_active?: boolean
  access_status?: string
}

export const adminClient = axios.create({
  baseURL: `${API_BASE_URL}/auth`,
  headers: { 'Content-Type': 'application/json' },
})

adminClient.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('access_token') : null
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const adminApi = {
  listUsers: async (): Promise<AdminUser[]> => {
    const { data } = await adminClient.get('/users')
    return data
  },
  updateUser: async (userId: number, patch: UserPatch): Promise<AdminUser> => {
    const { data } = await adminClient.patch(`/users/${userId}`, patch)
    return data.user
  },
  createUser: async (payload: UserCreate): Promise<AdminUser> => {
    const { data } = await adminClient.post('/admin/users', payload)
    return data.user
  },
  listRoles: async (): Promise<AdminRole[]> => {
    const { data } = await adminClient.get('/roles')
    return data
  },
  listRegions: async (): Promise<RegionOption[]> => {
    const { data } = await axios.get(`${API_BASE_URL}/water/regions`, {
      headers: { Authorization: `Bearer ${sessionStorage.getItem('access_token')}` },
    })
    return data
  },
  listAssets: async (regionId?: number): Promise<AssetOption[]> => {
    const { data } = await axios.get(`${API_BASE_URL}/water/assets`, {
      headers: { Authorization: `Bearer ${sessionStorage.getItem('access_token')}` },
      params: regionId ? { region_id: regionId } : {},
    })
    return data
  },
  listOperators: async (): Promise<AdminUser[]> => {
    const { data } = await adminClient.get('/operators')
    return data
  },
  createOperator: async (payload: OperatorCreate): Promise<AdminUser> => {
    const { data } = await adminClient.post('/operators', payload)
    return data.user
  },
  updateOperator: async (userId: number, patch: OperatorPatch): Promise<AdminUser> => {
    const { data } = await adminClient.patch(`/operators/${userId}`, patch)
    return data.user
  },
  listOperatorRoles: async (): Promise<AdminRole[]> => {
    const { data } = await adminClient.get('/operator-roles')
    return data
  },
}