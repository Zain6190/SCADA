// packages/dashboard/src/context/AuthContext.tsx
'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import axios from 'axios'
import { modulesForUser } from '@/lib/rbac'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

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
      // A disabled/pending session should land on the right status screen.
      const detail = error?.response?.data?.detail
      if (detail === 'account-disabled') router.replace('/account-disabled')
      else if (detail === 'access-pending') router.replace('/access-pending')
    }
  }

  const login = async (username: string, password: string) => {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)

    const response = await axios.post(`${API_URL}/auth/token`, formData)
    const { access_token, user } = response.data

    setToken(access_token)
    setUser(user)
    setUserState(user)

    router.push(homeFor(user))
  }

  const register = async (data: any) => {
    try {
      // Send registration data
      const response = await axios.post(`${API_URL}/auth/register`, data)
      console.log('Registration successful:', response.data)

      // Auto-login after registration
      await login(data.username, data.password)
    } catch (error: any) {
      console.error('Registration error:', error)

      if (error.response) {
        // Server responded with error
        throw new Error(error.response.data.detail || 'Registration failed')
      } else if (error.request) {
        // No response from server
        throw new Error('Cannot connect to server. Make sure backend is running on port 8000')
      } else {
        throw new Error('Registration failed. Please try again.')
      }
    }
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