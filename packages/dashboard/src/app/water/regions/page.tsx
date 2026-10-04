// packages/dashboard/src/app/water/regions/page.tsx
// AquaVision Regions - GEE-backed indicator coverage, WAI, quality and alerts.
'use client'

import { useMemo, useState } from 'react'
import { MapPin, Search, Activity, Droplets, Bell } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge, SeverityBadge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useWaterRegions, useWaterIndicators, useStressAlerts } from '@/features/water/hooks'
import { SEVERITY_RANK, type SeverityLevel } from '@/lib/severity'
import { fmtNumber, fmtPct } from '@/lib/format'
import Link from 'next/link'

type SortKey = 'name' | 'wai' | 'severity' | 'alerts'
type SortDir = 'asc' | 'desc'
type TypeFilter = 'all' | 'province' | 'district'

interface RegionRow {
  id: number
  name: string
  code?: string | null
  type: string
  latestWeek: string
  wai: number | null
  severity: SeverityLevel | null
  quality: string | null
  rainfallAnomaly: number | null
  months: number
  firstWeek: string
  history: number[]
  openAlerts: number
}

const isOpenStatus = (status: string | null | undefined) =>
  (status ?? '').toUpperCase() !== 'RESOLVED'

const fmtMonth = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })

export default function RegionsPage() {
  const regionsQuery = useWaterRegions()
  const indicatorsQuery = useWaterIndicators({ limit: 500 })
  const stressQuery = useStressAlerts({ limit: 500 })

  const [query, setQuery] = useState('')
  const [typeF, setTypeF] = useState<TypeFilter>('all')
  const [sevF, setSevF] = useState<'all' | SeverityLevel>('all')
  const [sortKey, setSortKey] = useState<SortKey>('severity')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const rows = useMemo<RegionRow[]>(() => {
    const regions = regionsQuery.data ?? []
    const indicators = indicatorsQuery.data ?? []
    const stress = stressQuery.data ?? []

    const byRegion = new Map<number, typeof indicators>()
    for (const ind of indicators) {
      const list = byRegion.get(ind.regionId) ?? []
      list.push(ind)
      byRegion.set(ind.regionId, list)
    }
    const openByRegion = new Map<number, number>()
    for (const alert of stress) {
      if (!isOpenStatus(alert.status)) continue
      openByRegion.set(alert.region_id, (openByRegion.get(alert.region_id) ?? 0) + 1)
    }

    const built: RegionRow[] = []
    for (const region of regions) {
      const series = (byRegion.get(region.id) ?? []).sort((a, b) =>
        a.weekStart.localeCompare(b.weekStart),
      )
      if (!series.length) continue
      const latest = series[series.length - 1]
      built.push({
        id: region.id,
        name: region.name,
        code: region.code,
        type: region.type,
        latestWeek: latest.weekStart,
        wai: latest.waiScore ?? null,
        severity: latest.severity ?? null,
        quality: latest.qualityStatus ?? null,
        rainfallAnomaly: latest.rainfallAnomaly ?? null,
        months: series.length,
        firstWeek: series[0].weekStart,
        history: series.slice(-12).map((s) => Number(s.waiScore ?? 0)),
        openAlerts: openByRegion.get(region.id) ?? 0,
      })
    }
    return built
  }, [regionsQuery.data, indicatorsQuery.data, stressQuery.data])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const out = rows.filter((r) => {
      if (q && !r.name.toLowerCase().includes(q) && !(r.code ?? '').toLowerCase().includes(q)) return false
      if (typeF === 'province' && r.type !== 'province') return false
      if (typeF === 'district' && r.type === 'province') return false
      if (sevF !== 'all' && r.severity !== sevF) return false
      return true
    })
    const dir = sortDir === 'asc' ? 1 : -1
    out.sort((a, b) => {
      if (sortKey === 'name') return dir * a.name.localeCompare(b.name)
      if (sortKey === 'alerts') return dir * (a.openAlerts - b.openAlerts)
      if (sortKey === 'wai') {
        if (a.wai == null && b.wai == null) return 0
        if (a.wai == null) return 1
        if (b.wai == null) return -1
        return dir * (a.wai - b.wai)
      }
      const rankA = SEVERITY_RANK[a.severity ?? 'Normal'] ?? 0
      const rankB = SEVERITY_RANK[b.severity ?? 'Normal'] ?? 0
      if (rankA === rankB) return a.name.localeCompare(b.name)
      return dir === 1 ? rankA - rankB : rankB - rankA
    })
    return out
  }, [rows, query, typeF, sevF, sortKey, sortDir])

  const avgWai = useMemo(() => {
    const values = filtered.map((r) => r.wai).filter((v): v is number => v != null)
    if (!values.length) return null
    return values.reduce((sum, v) => sum + v, 0) / values.length
  }, [filtered])

  const openAlerts = rows.reduce((sum, r) => sum + r.openAlerts, 0)
  const withoutData = (regionsQuery.data ?? []).length - rows.length
  const latestMonth = rows.length ? rows.map((r) => r.latestWeek).sort().slice(-1)[0] : null

  const provinces = filtered.filter((r) => r.type === 'province')
  const districts = filtered.filter((r) => r.type !== 'province')

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'name' ? 'asc' : 'desc')
    }
  }

  const pending = regionsQuery.isPending || indicatorsQuery.isPending
  const failed = regionsQuery.isError || indicatorsQuery.isError

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Water Regions"
          description="Monthly GEE water indicators by province and district — satellite-derived, not simulated."
          icon={<MapPin className="h-6 w-6" />}
          action={
            rows.length ? (
              <Badge tone="sky">{rows.length} regions with data</Badge>
            ) : undefined
          }
        />

        {pending ? (
          <Spinner />
        ) : failed ? (
          <ErrorState
            onRetry={() => {
              regionsQuery.refetch()
              indicatorsQuery.refetch()
            }}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No indicator data yet"
            message="No region has real (GEE) indicator rows yet. Run the WAI pipeline to populate them."
          />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <KpiCard
                label="Regions with real data"
                value={rows.length}
                detail={latestMonth ? `Coverage through ${fmtMonth(latestMonth)}` : undefined}
                icon={MapPin}
              />
              <KpiCard
                label="Average WAI"
                value={avgWai != null ? fmtNumber(avgWai) : '—'}
                detail={latestMonth ? `Across listed regions · ${fmtMonth(latestMonth)}` : undefined}
                icon={Droplets}
                severity={avgWai != null ? (avgWai < 25 ? 'Critical' : avgWai < 40 ? 'Severe' : avgWai < 55 ? 'Stressed' : 'Normal') : undefined}
              />
              <KpiCard
                label="Open stress alerts"
                value={openAlerts}
                detail="Region-scoped WAI alerts (active)"
                icon={Bell}
                accent={openAlerts > 0 ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'}
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search region or code…"
                  className="w-64 rounded-lg border border-line bg-surface py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-subtle focus:border-brand focus:outline-none"
                />
              </div>
              <div className="flex rounded-lg border border-line bg-surface p-0.5">
                {(['all', 'province', 'district'] as TypeFilter[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTypeF(t)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                      typeF === t ? 'bg-brand-soft text-brand' : 'text-ink-muted hover:text-ink'
                    }`}
                  >
                    {t === 'all' ? 'All' : `${t}s`}
                  </button>
                ))}
              </div>
              <select
                value={sevF}
                onChange={(e) => setSevF(e.target.value as 'all' | SeverityLevel)}
                className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-brand focus:outline-none"
              >
                <option value="all">All severities</option>
                <option value="Critical">Critical</option>
                <option value="Severe">Severe</option>
                <option value="Stressed">Stressed</option>
                <option value="Moderate">Moderate</option>
                <option value="Normal">Normal</option>
              </select>
              <span className="text-caption text-ink-subtle">
                {filtered.length} of {rows.length} shown
              </span>
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                title="No regions match"
                message="Adjust the search or filters to see regions."
              />
            ) : (
              <>
                <RegionTable
                  title="Provinces"
                  rows={provinces}
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={toggleSort}
                />
                {districts.length > 0 && (
                  <RegionTable
                    title="Districts"
                    rows={districts}
                    sortKey={sortKey}
                    sortDir={sortDir}
                    onSort={toggleSort}
                  />
                )}
              </>
            )}

            <p className="text-[11px] text-ink-subtle">
              Source: Google Earth Engine — CHIRPS rainfall, ERA5-Land evapotranspiration, JRC
              water extent, Sentinel-2 NDVI. Rows flagged PARTIAL are inside the data-lag window.
              {withoutData > 0 && ` ${withoutData} region(s) hidden — no indicator data yet.`}
            </p>
          </>
        )}
      </div>
    </AppShell>
  )
}

function RegionTable({
  title,
  rows,
  sortKey,
  sortDir,
  onSort,
}: {
  title: string
  rows: RegionRow[]
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
}) {
  if (!rows.length) return null
  const openAlerts = rows.reduce((sum, r) => sum + r.openAlerts, 0)
  const arrow = (key: SortKey) => (sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '')

  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={`${rows.length} regions`}
        icon={<MapPin className="h-5 w-5" />}
        accent="bg-brand-soft text-brand"
        action={
          openAlerts > 0 ? (
            <Badge tone="amber">{openAlerts} open alerts</Badge>
          ) : (
            <Badge tone="emerald">no open alerts</Badge>
          )
        }
      />
      <CardBody className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-surface text-[11px] uppercase tracking-wider text-ink-subtle">
              <tr>
                <Th sortable onClick={() => onSort('name')} active={sortKey === 'name'} dir={sortDir}>
                  Region{arrow('name')}
                </Th>
                <Th>Latest month</Th>
                <Th sortable onClick={() => onSort('wai')} active={sortKey === 'wai'} dir={sortDir}>
                  WAI trend{arrow('wai')}
                </Th>
                <Th sortable onClick={() => onSort('severity')} active={sortKey === 'severity'} dir={sortDir}>
                  Severity{arrow('severity')}
                </Th>
                <Th>Rainfall anom.</Th>
                <Th>Quality</Th>
                <Th sortable onClick={() => onSort('alerts')} active={sortKey === 'alerts'} dir={sortDir}>
                  Alerts{arrow('alerts')}
                </Th>
                <Th>History</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((r) => (
                <tr key={r.id} className="text-ink-muted hover:bg-surface-alt">
                  <Td>
                    <Link href={`/water/regions/${r.id}`} className="font-medium text-ink hover:text-brand">
                      {r.name}
                    </Link>
                    {r.code && (
                      <span className="ml-2 rounded bg-surface-alt px-1.5 py-0.5 font-mono text-[10px] text-ink-subtle">
                        {r.code}
                      </span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-ink-muted">{fmtMonth(r.latestWeek)}</Td>
                  <Td>
                    <div className="flex items-center gap-3">
                      <span className="w-9 font-mono text-sm font-semibold tabular-nums text-ink">
                        {r.wai != null ? fmtNumber(r.wai) : '—'}
                      </span>
                      <Sparkline values={r.history} />
                    </div>
                  </Td>
                  <Td>{r.severity ? <SeverityBadge severity={r.severity} /> : '—'}</Td>
                  <Td className={`font-mono text-xs tabular-nums ${r.rainfallAnomaly != null && r.rainfallAnomaly < -30 ? 'text-warn' : ''}`}>
                    {r.rainfallAnomaly != null ? fmtPct(r.rainfallAnomaly, 0) : '—'}
                  </Td>
                  <Td>
                    {r.quality === 'VALID' ? (
                      <Badge tone="ok">VALID</Badge>
                    ) : r.quality === 'PARTIAL' ? (
                      <Badge tone="amber">PARTIAL</Badge>
                    ) : r.quality === 'STALE' ? (
                      <Badge tone="slate">STALE</Badge>
                    ) : (
                      <span className="text-[11px] text-ink-subtle">—</span>
                    )}
                  </Td>
                  <Td>
                    {r.openAlerts > 0 ? (
                      <Badge tone="amber">{r.openAlerts}</Badge>
                    ) : (
                      <span className="text-[11px] text-ink-subtle">0</span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap text-[11px] text-ink-subtle">
                    {r.months < 12 ? (
                      <Badge tone="slate">Since {fmtMonth(r.firstWeek)}</Badge>
                    ) : (
                      `${r.months} mo`
                    )}
                  </Td>
                  <Td className="text-right text-[11px] text-ink-subtle">
                    <Link href={`/water/regions/${r.id}`}>View →</Link>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  )
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="text-[11px] text-ink-subtle">—</span>
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const w = 96
  const h = 24
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w
      const y = h - 3 - ((v - min) / span) * (h - 6)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const lastY = h - 3 - ((values[values.length - 1] - min) / span) * (h - 6)
  return (
    <svg width={w} height={h} className="shrink-0 overflow-visible" aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke="#38bdf8"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={w} cy={lastY.toFixed(1)} r="2" fill="#38bdf8" />
    </svg>
  )
}

function Th({
  children,
  className,
  sortable,
  onClick,
  active,
  dir,
}: {
  children?: React.ReactNode
  className?: string
  sortable?: boolean
  onClick?: () => void
  active?: boolean
  dir?: SortDir
}) {
  return (
    <th
      className={`px-4 py-2.5 font-medium ${sortable ? 'cursor-pointer select-none hover:text-ink' : ''} ${active ? 'text-brand' : ''} ${className ?? ''}`}
      onClick={sortable ? onClick : undefined}
      aria-sort={sortable ? (active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none') : undefined}
    >
      {children}
    </th>
  )
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-2.5 text-xs ${className ?? ''}`}>{children}</td>
}
