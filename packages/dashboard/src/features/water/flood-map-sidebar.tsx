'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ChevronDown, ChevronUp, X, Layers, Activity, Gauge } from 'lucide-react'
import type { FloodTerritoryFeature, LayerState, RegionAlert } from './use-flood-map-state'

const TRAVEL_TIMES = [
  { color: '#ef4444', label: '0-6h', tag: 'Critical' },
  { color: '#f97316', label: '6-12h', tag: 'Urgent' },
  { color: '#eab308', label: '12-24h', tag: 'Warning' },
  { color: '#22c55e', label: '24-48h', tag: 'Watch' },
  { color: '#3b82f6', label: '48h+', tag: 'Advisory' },
]

const RIVER_COLORS: Record<string, string> = {
  Indus: '#38bdf8', Jhelum: '#34d399', Kabul: '#f59e0b', Chenab: '#a78bfa', Panjnad: '#f472b6',
}

const STATUS_LEVELS = [
  { color: '#ef4444', label: 'Critical', desc: 'Exceeds critical level' },
  { color: '#f97316', label: 'Danger', desc: 'Above danger threshold' },
  { color: '#eab308', label: 'Warning', desc: 'Exceeds warning level' },
  { color: '#22c55e', label: 'Normal', desc: 'Within safe range' },
]

const FLOOD_PROB = [
  { color: '#ef4444', label: '>50%', tag: 'Critical' },
  { color: '#f97316', label: '20-50%', tag: 'Elevated' },
  { color: '#22c55e', label: '<20%', tag: 'Low' },
]

const TERRITORY_SEVERITY = [
  { color: '#64748b', label: 'None' },
  { color: '#3b82f6', label: 'Low' },
  { color: '#f59e0b', label: 'Moderate' },
  { color: '#f97316', label: 'High' },
  { color: '#ef4444', label: 'Extreme' },
]

const SEVERITY_COLOR: Record<string, string> = {
  NONE: '#64748b',
  LOW: '#3b82f6',
  MODERATE: '#f59e0b',
  HIGH: '#f97316',
  EXTREME: '#ef4444',
  CRITICAL: '#ef4444',
}

function formatPeople(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1_000) return `${Math.round(count / 1_000)}k`
  return count.toLocaleString()
}

interface SidebarProps {
  timeSlider: number
  onTimeSliderChange: (v: number) => void
  showRivers: boolean
  showLabels: boolean
  showWarnings: boolean
  showImpact: boolean
  showRainfall: boolean
  showFloodExtents: boolean
  showTerritories: boolean
  onToggleLayer: (layer: keyof LayerState) => void
  regionAlerts: RegionAlert[]
  alertedPopulation: number
  selectedDistrict?: string | null
  selectedTerritory?: FloodTerritoryFeature | null
  onSelectDistrict?: (district: string | null) => void
  totalPopulation: number
  totalBridges: number
  totalHospitals: number
  visibleSegments: number
  totalSegments: number
  selectedAssetId?: number | null
  impactSummary?: any
  calculating?: boolean
  onClearSelection?: () => void
  simAssetId: number
  simFlow: number
  onSimAssetChange: (id: number) => void
  onSimFlowChange: (flow: number) => void
  simImpact: any
  assetNames: Record<number, string>
}

function Section({ title, icon, children, defaultOpen = true }: { title: string; icon: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-line last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-[11px] uppercase tracking-wider text-ink-muted hover:text-ink transition-colors"
      >
        <span className="flex items-center gap-2 font-medium">{icon}{title}</span>
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
      {open && <div className="px-4 pb-3">{children}</div>}
    </div>
  )
}

