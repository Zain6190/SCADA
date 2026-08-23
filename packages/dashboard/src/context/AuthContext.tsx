// packages/dashboard/src/context/AuthContext.tsx
'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import axios from 'axios'
import { modulesForUser } from '@/lib/rbac'

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8100'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'user'

const getToken = () => sessionStorage.getItem(TOKEN_KEY)
const setToken = (token: string) => sessionStorage.setItem(TOKEN_KEY, token)
const removeToken = () => sessionStorage.removeItem(TOKEN_KEY)

const getStoredUser = () => {
  const raw = sessionStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}
const storeUser = (user: any) => sessionStorage.setItem(USER_KEY, JSON.stringify(user))
const removeStoredUser = () => sessionStorage.removeItem(USER_KEY)

/** Home route for a signed-in user, based on their portals + roles. */
export function homeFor(user: User | null): string {
  if (!user) return '/login'
  if (user.is_active === false) return '/account-disabled'
  const portals = modulesForUser(user).filter((m) => m !== 'command')
  if (portals.length > 1) return '/'
  const only = portals[0]
  if (only === 'aqua') {
    const roles = user.roles ?? []
    if (roles.includes('WATER_OPS') || user.role === 'WATER_OPS') return '/water/operator'
    if (roles.includes('CROP_ANALYST') || user.role === 'CROP_ANALYST') return '/water/analyst'
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
  is_active?: boolean
  access_status?: string
  permissions?: string[]
  region_ids?: number[]
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
    const userData = getStoredUser()

    if (token && userData) {
      setUserState(userData)
      verifyToken(token)
    }
    setLoading(false)
  }, [])

  const verifyToken = async (token: string) => {
    try {
      const response = await axios.get(`${API_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const me = response.data
      setUserState(me)
      storeUser(me)
    } catch (error: any) {
      sessionStorage.clear()
      removeToken()
      removeStoredUser()
      setUserState(null)
    }
  }

  const login = async (username: string, password: string) => {
    const response = await axios.post(`${API_URL}/auth/login`, { username, password })
    const { access_token, user: userData } = response.data

    setToken(access_token)
    storeUser(userData)
    setUserState(userData)

    router.push(homeFor(userData))
  }

  const register = async (data: any) => {
    throw new Error('Registration not available. Contact your administrator.')
  }

  const logout = async () => {
    sessionStorage.clear()
    removeToken()
    removeStoredUser()
    setUserState(null)
    router.push('/login')
  }

  const hasPermission = (perm: string) => {
    if (!user) return false
    const perms = user.permissions ?? []
    if (perms.includes('*')) return true
    if (perms.includes(perm)) return true
    // Wildcard match: 'water:*' matches 'water:ack'
    const parts = perm.split(':')
    if (parts.length === 2 && perms.includes(`${parts[0]}:*`)) return true
    return false
  }

  const isViewer = () => {
    if (!user) return true
    return user.role === 'VIEWER' || user.roles?.includes('VIEWER')
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
