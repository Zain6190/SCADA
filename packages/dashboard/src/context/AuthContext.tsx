// packages/dashboard/src/context/AuthContext.tsx
'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import axios from 'axios'
import { modulesForUser } from '@/lib/rbac'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8100'

// Demo users for local testing (no real auth backend yet)
const DEMO_USERS = {
  'admin': { username: 'admin', password: 'admin123', id: '1', email: 'admin@ibcp.gov.pk', full_name: 'System Admin', role: 'SYSTEM_ADMIN', roles: ['SYSTEM_ADMIN'], team: 'IT', is_active: true, access_status: 'ACTIVE', permissions: ['*'], region_ids: [], region_scope: { access: true, has_scope: false, scope_type: null, region_ids: null, restricted: false } },
  'water_ops': { username: 'water_ops', password: 'water123', id: '2', email: 'water.ops@ibcp.gov.pk', full_name: 'Water Operations', role: 'WATER_OPS', roles: ['WATER_OPS'], team: 'Water', is_active: true, access_status: 'ACTIVE', permissions: ['water:*'], region_ids: [1,2,3], region_scope: { access: true, has_scope: true, scope_type: 'region', region_ids: [1,2,3], restricted: true } },
  'crop_analyst': { username: 'crop_analyst', password: 'crop123', id: '3', email: 'crop@ibcp.gov.pk', full_name: 'Crop Analyst', role: 'CROP_ANALYST', roles: ['CROP_ANALYST'], team: 'Agriculture', is_active: true, access_status: 'ACTIVE', permissions: ['crop:*'], region_ids: [1,2], region_scope: { access: true, has_scope: true, scope_type: 'region', region_ids: [1,2], restricted: true } },
  'geo_analyst': { username: 'geo_analyst', password: 'geo123', id: '4', email: 'geo@ibcp.gov.pk', full_name: 'Geo Analyst', role: 'REMOTE_SENSING', roles: ['REMOTE_SENSING'], team: 'Remote Sensing', is_active: true, access_status: 'ACTIVE', permissions: ['geo:*'], region_ids: [1], region_scope: { access: true, has_scope: true, scope_type: 'region', region_ids: [1], restricted: true } },
  'viewer': { username: 'viewer', password: 'viewer123', id: '5', email: 'viewer@ibcp.gov.pk', full_name: 'Read-only Viewer', role: 'VIEWER', roles: ['VIEWER'], team: 'General', is_active: true, access_status: 'ACTIVE', permissions: [], region_ids: [], region_scope: { access: true, has_scope: false, scope_type: null, region_ids: null, restricted: false } }
}

// Helper functions for sessionStorage
const TOKEN_KEY = 'access_token'
const USER_KEY = 'user'

const getToken = () => sessionStorage.getItem(TOKEN_KEY)
const setToken = (token: string) => sessionStorage.setItem(TOKEN_KEY, token)
const removeToken = () => sessionStorage.removeItem(TOKEN_KEY)

const getUser = () => {
  const user = sessionStorage.getItem(USER_KEY)
  return user ? JSON.parse(user) : null
}
const setUser = (user: any) => sessionStorage.setItem(USER_KEY, JSON.stringify(user))
const removeUser = () => sessionStorage.removeItem(USER_KEY)

/** Home route for a signed-in user, based on their access status + portals. */
export function homeFor(user: User | null): string {
  if (!user) return '/login'
  if (user.access_status === 'SUSPENDED' || user.access_status === 'REVOKED' || user.is_active === false)
    return '/account-disabled'
  const portals = modulesForUser(user).filter((m) => m !== 'command')
  // Multi-portal users (e.g. admins) land on the Command Center.
  if (portals.length > 1) return '/'
  const only = portals[0]
  if (only === 'aqua') {
    const roles = user.roles ?? []
    if (roles.includes('field_officer') || user.role === 'field_officer') return '/water/operator'
    if (roles.includes('aquavision_analyst') || user.role === 'aquavision_analyst') return '/water/analyst'
    return '/water'
  }
  if (only === 'crop') return '/crop'
  if (only === 'geo') return '/geo'
  if (only === 'system') return '/system'
  return '/'
}

interface User {
  id: string
  username: string
  email: string
  full_name: string
  role: string
  roles: string[]
  team: string | null
  is_active?: boolean
  access_status?: string
  access_requested_at?: string | null
  permissions?: string[]
  region_ids?: number[]
  region_scope?: {
    access: boolean
    has_scope: boolean
    scope_type: string | null
    region_ids: number[] | null
    restricted: boolean
  }
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (data: any) => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
  hasPermission: (perm: string) => boolean
  isViewer: () => boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    const token = getToken()
    const userData = getUser()

    if (token && userData) {
      setUserState(userData)
      verifyToken(token)
    }
    setLoading(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const verifyToken = async (token: string) => {
    // Demo mode: token starts with "demo-token-"
    if (token.startsWith('demo-token-')) {
      // For demo, just keep the user from sessionStorage
      const userData = getUser()
      if (userData) setUserState(userData)
      return
    }
    try {
      const response = await axios.get(`${API_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      const me = response.data
      setUserState(me)
      setUser(me)
    } catch (error: any) {
      sessionStorage.clear()
      setUserState(null)
      const detail = error?.response?.data?.detail
      if (detail === 'account-disabled') router.replace('/account-disabled')
      else if (detail === 'access-pending') router.replace('/access-pending')
    }
  }

  const login = async (username: string, password: string) => {
    const demoUser = DEMO_USERS[username as keyof typeof DEMO_USERS]
    if (!demoUser || demoUser.password !== password) {
      throw new Error('Invalid username or password')
    }

    const mockToken = `demo-token-${Date.now()}`
    setToken(mockToken)
    setUser(demoUser)
    setUserState(demoUser)

    router.push(homeFor(demoUser))
  }

  const register = async (data: any) => {
    // Demo mode: no backend registration
    throw new Error('Registration not available in demo mode. Use demo credentials.')
  }

  const logout = async () => {
    sessionStorage.clear()
    setUserState(null)
    router.push('/login')
  }

  const hasPermission = (perm: string) => {
    if (!user) return false
    if (user.permissions?.includes(perm)) return true
    return user.role === 'admin' || user.roles?.includes('admin')
  }

  const isViewer = () => {
    if (!user) return true
    return user.role === 'viewer' || user.roles?.includes('viewer')
  }

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      login,
      register,
      logout,
      isAuthenticated: !!user,
      hasPermission,
      isViewer,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}