export function FloodMapSidebar({
  timeSlider, onTimeSliderChange,
  showRivers, showLabels, showWarnings, showImpact, showRainfall, showFloodExtents, showTerritories,
  onToggleLayer,
  regionAlerts, alertedPopulation, selectedDistrict, selectedTerritory, onSelectDistrict,
  totalPopulation, totalBridges, totalHospitals, visibleSegments, totalSegments,
  selectedAssetId, impactSummary, calculating, onClearSelection,
  simAssetId, simFlow, onSimAssetChange, onSimFlowChange, simImpact,
  assetNames,
}: SidebarProps) {
  const layers: { key: keyof LayerState; label: string; state: boolean }[] = [
    { key: 'showTerritories', label: 'Danger zones', state: showTerritories },
    { key: 'showRivers', label: 'River Geometry', state: showRivers },
    { key: 'showLabels', label: 'Asset Labels', state: showLabels },
    { key: 'showWarnings', label: 'FFD Warnings', state: showWarnings },
    { key: 'showImpact', label: 'Impact Assets', state: showImpact },
    { key: 'showRainfall', label: 'FFD Stations', state: showRainfall },
    { key: 'showFloodExtents', label: 'Flood Extents', state: showFloodExtents },
  ]

  return (
    <div className="flood-sidebar flex flex-col h-full bg-canvas border-l border-line overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-line bg-surface">
        <h3 className="text-xs font-semibold text-ink flex items-center gap-2">
          <svg className="h-3.5 w-3.5 text-brand" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
          Map Controls
        </h3>
        {selectedAssetId && onClearSelection && (
          <button
            onClick={onClearSelection}
            className="flex items-center gap-1 rounded-md bg-brand-soft px-2 py-1 text-[10px] text-brand hover:bg-brand-soft hover:text-brand transition-colors"
          >
            <X className="h-3 w-3" /> Back to Overview
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <Section title="Layers" icon={<Layers className="h-3 w-3" />} defaultOpen={true}>
          <div className="space-y-1">
            {layers.map((l) => (
              <label key={l.key} className="flex items-center gap-2.5 py-1 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={l.state}
                  onChange={() => onToggleLayer(l.key)}
                  className="h-3.5 w-3.5 rounded border-line-strong bg-surface-alt text-brand focus:ring-brand/25"
                />
                <span className="text-[11px] text-ink-muted group-hover:text-ink transition-colors">{l.label}</span>
              </label>
            ))}
          </div>
        </Section>

        <Section title="Travel Time" icon={<Activity className="h-3 w-3" />} defaultOpen={true}>
          <div className="space-y-1.5">
            {TRAVEL_TIMES.map((t) => (
              <div key={t.label} className="flex items-center gap-2">
                <div className="w-6 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: t.color }} />
                <span className="text-[11px] text-ink-muted flex-1">{t.label}</span>
                <span className="text-[9px] text-ink-subtle bg-surface-alt rounded px-1.5 py-0.5">{t.tag}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Status Severity" icon={<Gauge className="h-3 w-3" />} defaultOpen={true}>
          <div className="space-y-1.5">
            {STATUS_LEVELS.map((s) => (
              <div key={s.label} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                <div className="flex-1 min-w-0">
                  <span className="text-[11px] text-ink-muted">{s.label}</span>
                  <p className="text-[9px] text-ink-subtle truncate">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Flood Probability" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M2 12h20"/></svg>} defaultOpen={true}>
          <div className="space-y-1.5">
            {FLOOD_PROB.map((f) => (
              <div key={f.label} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: f.color }} />
                <span className="text-[11px] text-ink-muted flex-1">{f.label}</span>
                <span className="text-[9px] text-ink-subtle bg-surface-alt rounded px-1.5 py-0.5">{f.tag}</span>
              </div>
            ))}
          </div>
          <p className="text-[9px] text-ink-subtle mt-2">XGBoost (Tarbela/Mangla) or threshold fallback</p>
        </Section>

        <Section title="Rivers" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/></svg>} defaultOpen={false}>
          <div className="space-y-1.5">
            {Object.entries(RIVER_COLORS).map(([name, color]) => (
              <div key={name} className="flex items-center gap-2">
                <div className="w-6 h-1 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span className="text-[11px] text-ink-muted">{name}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Asset Types" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="10" r="3"/><path d="M12 21.7C17.3 17 20 13 20 10a8 8 0 1 0-16 0c0 3 2.7 7 8 11.7z"/></svg>} defaultOpen={false}>
          <div className="space-y-1.5">
            {[{ color: '#94a3b8', label: 'Dam' }, { color: '#f59e0b', label: 'Barrage' }, { color: '#a78bfa', label: 'Headworks' }].map((a) => (
              <div key={a.label} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: a.color }} />
                <span className="text-[11px] text-ink-muted">{a.label}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Region alerts" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>} defaultOpen={true}>
          <div className="mb-2 flex flex-wrap gap-x-2 gap-y-1">
            {TERRITORY_SEVERITY.map((item) => (
              <span key={item.label} className="flex items-center gap-1 text-[9px] text-slate-500">
                <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
          {regionAlerts.length === 0 ? (
            <p className="text-[11px] text-slate-500">No danger zones. A district is marked when its flood prediction reaches moderate severity.</p>
          ) : (
            <div className="space-y-1.5">
              {regionAlerts.map((alert) => {
                const active = selectedDistrict === alert.district
                const color = SEVERITY_COLOR[alert.severity] || '#f59e0b'
                return (
                  <button
                    key={alert.district}
                    type="button"
                    onClick={() => onSelectDistrict?.(alert.district)}
                    className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${active ? 'border-sky-500/50 bg-sky-500/10' : 'border-slate-800 bg-slate-900/80 hover:border-slate-700'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-semibold text-slate-100">{alert.district}</span>
                      <span className="text-[9px] font-medium" style={{ color }}>{alert.severity}</span>
                    </div>
                    <p className="text-[10px] text-amber-400 mt-0.5">{formatPeople(alert.population_exposed)} people</p>
                    <p className="text-[9px] text-slate-500 truncate">
                      {alert.inside_count ?? alert.inside?.length ?? 0} places inside · {alert.bridges} bridges · {alert.hospitals} hospitals
                    </p>
                  </button>
                )
              })}
            </div>
          )}
        </Section>

        {selectedTerritory && (
          <Section title="Region impact" icon={<Activity className="h-3 w-3" />} defaultOpen={true}>
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold text-white">{selectedTerritory.properties.district}</p>
                  <p className="text-[10px] text-slate-500">{selectedTerritory.properties.province}</p>
                </div>
                {onSelectDistrict && (
                  <button
                    type="button"
                    onClick={() => onSelectDistrict(null)}
                    className="text-[10px] text-slate-500 hover:text-slate-300"
                  >
                    Clear
                  </button>
                )}
              </div>
              <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-3 py-2">
                <p className="text-[9px] uppercase tracking-wider text-slate-500">Prediction</p>
                <p className="text-xs font-semibold" style={{ color: SEVERITY_COLOR[selectedTerritory.properties.flood_severity] || '#e2e8f0' }}>
                  {selectedTerritory.properties.flood_severity} · {Math.round((selectedTerritory.properties.flood_probability || 0) * 100)}%
                </p>
              </div>
              <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-3 py-2">
                <p className="text-[9px] uppercase tracking-wider text-slate-500 mb-1">Population exposed</p>
                <p className="text-lg font-bold text-amber-400">{(selectedTerritory.properties.population_exposed || 0).toLocaleString()}</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-2 py-1.5 text-center">
                  <p className="text-[9px] text-slate-500">Bridges</p>
                  <p className="text-xs font-semibold text-slate-200">{selectedTerritory.properties.bridges}</p>
                </div>
                <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-2 py-1.5 text-center">
                  <p className="text-[9px] text-slate-500">Hospitals</p>
                  <p className="text-xs font-semibold text-slate-200">{selectedTerritory.properties.hospitals}</p>
                </div>
              </div>
              {selectedTerritory.properties.recommendation && (
                <p className="text-[11px] text-slate-300">{selectedTerritory.properties.recommendation}</p>
              )}
              <p className="text-[10px] text-slate-500">
                Source: {selectedTerritory.properties.source_asset_name}
                {selectedTerritory.properties.ot_source === 'SOFT_OT_SCENARIO' ? ' · scenario discharge' : ''}
              </p>
              {selectedTerritory.properties.source_asset_id ? (
                <Link
                  href={`/water/ot?asset=${selectedTerritory.properties.source_asset_id}`}
                  className="text-[11px] text-sky-300 hover:underline"
                >
                  Open {selectedTerritory.properties.ot_device_code || 'Soft OT'} for this district
                </Link>
              ) : null}
              {(selectedTerritory.properties.inside || []).length > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="text-[9px] uppercase tracking-wider text-slate-500">Inside this zone</p>
                  {selectedTerritory.properties.inside!.map((place) => (
                    <div key={`${place.kind}-${place.name}`} className="flex items-center justify-between gap-2">
                      <span className="text-[11px] text-slate-200 truncate">{place.name}</span>
                      <span className="text-[9px] uppercase text-slate-500">{place.kind}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Section>
        )}

        <Section title="Visible Summary" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>} defaultOpen={true}>
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <span className="text-[11px] text-ink-muted">Population at Risk</span>
              <span className="text-[11px] font-semibold text-warn">{(totalPopulation / 1000000).toFixed(1)}M</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-slate-400">Alerted population</span>
              <span className="text-[11px] font-semibold text-red-400">{formatPeople(alertedPopulation)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-ink-muted">Bridges</span>
              <span className="text-[11px] font-semibold text-ink">{totalBridges}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-ink-muted">Hospitals</span>
              <span className="text-[11px] font-semibold text-ink">{totalHospitals}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-ink-muted">Segments Visible</span>
              <span className="text-[11px] font-semibold text-brand">{visibleSegments} / {totalSegments}</span>
            </div>
          </div>
        </Section>

        {selectedAssetId && (
          <Section title="Impact Analysis" icon={<Activity className="h-3 w-3" />} defaultOpen={true}>
            {calculating ? (
              <p className="text-[11px] text-ink-muted animate-pulse">Calculating downstream impact...</p>
            ) : impactSummary ? (
              <div className="space-y-2">
                <div className="rounded-lg bg-brand-soft border border-brand/25 px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wider text-ink-subtle mb-1">Source</p>
                  <p className="text-xs font-semibold text-white">{impactSummary.source_asset}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-surface border border-line px-3 py-2">
                    <p className="text-[9px] uppercase tracking-wider text-ink-subtle">Flow</p>
                    <p className="text-[11px] font-semibold text-brand">{impactSummary.release_flow_cusecs?.toLocaleString()} cusecs</p>
                  </div>
                  <div className="rounded-lg bg-surface border border-line px-3 py-2">
                    <p className="text-[9px] uppercase tracking-wider text-ink-subtle">Travel</p>
                    <p className="text-[11px] font-semibold text-brand">{impactSummary.total_travel_hours?.toFixed(1)}h</p>
                  </div>
                </div>
                <div className="rounded-lg bg-surface border border-line px-3 py-2">
                  <p className="text-[9px] uppercase tracking-wider text-ink-subtle mb-1">Population Exposed</p>
                  <p className="text-lg font-bold text-warn">{(impactSummary.total_population_exposed / 1000000).toFixed(1)}M</p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-lg bg-surface border border-line px-2 py-1.5 text-center">
                    <p className="text-[9px] text-ink-subtle">Bridges</p>
                    <p className="text-xs font-semibold text-ink">{impactSummary.total_bridges}</p>
                  </div>
                  <div className="rounded-lg bg-surface border border-line px-2 py-1.5 text-center">
                    <p className="text-[9px] text-ink-subtle">Hospitals</p>
                    <p className="text-xs font-semibold text-ink">{impactSummary.total_hospitals}</p>
                  </div>
                  <div className="rounded-lg bg-surface border border-line px-2 py-1.5 text-center">
                    <p className="text-[9px] text-ink-subtle">Segments</p>
                    <p className="text-xs font-semibold text-ink">{impactSummary.segments?.length}</p>
                  </div>
                </div>
                <div className="rounded-lg bg-surface border border-line px-3 py-2">
                  <p className="text-[9px] uppercase tracking-wider text-ink-subtle">Furthest Asset</p>
                  <p className="text-xs font-semibold text-brand">{impactSummary.furthest_asset}</p>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-ink-subtle">No impact data</p>
            )}
          </Section>
        )}

        <Section title="Scenario Simulation" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20V10M18 20V4M6 20v-4"/></svg>} defaultOpen={false}>
          <div className="space-y-2">
            <div>
              <label className="text-[10px] text-ink-subtle block mb-0.5">Source Asset</label>
              <select
                value={simAssetId}
                onChange={(e) => onSimAssetChange(Number(e.target.value))}
                className="w-full rounded-lg border border-line-strong bg-surface-alt px-2 py-1.5 text-[11px] text-white focus:outline-none focus:ring-1 focus:ring-brand/25"
              >
                {Object.entries(assetNames).map(([id, name]) => (
                  <option key={id} value={id}>{name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-ink-subtle block mb-0.5">Flow (cusecs)</label>
              <input
                type="number"
                value={simFlow}
                onChange={(e) => onSimFlowChange(Number(e.target.value))}
                className="w-full rounded-lg border border-line-strong bg-surface-alt px-2 py-1.5 text-[11px] text-white focus:outline-none focus:ring-1 focus:ring-brand/25"
              />
            </div>
            {simImpact && (
              <div className="mt-2 pt-2 border-t border-line space-y-1">
                <p className="text-[10px] text-ink-subtle uppercase tracking-wider font-medium">Estimated Impact</p>
                <div className="flex justify-between"><span className="text-[11px] text-ink-muted">Segments</span><span className="text-[11px] font-semibold text-white">{simImpact.segments}</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-ink-muted">Population</span><span className="text-[11px] font-semibold text-warn">{(simImpact.population / 1000000).toFixed(1)}M</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-ink-muted">Bridges</span><span className="text-[11px] font-semibold text-white">{simImpact.bridges}</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-ink-muted">Hospitals</span><span className="text-[11px] font-semibold text-white">{simImpact.hospitals}</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-ink-muted">Max Travel</span><span className="text-[11px] font-semibold text-brand">{simImpact.maxTravel.toFixed(1)}h</span></div>
              </div>
            )}
          </div>
        </Section>

        <Section title="Forecast Window" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>} defaultOpen={false}>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-ink-subtle">Visible forecast</span>
              <span className="text-xs font-semibold text-brand">{timeSlider}h</span>
            </div>
            <input
              type="range"
              min={0}
              max={72}
              value={timeSlider}
              onChange={(e) => onTimeSliderChange(Number(e.target.value))}
              className="flood-slider w-full"
            />
            <div className="flex justify-between text-[9px] text-ink-subtle mt-1">
              <span>0h</span><span>12h</span><span>24h</span><span>48h</span><span>72h</span>
            </div>
          </div>
        </Section>
      </div>
    </div>
  )
}
