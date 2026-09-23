// packages/dashboard/src/app/login/page.tsx
'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ArrowRight, Eye, EyeOff, ShieldCheck, Waves } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import styles from './login.module.css'

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
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
        setError(detail || 'We could not sign you in. Check your username and password, then try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.contextPanel} aria-labelledby="context-heading">
        <Link href="/" className={styles.wordmark} aria-label="IBCP-SCADA home">
          <span className={styles.wordmarkMark} aria-hidden="true">Σ</span>
          <span>
            <strong>IBCP-SCADA</strong>
            <small>Indus Basin Operations</small>
          </span>
        </Link>

        <div className={styles.contextCopy}>
          <p className={styles.systemLabel}>
            <Waves aria-hidden="true" />
            Protected operations console
          </p>
          <h2 id="context-heading">One basin. One protected record.</h2>
          <p>
            Enter the same operational picture used to review water conditions,
            forecasts and alerts across the Indus Basin.
          </p>
        </div>

        <BasinTrace />

        <p className={styles.securityNote}>
          <ShieldCheck aria-hidden="true" />
          Session access is role-scoped and recorded.
        </p>
      </section>

      <section className={styles.formPanel} aria-labelledby="login-heading">
        <Link href="/" className={styles.backLink}>
          <ArrowLeft aria-hidden="true" />
          Back to overview
        </Link>

        <div className={styles.formWrap}>
          <div className={styles.formHeading}>
            <p>Authorised access</p>
            <h1 id="login-heading">Sign in to the console</h1>
            <span>Use the username assigned to your operator account.</span>
          </div>

          {error && (
            <div className={styles.error} role="alert">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className={styles.form} aria-busy={loading}>
            <div className={styles.field}>
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="admin"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                autoFocus
              />
            </div>

            <div className={styles.field}>
              <label htmlFor="password">Password</label>
              <div className={styles.passwordField}>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  className={styles.visibilityButton}
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </div>
            </div>

            <button type="submit" className={styles.submitButton} disabled={loading}>
              {loading ? (
                <>
                  <span className={styles.spinner} aria-hidden="true" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight aria-hidden="true" />
                </>
              )}
            </button>
          </form>

          <div className={styles.demoAccess}>
            <span>Local demonstration access</span>
            <code>admin / admin123</code>
          </div>
        </div>

        <p className={styles.formFooter}>IBCP-SCADA · Indus Basin Cyber-Physical System</p>
      </section>
    </main>
  )
}

function BasinTrace() {
  return (
    <svg
      className={styles.basinTrace}
      viewBox="0 0 560 360"
      role="img"
      aria-label="Schematic trace of the Indus river network"
    >
      <g className={styles.traceGrid} aria-hidden="true">
        <path d="M0 90H560M0 180H560M0 270H560" />
        <path d="M112 0V360M224 0V360M336 0V360M448 0V360" />
      </g>
      <g className={styles.traceRivers} aria-hidden="true">
        <path d="M269 8C252 59 283 82 272 128C262 169 298 190 289 229C281 268 310 300 322 353" />
        <path d="M95 61C159 78 207 106 273 144" />
        <path d="M484 73C421 91 367 123 293 166" />
        <path d="M513 145C432 151 372 177 294 211" />
        <path d="M477 235C409 219 357 231 296 249" />
      </g>
      {[58, 128, 212, 275, 326].map((y) => (
        <circle key={y} className={styles.traceStation} cx={y === 58 ? 268 : 270 + y / 6} cy={y} r="5" />
      ))}
    </svg>
  )
}
