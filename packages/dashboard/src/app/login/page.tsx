'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ArrowRight, Eye, EyeOff, ShieldCheck, Pause, Play, Radio, Waves, Sprout, Map, Activity, FileCheck } from 'lucide-react'
import { BrandMark } from '@/components/shared/brand-mark'
import { useAuth } from '@/context/AuthContext'
import styles from './login.module.css'

const MODULES = [
  { name: 'AquaVision', detail: 'Water operations', icon: Waves, x: 190, y: 132, path: 'M190 132C190 238 360 198 360 290', activity: 'River observations entering the operational picture.', readiness: 'Ready for review', source: 'IRSA · reservoirs · barrages' },
  { name: 'Crop Yield', detail: 'Agricultural intelligence', icon: Sprout, x: 493, y: 112, path: 'M493 112C493 210 360 198 360 290', activity: 'Seasonal indicators connected to regional crop analysis.', readiness: 'Analysis workspace', source: 'Crop indicators · regional history' },
  { name: 'GeoVision', detail: 'Geospatial analysis', icon: Map, x: 596, y: 289, path: 'M596 289C520 289 440 290 360 290', activity: 'Regional layers bringing geography into the same view.', readiness: 'Layers for exploration', source: 'GIS · regions · satellite indices' },
  { name: 'Flood Forecasts', detail: 'Prediction & impact', icon: Activity, x: 503, y: 457, path: 'M503 457C503 357 360 382 360 290', activity: 'Forecasts linked to downstream impact and operator review.', readiness: 'Advisory workflow', source: 'FFD bulletins · model predictions' },
  { name: 'Field Telemetry', detail: 'Simulated PLC / RTU', icon: Radio, x: 191, y: 462, path: 'M191 462C191 352 360 382 360 290', activity: 'Simulated field signals flowing into water operations.', readiness: 'Simulation workspace', source: 'Soft OT · sensors · gate positions' },
  { name: 'Audit Record', detail: 'Traceable decisions', icon: FileCheck, x: 123, y: 289, path: 'M123 289C210 289 280 290 360 290', activity: 'Operator decisions connected to a traceable audit record.', readiness: 'Review & traceability', source: 'Roles · alert actions · audit trail' },
]

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
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark} aria-label="IBCP-SCADA home">
          <span className={styles.wordmarkMark}><BrandMark width={36} height={36} /></span>
          <span><strong>IBCP-SCADA</strong><small>Indus Basin Operations</small></span>
        </Link>
        <Link href="/" className={styles.overviewLink}><ArrowLeft size={14} aria-hidden="true" /> Basin overview</Link>
      </header>
      <div className={styles.content}>
        <ModuleNetwork />
        <section className={styles.formPanel} aria-labelledby="login-heading">
          <div className={styles.formWrap}>
            <span className={styles.formLogo}><BrandMark width={38} height={38} /></span>
            <div className={styles.formHeading}>
              <p>THE INDUS BASIN PLATFORM</p>
              <h1 id="login-heading">Welcome to the console.</h1>
              <span>One connected view. Sign in to your workspace.</span>
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


            <p className={styles.accessNote}>Need access? <span>Contact your system administrator.</span></p>
            <div className={styles.securityNote}><ShieldCheck size={16} aria-hidden="true" /><span>Role-scoped access. Every decision has a record.</span></div>
            <details className={styles.demoAccess}>
              <summary>Local demonstration access</summary>
              <code>admin / admin123</code>
            </details>
            <p className={styles.formFooter}>Indus Basin Cyber-Physical System</p>
          </div>
        </section>
      </div>
      <footer className={styles.pageFooter}><span>WATER · LAND · INTELLIGENCE</span><span>IBCP-SCADA / Pakistan</span></footer>
    </main>
  )
}

