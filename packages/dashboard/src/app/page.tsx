// packages/dashboard/src/app/page.tsx
// Public landing page. No auth gate, API calls or AppShell.
'use client'

import Link from 'next/link'
import {
  Activity,
  ArrowRight,
  Bell,
  Database,
  Radio,
  Satellite,
  ShieldCheck,
  Waves,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import styles from './landing.module.css'

const FLOW: Array<{
  step: string
  title: string
  detail: string
  source: string
  icon: LucideIcon
}> = [
  {
    step: '01',
    title: 'Observations',
    detail: 'River levels, reservoir inflow and outflow, satellite rainfall, surface water and field telemetry enter one traceable record.',
    source: 'IRSA · PMD/FFD · GEE · field sensors',
    icon: Radio,
  },
  {
    step: '02',
    title: 'Analysis',
    detail: 'Readings are checked for freshness and provenance, then compared with asset thresholds and regional water-stress indicators.',
    source: 'Validation · WAI · threshold engine',
    icon: Activity,
  },
  {
    step: '03',
    title: 'Forecasts',
    detail: 'Short-horizon models estimate water availability, flood risk and the likely travel of a release through downstream assets.',
    source: 'XGBoost · downstream impact model',
    icon: Satellite,
  },
  {
    step: '04',
    title: 'Operator decisions',
    detail: 'Teams acknowledge, investigate and escalate alerts from the same operational picture, with each action recorded for review.',
    source: 'Role-based queues · audit trail',
    icon: Bell,
  },
]

export default function LandingPage() {
  const { user, loading } = useAuth()
  const signedIn = !loading && !!user

  return (
    <div className={styles.page}>
      <SiteHeader signedIn={signedIn} />
      <main>
        <Hero signedIn={signedIn} />
        <ConsoleEvidence />
        <OperationalFlow />
        <AccessClose signedIn={signedIn} />
      </main>
      <SiteFooter signedIn={signedIn} />
    </div>
  )
}

function SiteHeader({ signedIn }: { signedIn: boolean }) {
  return (
    <header className={styles.header}>
      <div className={styles.headerInner}>
        <Link href="/" className={styles.wordmark} aria-label="IBCP-SCADA home">
          <span className={styles.wordmarkMark} aria-hidden="true">Σ</span>
          <span>
            <strong>IBCP-SCADA</strong>
            <small>Indus Basin Operations</small>
          </span>
        </Link>

        <Link href={signedIn ? '/portal' : '/login'} className={styles.headerAction}>
          {signedIn ? 'Open Console' : 'Sign In'}
          <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </header>
  )
}

function Hero({ signedIn }: { signedIn: boolean }) {
  return (
    <section className={styles.hero}>
      <div className={styles.heroCopy}>
        <p className={styles.systemLabel}>
          <Waves aria-hidden="true" />
          Indus Basin cyber-physical system
        </p>
        <h1>One view of the Indus Basin.</h1>
        <p className={styles.heroLede}>
          IBCP-SCADA connects official river bulletins, satellite observation,
          operational telemetry and forecasting in one decision surface for water
          and flood management.
        </p>
        <Link href={signedIn ? '/portal' : '/login'} className={styles.primaryAction}>
          {signedIn ? 'Open Command Center' : 'Open the Console'}
          <ArrowRight aria-hidden="true" />
        </Link>
        <dl className={styles.heroFacts}>
          <div>
            <dt>Operational scope</dt>
            <dd>Dams · barrages · link canals</dd>
          </div>
          <div>
            <dt>Decision record</dt>
            <dd>Observed · modelled · actioned</dd>
          </div>
        </dl>
      </div>
      <BasinMap />
    </section>
  )
}

function BasinMap() {
  return (
    <figure className={styles.basinFigure}>
      <div className={styles.mapHeading}>
        <span>Basin schematic</span>
        <span>North → South</span>
      </div>
      <svg
        className={styles.basinMap}
        viewBox="0 0 620 600"
        role="img"
        aria-labelledby="basin-map-title basin-map-description"
      >
        <title id="basin-map-title">Schematic of the Indus Basin river network</title>
        <desc id="basin-map-description">
          The Indus river and major tributaries flowing past Tarbela, Chashma,
          Guddu, Sukkur and Kotri monitoring locations.
        </desc>
        <g className={styles.mapGrid} aria-hidden="true">
          <path d="M40 120H580 M40 240H580 M40 360H580 M40 480H580" />
          <path d="M140 40V560 M280 40V560 M420 40V560" />
        </g>
        <path
          className={styles.basinLand}
          d="M233 34C278 21 342 39 375 75C409 112 407 159 443 193C482 230 535 258 542 311C550 374 499 419 463 464C425 512 390 574 324 579C260 583 226 531 189 486C151 439 99 410 82 351C64 289 102 244 133 196C163 149 178 63 233 34Z"
        />
        <g className={styles.tributaries} aria-hidden="true">
          <path d="M183 105C220 121 241 139 270 171" />
          <path d="M472 144C420 158 384 181 342 212" />
          <path d="M505 219C450 224 407 243 357 269" />
          <path d="M510 291C454 287 411 299 359 315" />
          <path d="M475 353C431 341 397 346 354 356" />
        </g>
        <path
          className={styles.indusRiver}
          d="M270 71C256 119 286 151 276 196C266 240 304 264 295 307C286 354 317 385 308 426C300 464 326 501 337 552"
        />
        <g className={styles.mapStations}>
          <MapStation x={271} y={151} label="Tarbela" align="start" />
          <MapStation x={278} y={239} label="Chashma" align="start" />
          <MapStation x={297} y={354} label="Guddu" align="end" attention />
          <MapStation x={309} y={425} label="Sukkur" align="start" />
          <MapStation x={333} y={516} label="Kotri" align="end" />
        </g>
      </svg>
      <figcaption className={styles.mapLegend}>
        <span><i className={styles.legendRiver} />River network</span>
        <span><i className={styles.legendStation} />Monitored location</span>
        <span>Schematic · not to scale</span>
      </figcaption>
    </figure>
  )
}

function MapStation({
  x,
  y,
  label,
  align,
  attention = false,
}: {
  x: number
  y: number
  label: string
  align: 'start' | 'end'
  attention?: boolean
}) {
  const offset = align === 'start' ? 18 : -18
  return (
    <g className={attention ? styles.stationAttention : undefined}>
      {attention && <circle className={styles.stationSignal} cx={x} cy={y} r="12" />}
      <circle className={styles.stationDot} cx={x} cy={y} r="5" />
      <path className={styles.stationRule} d={`M${x + (align === 'start' ? 6 : -6)} ${y}h${offset}`} />
      <text className={styles.stationLabel} x={x + offset + (align === 'start' ? 6 : -6)} y={y + 4} textAnchor={align}>
        {label}
      </text>
    </g>
  )
}

function ConsoleEvidence() {
  return (
    <section className={styles.consoleSection}>
      <div className={styles.sectionIntro}>
        <div>
          <p className={styles.sectionLabel}>The operational picture</p>
          <h2>See the reading, its source and what needs attention.</h2>
        </div>
        <p>
          The console keeps observed, modelled and simulated information distinct,
          while bringing the signals an operator needs into one scan.
        </p>
      </div>
      <figure className={styles.consolePreview}>
        <div className={styles.consoleTopline}>
          <div>
            <span className={styles.consoleMark}>Σ</span>
            <strong>AquaVision · National overview</strong>
          </div>
          <span className={styles.sampleFlag}>Illustrative sample</span>
        </div>
        <div className={styles.metricStrip}>
          <Metric label="Reservoir level" value="72.4" unit="ft" source="Sample · Tarbela" />
          <Metric label="Water availability" value="61" unit="/ 100" source="Sample · WAI" />
          <Metric label="Priority queue" value="2" unit="alerts" source="Sample · operator" attention />
        </div>
        <div className={styles.consoleBody}>
          <div className={styles.networkPanel}>
            <div className={styles.panelHeading}>
              <div>
                <span>Downstream chain</span>
                <strong>Tarbela → Kotri</strong>
              </div>
              <span className={styles.nominalStatus}>Nominal</span>
            </div>
            <svg viewBox="0 0 620 178" role="img" aria-label="Illustrative downstream asset chain">
              <path className={styles.networkLine} d="M45 90C145 42 205 136 306 90S466 43 575 90" />
              {[
                [62, 82, 'Tarbela'],
                [188, 105, 'Chashma'],
                [314, 86, 'Guddu'],
                [443, 64, 'Sukkur'],
                [563, 88, 'Kotri'],
              ].map(([x, y, name]) => (
                <g key={name as string}>
                  <circle className={styles.networkNode} cx={x as number} cy={y as number} r="7" />
                  <text className={styles.networkLabel} x={x as number} y={(y as number) + 28} textAnchor="middle">{name}</text>
                </g>
              ))}
            </svg>
          </div>
          <div className={styles.alertPanel}>
            <div className={styles.panelHeading}>
              <div>
                <span>Operator queue</span>
                <strong>What needs review</strong>
              </div>
            </div>
            <div className={styles.alertRow}>
              <span className={styles.alertIcon}><Bell aria-hidden="true" /></span>
              <div>
                <strong>Rising discharge</strong>
                <span>Sample · Guddu barrage</span>
              </div>
              <span className={styles.warningStatus}>Review</span>
            </div>
            <div className={styles.alertRow}>
              <span className={styles.dataIcon}><Database aria-hidden="true" /></span>
              <div>
                <strong>Source freshness</strong>
                <span>IRSA bulletin received</span>
              </div>
              <span className={styles.nominalStatus}>Current</span>
            </div>
          </div>
        </div>
        <figcaption>Interface preview · sample values for presentation only, not current readings.</figcaption>
      </figure>
    </section>
  )
}

function Metric({
  label,
  value,
  unit,
  source,
  attention = false,
}: {
  label: string
  value: string
  unit: string
  source: string
  attention?: boolean
}) {
  return (
    <div className={attention ? styles.metricAttention : styles.metric}>
      <span>{label}</span>
      <strong>{value} <small>{unit}</small></strong>
      <span>{source}</span>
    </div>
  )
}

function OperationalFlow() {
  return (
    <section className={styles.flowSection}>
      <div className={styles.flowHeading}>
        <p className={styles.sectionLabel}>One connected record</p>
        <h2>From observation to decision.</h2>
        <p>
          Each stage keeps its source visible, so published readings, derived
          indicators and model output are never mistaken for one another.
        </p>
      </div>
      <ol className={styles.flowList}>
        {FLOW.map(({ step, title, detail, source, icon: Icon }) => (
          <li key={step}>
            <div className={styles.flowStepHeading}>
              <span>{step}</span>
              <Icon aria-hidden="true" />
            </div>
            <h3>{title}</h3>
            <p>{detail}</p>
            <small>{source}</small>
          </li>
        ))}
      </ol>
    </section>
  )
}

function AccessClose({ signedIn }: { signedIn: boolean }) {
  return (
    <section className={styles.accessSection}>
      <div className={styles.accessIcon} aria-hidden="true">
        <ShieldCheck />
      </div>
      <div>
        <p className={styles.sectionLabel}>Role-based access</p>
        <h2>One record. The right view for every role.</h2>
        <p>
          Water operators, analysts and administrators enter through the same
          console. Permissions and geographic scope determine what each person can
          inspect and act on.
        </p>
      </div>
      <Link href={signedIn ? '/portal' : '/login'} className={styles.textAction}>
        {signedIn ? 'Go to Command Center' : 'Sign in to IBCP-SCADA'}
        <ArrowRight aria-hidden="true" />
      </Link>
    </section>
  )
}

function SiteFooter({ signedIn }: { signedIn: boolean }) {
  return (
    <footer className={styles.footer}>
      <p className={styles.footerStatement}>
        A connected basin deserves one clear operational picture.
      </p>
      <div className={styles.footerMeta}>
        <span>IBCP-SCADA · Indus Basin Cyber-Physical System</span>
        <Link href={signedIn ? '/portal' : '/login'}>
          {signedIn ? 'Open Console' : 'Sign In'}
        </Link>
      </div>
    </footer>
  )
}
