// packages/dashboard/src/app/key-terms/page.tsx
// Plain-language reference for the domain terms the console puts on screen.
// Definitions describe what THIS system does with each term — the thresholds,
// weights and lifecycles below are the ones the backend actually applies.
'use client'

import { useMemo, useState } from 'react'
import { BookOpen, Search } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardBody, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/state'

interface Term {
  term: string
  short?: string
  definition: string
  /** Where the reader will run into it in this console. */
  seenOn?: string
}

interface Section {
  id: string
  title: string
  blurb: string
  terms: Term[]
}

const SECTIONS: Section[] = [
  {
    id: 'water',
    title: 'Water & hydrology',
    blurb: 'The quantities this system measures at dams, barrages and river stations.',
    terms: [
      {
        term: 'WAI',
        short: 'Water Availability Index',
        definition:
          'A 0–100 score for how much water is available, where 100 is plentiful and 0 is severe shortage. The real-time version is built from three parts: how today\'s flow ranks against the last 90 days (50%), how full the reservoir is (30%), and whether the last 7 days are wetter or drier than the 7 before (20%). Barrages have no storage, so their score is re-weighted across the other two.',
        seenOn: 'Overview, Indicators, Predictions',
      },
      {
        term: 'Severity bands',
        definition:
          'The words attached to a WAI score. Below 25 is Critical, below 40 Severe, below 55 Stressed, below 70 Moderate, and 70 or above Normal. A lower score always means less water, so Critical is the worst case.',
        seenOn: 'Everywhere a coloured status badge appears',
      },
      {
        term: 'Cusec',
        definition:
          'Cubic feet per second — the unit for how fast water moves past a point. One cusec is roughly 28 litres every second. Pakistani irrigation practice uses cusecs rather than cubic metres.',
        seenOn: 'Assets, FFD Bulletins, Virtual HMI',
      },
      {
        term: 'MAF',
        short: 'Million Acre-Feet',
        definition:
          'A volume, not a rate: the amount of water that would cover one million acres to a depth of one foot. Used for reservoir capacity.',
        seenOn: 'Asset details',
      },
      {
        term: 'Inflow / Outflow',
        definition:
          'Inflow is water arriving at a dam or barrage; outflow is water released downstream. The gap between them is what the structure is storing or draining.',
        seenOn: 'Assets, Virtual HMI',
      },
      {
        term: 'Discharge',
        definition:
          'The volume of water flowing past a river gauge per second. For a river station it is the headline reading; for a barrage it is what passes through.',
        seenOn: 'FFD Bulletins, Flood Map',
      },
      {
        term: 'Gauge level',
        definition:
          'The height of the water surface at a measuring station, in feet. Compared against that site\'s warning and critical marks to decide whether an alert fires.',
        seenOn: 'Assets, Alerts',
      },
      {
        term: 'Barrage',
        definition:
          'A low structure across a river that raises the water level to divert it into canals. Unlike a dam it stores very little, which is why barrages show no storage percentage.',
        seenOn: 'Assets, Flood Map',
      },
      {
        term: 'Link canal',
        definition:
          'A man-made channel that moves water from one river to another, so a surplus in one basin can cover a shortfall in the next.',
        seenOn: 'Assets, IRSA ingestion',
      },
      {
        term: 'Travel time',
        definition:
          'How long a flood wave takes to reach a downstream point. This is the number that turns a reading into a warning: it tells an operator how many hours there are to act.',
        seenOn: 'Flood Arrival Map, Downstream Impact',
      },
      {
        term: 'Flood stage',
        definition:
          'The official classification in a PMD bulletin — Below Low, Low, Medium, High, or Exceptionally High — describing how serious flow at a site is.',
        seenOn: 'FFD Bulletins',
      },
    ],
  },
  {
    id: 'satellite',
    title: 'Satellite & weather data',
    blurb: 'What the system observes from orbit, and the indices derived from it.',
    terms: [
      {
        term: 'NDVI',
        short: 'Normalized Difference Vegetation Index',
        definition:
          'A −1 to 1 measure of how green and healthy vegetation is, from how strongly plants reflect near-infrared light. Higher means healthier crops; a falling NDVI can signal water stress before a farmer sees it.',
        seenOn: 'GeoVision, Crop Yield',
      },
      {
        term: 'NDWI / MNDWI',
        short: 'Normalized Difference Water Index',
        definition:
          'The same idea applied to water: these indices separate water from land in a satellite image, which is how the system estimates the surface area of a reservoir or flooded zone without anyone visiting it.',
        seenOn: 'GeoVision, surface-water pipeline',
      },
      {
        term: 'ET',
        short: 'Evapotranspiration',
        definition:
          'Water lost to the air — evaporating from soil and transpiring from plants — in millimetres. High ET means the landscape is drying out quickly, so the same rainfall goes less far.',
        seenOn: 'Overview, Indicators',
      },
      {
        term: 'CHIRPS',
        definition:
          'A rainfall dataset combining satellite estimates with ground station records, used here as the rainfall input where no local gauge exists.',
        seenOn: 'Overview, GEE pipeline',
      },
      {
        term: 'MODIS',
        definition:
          'Instruments aboard NASA satellites that image the whole planet every day or two. This system uses their evapotranspiration and vegetation products.',
        seenOn: 'Overview, GeoVision',
      },
      {
        term: 'ERA5-Land',
        definition:
          'A reanalysis dataset: a physics model run backwards over historical observations to produce a consistent record of past weather, used to fill gaps the satellites miss.',
        seenOn: 'Indicators, data provenance',
      },
      {
        term: 'GEE',
        short: 'Google Earth Engine',
        definition:
          'A cloud platform holding decades of satellite imagery. The system sends it a calculation and receives summary numbers back, so no imagery is ever downloaded.',
        seenOn: 'Pipelines, provenance labels',
      },
      {
        term: 'Anomaly',
        definition:
          'A reading expressed as a difference from that place\'s own historical average, rather than as an absolute. "Rainfall anomaly −30%" means this location got about a third less rain than it normally would.',
        seenOn: 'Overview, Indicators',
      },
    ],
  },
  {
    id: 'sources',
    title: 'Data sources & trust',
    blurb: 'Where each number comes from, and how the system ranks conflicting readings.',
    terms: [
      {
        term: 'IRSA',
        short: 'Indus River System Authority',
        definition:
          'The authority that allocates water between provinces and publishes a daily bulletin of levels, inflows and outflows. The system downloads that PDF and reads the table out of it automatically.',
        seenOn: 'Assets, provenance labels',
      },
      {
        term: 'PMD / FFD',
        short: 'Pakistan Meteorological Department / Flood Forecasting Division',
        definition:
          'The official source for flood bulletins and river status. Where IRSA reports how much water there is, FFD reports how dangerous it currently is.',
        seenOn: 'FFD Bulletins',
      },
      {
        term: 'GloFAS',
        short: 'Global Flood Awareness System',
        definition:
          'A European service holding a long modelled history of river flow worldwide. Used here to give the models decades of training history where local records are thin.',
        seenOn: 'Model training, Registry',
      },
      {
        term: 'Provenance',
        definition:
          'The record of where a number came from and when it was published. Every observation keeps its source and timestamp, so an official reading is never silently mixed with a modelled one.',
        seenOn: 'Overview footer, Audit Log',
      },
      {
        term: 'Source priority',
        definition:
          'A ranking used when two sources disagree about the same place and time. Official published readings outrank modelled or simulated values, so a simulation can never overwrite an IRSA row.',
        seenOn: 'Soft OT, ingestion logs',
      },
      {
        term: 'Quarantine',
        definition:
          'Where a reading goes when it fails a sanity check — a negative flow, or a level far outside the plausible range. It is kept for inspection rather than deleted, and excluded from the dashboards.',
        seenOn: 'Pipelines, Data quality',
      },
    ],
  },
  {
    id: 'ml',
    title: 'Machine learning',
    blurb: 'How forecasts are produced, judged, and allowed into production.',
    terms: [
      {
        term: 'Walk-forward validation',
        definition:
          'Testing a forecasting model the honest way: train it only on data up to a past date, predict what happened next, then step forward and repeat. It mimics real use, where tomorrow is genuinely unknown.',
        seenOn: 'ML Validation',
      },
      {
        term: 'Model lifecycle',
        definition:
          'A model is not trusted on arrival. It starts EXPERIMENTAL, then runs in SHADOW — making real predictions that are scored but never shown — and only becomes APPROVED and then PRODUCTION once its accuracy holds up. Models that fail are REJECTED.',
        seenOn: 'Model Registry',
      },
      {
        term: 'Shadow scoring',
        definition:
          'Running a candidate model alongside the live one every day and recording how it would have done, without anyone acting on its output. It is how a model earns promotion on evidence rather than optimism.',
        seenOn: 'Model Registry',
      },
      {
        term: 'MAE',
        short: 'Mean Absolute Error',
        definition:
          'The average size of the model\'s mistakes, in the unit being predicted. An MAE of 500 cusecs means the forecast is off by about 500 cusecs on a typical day.',
        seenOn: 'ML Validation, Analyst',
      },
      {
        term: 'MAPE',
        short: 'Mean Absolute Percentage Error',
        definition:
          'The same idea expressed as a percentage, so errors at a small river station and a huge dam can be compared fairly.',
        seenOn: 'ML Validation',
      },
      {
        term: 'R²',
        short: 'R-squared',
        definition:
          'How much of the real variation the model explains, from 0 to 1. Near 1 means it tracks the ups and downs closely; near 0 means it is little better than guessing the average.',
        seenOn: 'ML Validation, Analyst',
      },
      {
        term: 'AUC',
        definition:
          'A 0.5–1 score for yes/no predictions such as "will this flood?". 0.5 is a coin toss, 1 is perfect. It rewards ranking risky days above safe ones.',
        seenOn: 'ML Validation, Analyst',
      },
      {
        term: 'Lead time',
        definition:
          'How far ahead a forecast reaches — a 3-day lead time predicts the state three days from now. Accuracy always falls as lead time grows.',
        seenOn: 'Predictions',
      },
      {
        term: 'Reliability tier',
        definition:
          'A per-asset grade for how much to trust a forecast, derived from that asset\'s own past scored errors rather than from the model\'s overall average.',
        seenOn: 'Predictions',
      },
      {
        term: 'Confidence interval',
        definition:
          'The range a forecast is likely to fall within, not just the single number. A wide band is the model admitting uncertainty, which is more useful than false precision.',
        seenOn: 'Predictions',
      },
    ],
  },
  {
    id: 'ot',
    title: 'SCADA & control systems',
    blurb: 'The industrial-control side, simulated in software here — no hardware is ever commanded.',
    terms: [
      {
        term: 'SCADA',
        short: 'Supervisory Control and Data Acquisition',
        definition:
          'The class of system that watches industrial equipment and lets operators act on it. In water management that means gates, pumps and gauges across a whole basin.',
        seenOn: 'Throughout',
      },
      {
        term: 'PLC',
        short: 'Programmable Logic Controller',
        definition:
          'A rugged industrial computer sitting at the equipment itself, running safety logic in a fast loop — closing a gate when a level is exceeded, for instance, without waiting for a human.',
        seenOn: 'Soft OT',
      },
      {
        term: 'RTU',
        short: 'Remote Terminal Unit',
        definition:
          'A device at a remote site that records readings and forwards them when a link is available. Built for places with no reliable power or network.',
        seenOn: 'Soft OT',
      },
      {
        term: 'HMI',
        short: 'Human-Machine Interface',
        definition:
          'The operator-facing screen for a piece of equipment, showing its live tags and offering the controls. The Virtual HMI here mirrors that layout against a simulated device.',
        seenOn: 'Soft OT device pages',
      },
      {
        term: 'Soft OT',
        definition:
          'A software twin of the operational-technology layer. It replays official readings and lets scenarios run, so control-room behaviour can be demonstrated without any connection to a real dam.',
        seenOn: 'Soft OT (PLC/RTU)',
      },
      {
        term: 'Track vs scenario mode',
        definition:
          'In track mode a simulated device replays the official IRSA/FFD record for the day. Setting a setpoint switches that asset to scenario mode, where values are hypothetical and clearly labelled as such.',
        seenOn: 'Soft OT',
      },
      {
        term: 'Setpoint',
        definition:
          'The target value an operator asks a controller to hold — a gate opening or a release rate. Here it only ever moves the simulation.',
        seenOn: 'Virtual HMI',
      },
      {
        term: 'Interlock',
        definition:
          'A safety rule the controller enforces regardless of what is requested, such as refusing to open a gate beyond a limit. Interlocks exist so a mistaken command cannot cause harm.',
        seenOn: 'Soft OT',
      },
      {
        term: 'AI / DI tags',
        short: 'Analogue Input / Digital Input',
        definition:
          'The named signals a device publishes. Analogue inputs carry measured numbers such as level or flow; digital inputs carry true/false states such as "power OK".',
        seenOn: 'Virtual HMI',
      },
      {
        term: 'Fault injection',
        definition:
          'Deliberately simulating a failure — a stuck sensor, a comms drop, an inflow surge — to show how the system and the operator respond. A demonstration tool, not a real command.',
        seenOn: 'Virtual HMI',
      },
    ],
  },
  {
    id: 'ops',
    title: 'Operations & workflow',
    blurb: 'How a reading becomes an alert, and how people are held to answering it.',
    terms: [
      {
        term: 'Alert lifecycle',
        definition:
          'An alert moves through New, Acknowledged, Investigating, Escalated and Resolved. Each step records who acted and when, so the trail shows not just that a warning fired but what was done about it.',
        seenOn: 'Alerts, My Tasks',
      },
      {
        term: 'Escalation',
        definition:
          'Raising an alert to a higher authority when it is severe or has gone unanswered too long.',
        seenOn: 'Alerts',
      },
      {
        term: 'SLA',
        short: 'Service Level Agreement',
        definition:
          'The time limit for responding to an alert. A breached SLA means nobody answered in the agreed window — tracked because a flood warning that sits unread is the same as no warning.',
        seenOn: 'My Tasks, Alerts',
      },
      {
        term: 'Episode',
        definition:
          'A group of related alerts from the same underlying event, so one flood peak crossing several thresholds reads as a single incident rather than a dozen separate ones.',
        seenOn: 'Alerts, Registry rollups',
      },
      {
        term: 'Instruction',
        definition:
          'A task issued from an alert to a named operator — inspect a gate, confirm a reading — which is then accepted, worked and reported back.',
        seenOn: 'My Tasks',
      },
      {
        term: 'Verification',
        definition:
          'A supervisor confirming that the work reported against an instruction actually happened, with a note. The step that closes the loop.',
        seenOn: 'My Tasks',
      },
      {
        term: 'RBAC',
        short: 'Role-Based Access Control',
        definition:
          'Permissions attached to roles rather than individuals, so an operator, an analyst and an administrator each see a different console. Access is also scoped geographically — a Sindh operator sees Sindh.',
        seenOn: 'Portal Access, Command Center',
      },
      {
        term: 'Audit log',
        definition:
          'An append-only record of who did what and when. In a system that can influence flood response, being able to reconstruct decisions afterwards matters as much as making them.',
        seenOn: 'Audit Log',
      },
    ],
  },
]