function ModuleNetwork() {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReducedMotion(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])
  useEffect(() => {
    if (paused || reducedMotion) return
    const timer = window.setInterval(() => {
      if (!document.hidden) setActive((index) => (index + 1) % MODULES.length)
    }, 4200)
    return () => window.clearInterval(timer)
  }, [paused, reducedMotion])
  const current = MODULES[active]
  const stopped = paused || reducedMotion
  return (
    <section className={styles.contextPanel} aria-labelledby="context-heading" data-paused={stopped}>
      <div className={styles.networkTopline}>
        <span><i /> CONNECTED BASIN INTELLIGENCE</span>
        <button type="button" className={styles.motionButton} onClick={() => setPaused((value) => !value)} aria-label={paused ? 'Resume animation' : 'Pause animation'} aria-pressed={paused} disabled={reducedMotion}>
          {stopped ? <Play size={13} aria-hidden="true" /> : <Pause size={13} aria-hidden="true" />}
          {reducedMotion ? 'Motion reduced' : paused ? 'Paused' : 'Pause'}
        </button>
      </div>
      <div className={styles.network}>
        <svg className={styles.networkSvg} viewBox="0 0 720 570" role="img" aria-labelledby="module-network-title module-network-desc">
          <title id="module-network-title">Connected IBCP-SCADA modules</title>
          <desc id="module-network-desc">AquaVision, Crop Yield, GeoVision, Flood Forecasts, Field Telemetry and Audit Record connect to a shared operations console. Animated signals illustrate workflows and do not indicate live service health.</desc>
          <defs><radialGradient id="basin-halo"><stop offset="0%" stopColor="#77CCB0" stopOpacity=".14" /><stop offset="100%" stopColor="#77CCB0" stopOpacity="0" /></radialGradient></defs>
          <circle cx="360" cy="290" r="250" fill="url(#basin-halo)" />
          <g className={styles.orbits} fill="none"><circle cx="360" cy="290" r="225" /><circle cx="360" cy="290" r="169" /><circle cx="360" cy="290" r="104" /></g>
          <circle className={styles.orbitAccent} cx="360" cy="290" r="169" fill="none" />
          <g className={styles.compassLabels}><text x="360" y="102" textAnchor="middle">OBSERVE</text><text x="548" y="294">ANALYSE</text><text x="360" y="487" textAnchor="middle">DECIDE</text><text x="129" y="294">RECORD</text></g>
          {MODULES.map((module, index) => (
            <g key={module.name} data-active={index === active} className={styles.connection}>
              <path d={module.path} className={styles.connectionLine} fill="none" />
              <path d={module.path} pathLength="200" className={styles.signal} fill="none" style={{ animationDelay: '-' + index * .7 + 's' }} />
            </g>
          ))}
          <g transform="translate(305 235)" className={styles.hub}>
            <rect width="110" height="110" rx="27" />
            <BrandMark x={19} y={15} width={72} height={72} />
            <text x="55" y="95" textAnchor="middle">IBCP-SCADA</text>
          </g>
          {MODULES.map((module, index) => {
            const Icon = module.icon
            return (
              <g key={module.name} className={styles.moduleNode} data-active={index === active} transform={'translate(' + (module.x - 83) + ' ' + (module.y - 27) + ')'}>
                <rect width="166" height="54" rx="10" />
                <Icon x={13} y={12} width={17} height={17} />
                <text x="39" y="24" className={styles.moduleName}>{module.name}</text>
                <text x="39" y="41" className={styles.moduleDetail}>{module.detail}</text>
                <circle className={styles.nodeLight} cx="150" cy="15" r="3" />
              </g>
            )
          })}
          <g className={styles.networkCoordinates}><text x="30" y="548">INDUS BASIN / CONNECTED VIEW</text><text x="690" y="548" textAnchor="end">06 MODULES</text></g>
        </svg>
      </div>
      <div className={styles.telemetry}>
        <div className={styles.readiness}>
          <span className={styles.telemetryLabel}>MODULE READINESS</span>
          <strong key={current.name} className={styles.activityEnter}><i />{current.readiness}</strong>
          <span>{current.name} · {String(active + 1).padStart(2, '0')} / 06</span>
        </div>
        <div className={styles.activity}>
          <span className={styles.telemetryLabel}>ACTIVITY STREAM</span>
          <p key={current.name} className={styles.activityEnter}>{current.activity}</p>
          <span>{current.source}</span>
        </div>
        <div className={styles.cycleProgress} key={active} data-stopped={stopped}><span /></div>
      </div>
      <p className={styles.illustrative}>Illustrative activity · not live system status</p>
      <div className={styles.contextCopy}>
        <h2 id="context-heading">One basin. Every signal connected.</h2>
        <p>From river observations to field decisions, a shared operational picture for the Indus Basin.</p>
      </div>
    </section>
  )
}
