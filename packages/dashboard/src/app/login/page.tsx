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
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top_left,_rgba(56,189,248,0.06),_transparent_45%),radial-gradient(ellipse_at_bottom_right,_rgba(139,92,246,0.05),_transparent_40%)]" />

      <div className="relative w-full max-w-md px-4">
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/50 shadow-xl shadow-black/20 backdrop-blur p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-sky-500 to-cyan-600 rounded-2xl flex items-center justify-center mx-auto shadow-lg shadow-sky-500/20">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-semibold text-slate-100 mt-4">Welcome Back</h1>
            <p className="text-slate-500 text-sm mt-1">Sign in to IBCP-SCADA Operations Console</p>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 rounded-xl border border-red-500/30 bg-red-500/10 text-sm text-red-300">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800/60 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none transition-colors"
                placeholder="Enter your username"
                required
                autoFocus
              />
            </div>

            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800/60 text-sm text-slate-200 placeholder-slate-600 focus:border-sky-500/50 focus:outline-none transition-colors"
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-cyan-600 text-sm font-semibold text-white shadow-lg shadow-sky-500/20 hover:from-sky-400 hover:to-cyan-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          {/* Demo credentials hint */}
          <div className="mt-6 pt-4 border-t border-slate-800/70">
            <p className="text-[11px] text-slate-600 text-center">
              Demo: <span className="text-slate-500">admin / admin123</span> · <span className="text-slate-500">water_ops / water123</span>
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-slate-600 mt-6">
          IBCP-SCADA · Indus Basin Cyber-Physical System
        </p>
      </div>
    </div>
  )
}
