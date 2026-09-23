// packages/dashboard/src/app/register/page.tsx
'use client'

import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import Link from 'next/link'
import { UserPlus, Eye, EyeOff, AlertCircle } from 'lucide-react'

export default function RegisterPage() {
  const { register } = useAuth()
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    full_name: '',
    password: '',
    role: 'user',
    team: ''
  })
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    setSuccess(false)

    try {
      await register(formData)
      setSuccess(true)
      // AuthContext will redirect after login
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas py-8">
      <div className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-brand rounded-2xl flex items-center justify-center mx-auto shadow-card">
            <UserPlus className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-ink mt-4">Create Account</h1>
          <p className="text-ink-subtle text-sm">Join IBCP-SCADA platform</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-crit-soft border border-crit/25 rounded-lg flex items-start gap-2">
            <AlertCircle className="w-5 h-5 text-crit flex-shrink-0 mt-0.5" />
            <span className="text-crit text-sm">{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-ok-soft border border-ok/25 rounded-lg">
            <span className="text-ok text-sm">✅ Registration successful! Redirecting...</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-ink-muted mb-1">
              Full Name *
            </label>
            <input
              type="text"
              value={formData.full_name}
              onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
              className="w-full px-4 py-2 border border-line rounded-lg focus:ring-2 focus:ring-brand/25 focus:border-transparent outline-none transition"
              placeholder="Enter your full name"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-muted mb-1">
              Username *
            </label>
            <input
              type="text"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              className="w-full px-4 py-2 border border-line rounded-lg focus:ring-2 focus:ring-brand/25 focus:border-transparent outline-none transition"
              placeholder="Choose a username"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-muted mb-1">
              Email *
            </label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full px-4 py-2 border border-line rounded-lg focus:ring-2 focus:ring-brand/25 focus:border-transparent outline-none transition"
              placeholder="Enter your email"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-muted mb-1">
              Password *
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="w-full px-4 py-2 border border-line rounded-lg focus:ring-2 focus:ring-brand/25 focus:border-transparent outline-none transition"
                placeholder="Create a password (min 6 characters)"
                required
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-subtle"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-muted mb-1">
              Team (Optional)
            </label>
            <select
              value={formData.team}
              onChange={(e) => setFormData({ ...formData, team: e.target.value })}
              className="w-full px-4 py-2 border border-line rounded-lg focus:ring-2 focus:ring-brand/25 focus:border-transparent outline-none transition"
            >
              <option value="">Select your team</option>
              <option value="geovision">🌿 GeoVision AI</option>
              <option value="flood">🌊 Flood SCADA</option>
              <option value="soil">🌾 Soil Monitoring</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-brand text-white font-medium rounded-lg hover:bg-brand-hover transition shadow-card disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating account...' : 'Create Account'}
          </button>
        </form>

        <p className="text-center text-sm text-ink-subtle mt-6">
          Already have an account?{' '}
          <Link href="/login" className="text-brand hover:text-brand font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}