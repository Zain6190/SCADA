// packages/dashboard/src/app/login/page.tsx
'use client'

import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, LogIn, Shield } from 'lucide-react'

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(username, password)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      if (detail === 'account-disabled') {
        router.push('/account-disabled')
      } else if (detail === 'access-pending') {
        router.push('/access-pending')
      } else {
        setError(detail || 'Login failed')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas">
      <div className="pointer-events-none fixed inset-0 " />

      <div className="relative w-full max-w-md px-4">
        <div className="rounded-2xl border border-line bg-surface shadow-card backdrop-blur p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-brand rounded-2xl flex items-center justify-center mx-auto shadow-card">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-semibold text-ink mt-4">Welcome Back</h1>
            <p className="text-ink-subtle text-sm mt-1">Sign in to IBCP-SCADA Operations Console</p>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 rounded-xl border border-crit/25 bg-crit-soft text-sm text-crit">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider text-ink-subtle mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-line-strong bg-surface-alt text-sm text-ink placeholder-ink-subtle focus:border-brand focus:outline-none transition-colors"
                placeholder="Enter your username"
                required
                autoFocus
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider text-ink-subtle mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-line-strong bg-surface-alt text-sm text-ink placeholder-ink-subtle focus:border-brand focus:outline-none transition-colors"
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-subtle hover:text-ink-muted transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-brand text-sm font-semibold text-white shadow-card hover:bg-brand-hover transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          {/* Demo credentials hint */}
          <div className="mt-6 pt-4 border-t border-line">
            <p className="text-[11px] text-ink-subtle text-center">
              Demo: <span className="text-ink-subtle">admin / admin123</span> · <span className="text-ink-subtle">water_ops / water123</span>
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-ink-subtle mt-6">
          IBCP-SCADA · Indus Basin Cyber-Physical System
        </p>
      </div>
    </div>
  )
}