const ALL_TERMS = SECTIONS.reduce((n, s) => n + s.terms.length, 0)

export default function KeyTermsPage() {
  const [query, setQuery] = useState('')
  const [activeSection, setActiveSection] = useState<string | null>(null)

  const sections = useMemo(() => {
    const q = query.trim().toLowerCase()
    return SECTIONS
      .filter((s) => !activeSection || s.id === activeSection)
      .map((s) => ({
        ...s,
        terms: q
          ? s.terms.filter(
              (t) =>
                t.term.toLowerCase().includes(q) ||
                (t.short ?? '').toLowerCase().includes(q) ||
                t.definition.toLowerCase().includes(q)
            )
          : s.terms,
      }))
      .filter((s) => s.terms.length > 0)
  }, [query, activeSection])

  const matches = sections.reduce((n, s) => n + s.terms.length, 0)

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          title="Key Terms"
          description="Plain-language explanations of the terms this console uses. Thresholds and weights quoted here are the ones the system actually applies."
          icon={<BookOpen className="h-6 w-6" />}
          badge={<Badge tone="neutral">{ALL_TERMS} terms</Badge>}
        />

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="relative w-full sm:max-w-sm">
            <span className="sr-only">Search terms</span>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle"
              aria-hidden
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search a term, e.g. WAI or cusec"
              className="h-9 w-full rounded border border-line-strong bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-ink-subtle focus:border-brand focus:outline-none"
            />
          </label>

          <div className="flex flex-wrap gap-1.5">
            <Button
              variant={activeSection === null ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setActiveSection(null)}
            >
              All
            </Button>
            {SECTIONS.map((s) => (
              <Button
                key={s.id}
                variant={activeSection === s.id ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setActiveSection(s.id)}
              >
                {s.title}
              </Button>
            ))}
          </div>
        </div>

        {sections.length === 0 ? (
          <EmptyState
            title="No matching term"
            message={`Nothing here matches “${query}”. Try a shorter word, or clear the filter.`}
            action={
              <Button variant="secondary" size="sm" onClick={() => { setQuery(''); setActiveSection(null) }}>
                Clear search
              </Button>
            }
          />
        ) : (
          <>
            {query && (
              <p className="text-caption text-ink-subtle">
                {matches} {matches === 1 ? 'term' : 'terms'} matching “{query}”
              </p>
            )}

            {sections.map((section) => (
              <Card key={section.id}>
                <CardHeader title={section.title} subtitle={section.blurb} />
                <CardBody className="p-0">
                  <dl className="divide-y divide-line">
                    {section.terms.map((t) => (
                      <div
                        key={t.term}
                        className="grid gap-1 px-4 py-3.5 sm:grid-cols-[13rem_1fr] sm:gap-5"
                      >
                        <dt className="min-w-0">
                          <span className="text-sm font-semibold text-ink">{t.term}</span>
                          {t.short && (
                            <span className="mt-0.5 block text-caption text-ink-subtle">{t.short}</span>
                          )}
                        </dt>
                        <dd className="min-w-0">
                          <p className="text-sm leading-6 text-ink-muted">{t.definition}</p>
                          {t.seenOn && (
                            <p className="mt-1.5 text-caption text-ink-subtle">
                              Seen on: {t.seenOn}
                            </p>
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </CardBody>
              </Card>
            ))}
          </>
        )}
      </div>
    </AppShell>
  )
}
