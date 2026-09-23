// packages/dashboard/src/app/page.tsx
// Public landing page. No auth, no API calls, no AppShell — the signed-in
// launcher lives at /portal.
'use client'

import Link from 'next/link'
import {
  Droplets,
  Radio,
  Satellite,
  ShieldCheck,
  Waves,
  LineChart,
  Bell,
  MapPin,
  ArrowRight,
  FileText,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'

export default function LandingPage() {
  const { user, loading } = useAuth()
  const signedIn = !loading && !!user

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <SiteHeader signedIn={signedIn} />
      <Hero signedIn={signedIn} />
      <Capabilities />
      <DataSources />
      <Portals />
      <SiteFooter />
    </div>
  )
}

function SiteHeader({ signedIn }: { signedIn: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand shadow-card">
            <span className="text-sm font-bold text-white">Σ</span>
          </div>
          <div>
            <p className="text-sm font-semibold tracking-wide text-ink">IBCP-SCADA</p>
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink-subtle">Operations Console</p>
          </div>
        </div>

        <Link
          href={signedIn ? '/portal' : '/login'}
          className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-hover"
        >
          {signedIn ? 'Open Command Center' : 'Sign In'}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </header>
  )
}

function Hero({ signedIn }: { signedIn: boolean }) {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-20 pt-20 sm:px-6 lg:px-8 lg:pt-28">
      <span className="inline-flex items-center gap-2 rounded-full border border-brand/25 bg-brand-soft px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-brand">
        <Waves className="h-3.5 w-3.5" />
        Indus Basin Cyber-Physical System
      </span>

      <h1 className="mt-6 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl lg:text-6xl">
        Water intelligence for the{' '}
        <span className="text-brand">
          Indus Basin
        </span>
      </h1>

      <p className="mt-6 max-w-2xl text-base leading-7 text-ink-muted sm:text-lg">
        IBCP-SCADA brings dam and barrage telemetry, official flood bulletins and
        satellite observation into one operations console — so flood risk is seen
        early, water distribution is measured, and irrigation decisions rest on
        current data rather than yesterday&apos;s paperwork.
      </p>

      <div className="mt-10 flex flex-wrap items-center gap-4">
        <Link
          href={signedIn ? '/portal' : '/login'}
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-6 py-3 text-sm font-medium text-white shadow-card transition-colors hover:bg-brand-hover"
        >
          {signedIn ? 'Open Command Center' : 'Sign in to the console'}
          <ArrowRight className="h-4 w-4" />
        </Link>
        <a
          href="#capabilities"
          className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-surface px-6 py-3 text-sm font-medium text-ink transition-colors hover:bg-surface-alt"
        >
          What the system does
        </a>
      </div>

      <dl className="mt-16 grid gap-6 border-t border-line pt-10 sm:grid-cols-3">
        {[
          { term: 'Monitored assets', detail: 'Dams, barrages and link canals along the Indus and its tributaries' },
          { term: 'Refresh cadence', detail: 'IRSA readings ingested through the day; flood bulletins as issued' },
          { term: 'Access model', detail: 'Role-based portals with geographic scoping and a full audit trail' },
        ].map(({ term, detail }) => (
          <div key={term}>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-subtle">{term}</dt>
            <dd className="mt-2 text-sm leading-6 text-ink-muted">{detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

const CAPABILITIES = [
  {
    icon: Bell,
    title: 'Early warning',
    body: 'Readings are checked against per-asset warning and critical levels. Crossings raise alerts that operators acknowledge, escalate and resolve, with the full lifecycle recorded.',
    accent: 'bg-crit-soft text-crit',
  },
  {
    icon: LineChart,
    title: 'Forecasting',
    body: 'XGBoost models trained on historical river flow project water availability and flood risk over a short horizon, with walk-forward validation behind the numbers.',
    accent: 'bg-brand-soft text-brand',
  },
  {
    icon: MapPin,
    title: 'Downstream impact',
    body: 'For an asset at risk, the impact engine estimates travel time to downstream points and the population, settlements and infrastructure in the path.',
    accent: 'bg-brand-soft text-brand',
  },
  {
    icon: Droplets,
    title: 'Water availability',
    body: 'A weekly availability index per region, aggregated from surface-water extent, rainfall and evapotranspiration, so stress is comparable across the basin.',
    accent: 'bg-ok-soft text-ok',
  },
]

function Capabilities() {
  return (
    <section id="capabilities" className="border-t border-line bg-canvas">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
        <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          Built for the people who make the call
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted">
          Irrigation authorities, flood forecasting divisions and provincial disaster
          management — each sees the same underlying record, scoped to their region
          and responsibility.
        </p>

        <div className="mt-12 grid gap-6 sm:grid-cols-2">
          {CAPABILITIES.map(({ icon: Icon, title, body, accent }) => (
            <div
              key={title}
              className="rounded-2xl border border-line bg-surface p-6 transition-colors hover:border-line-strong"
            >
              <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${accent}`}>
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="mt-5 text-base font-semibold text-ink">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-ink-muted">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const SOURCES = [
  {
    icon: FileText,
    name: 'IRSA',
    detail: 'Daily river and reservoir bulletins — levels, inflow and outflow at each dam, barrage and link canal.',
  },
  {
    icon: Radio,
    name: 'PMD · Flood Forecasting Division',
    detail: 'Flood bulletins and river status: discharge readings and the flood stage declared at each site.',
  },
  {
    icon: Satellite,
    name: 'Google Earth Engine',
    detail: 'MODIS and CHIRPS products for rainfall, evapotranspiration and surface-water extent by region.',
  },
  {
    icon: ShieldCheck,
    name: 'Field telemetry',
    detail: 'Sensor and controller readings from the operational layer, kept separate from official published data.',
  },
]

function DataSources() {
  return (
    <section className="border-t border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
        <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          Where the data comes from
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted">
          Every observation keeps its source and publication time, so an official
          reading is never confused with a modelled or simulated one.
        </p>

        <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-line bg-surface-alt sm:grid-cols-2">
          {SOURCES.map(({ icon: Icon, name, detail }) => (
            <div key={name} className="bg-surface p-6">
              <div className="flex items-center gap-3">
                <Icon className="h-4 w-4 text-brand" />
                <h3 className="text-sm font-semibold text-ink">{name}</h3>
              </div>
              <p className="mt-3 text-sm leading-6 text-ink-muted">{detail}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const PORTAL_SUMMARY = [
  { name: 'AquaVision · Water', detail: 'Availability, stress index, early warning and operational telemetry.', accent: 'text-brand' },
  { name: 'Crop Yield', detail: 'Regional yield forecasting and crop health for irrigation planning.', accent: 'text-ok' },
  { name: 'Land · GeoVision', detail: 'Remote-sensing overview and derived land indices.', accent: 'text-brand' },
  { name: 'System', detail: 'Administration: health, audit trail and portal access control.', accent: 'text-warn' },
]

function Portals() {
  return (
    <section className="border-t border-line bg-canvas">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 lg:px-8">
        <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          Four portals, one record
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted">
          You see only what your role grants. Sign in to open the portals assigned
          to your account.
        </p>

        <ul className="mt-10 space-y-3">
          {PORTAL_SUMMARY.map(({ name, detail, accent }) => (
            <li
              key={name}
              className="flex flex-col gap-1 rounded-xl border border-line bg-surface px-5 py-4 sm:flex-row sm:items-center sm:gap-6"
            >
              <span className={`text-sm font-semibold ${accent} sm:w-56 sm:shrink-0`}>{name}</span>
              <span className="text-sm leading-6 text-ink-muted">{detail}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <p className="text-[11px] text-ink-subtle">
          IBCP-SCADA · Indus Basin Cyber-Physical System · AquaVision AI (XGBoost · GEE MODIS/CHIRPS)
        </p>
        <Link href="/login" className="text-[11px] font-medium text-brand hover:text-brand">
          Sign in →
        </Link>
      </div>
    </footer>
  )
}
