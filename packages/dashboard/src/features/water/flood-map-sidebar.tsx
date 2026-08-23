'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, X, Layers, Activity, Gauge } from 'lucide-react'

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

interface SidebarProps {
  timeSlider: number
  onTimeSliderChange: (v: number) => void
  showRivers: boolean
  showLabels: boolean
  showWarnings: boolean
  showImpact: boolean
  showRainfall: boolean
  showFloodExtents: boolean
  onToggleLayer: (layer: string) => void
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
    <div className="border-b border-slate-800/60 last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-[11px] uppercase tracking-wider text-slate-400 hover:text-slate-200 transition-colors"
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
  showRivers, showLabels, showWarnings, showImpact, showRainfall, showFloodExtents,
  onToggleLayer,
  totalPopulation, totalBridges, totalHospitals, visibleSegments, totalSegments,
  selectedAssetId, impactSummary, calculating, onClearSelection,
  simAssetId, simFlow, onSimAssetChange, onSimFlowChange, simImpact,
  assetNames,
}: SidebarProps) {
  const layers = [
    { key: 'rivers', label: 'River Geometry', state: showRivers },
    { key: 'labels', label: 'Asset Labels', state: showLabels },
    { key: 'warnings', label: 'FFD Warnings', state: showWarnings },
    { key: 'impact', label: 'Impact Assets', state: showImpact },
    { key: 'rainfall', label: 'FFD Stations', state: showRainfall },
    { key: 'floodExtents', label: 'Flood Extents', state: showFloodExtents },
  ]

  return (
    <div className="flood-sidebar flex flex-col h-full bg-slate-950 border-l border-slate-800/60 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/60 bg-slate-900/50">
        <h3 className="text-xs font-semibold text-slate-200 flex items-center gap-2">
          <svg className="h-3.5 w-3.5 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
          Map Controls
        </h3>
        {selectedAssetId && onClearSelection && (
          <button
            onClick={onClearSelection}
            className="flex items-center gap-1 rounded-md bg-sky-500/10 px-2 py-1 text-[10px] text-sky-400 hover:bg-sky-500/20 hover:text-sky-300 transition-colors"
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
                  className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500"
                />
                <span className="text-[11px] text-slate-400 group-hover:text-slate-200 transition-colors">{l.label}</span>
              </label>
            ))}
          </div>
        </Section>

        <Section title="Travel Time" icon={<Activity className="h-3 w-3" />} defaultOpen={true}>
          <div className="space-y-1.5">
            {TRAVEL_TIMES.map((t) => (
              <div key={t.label} className="flex items-center gap-2">
                <div className="w-6 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: t.color }} />
                <span className="text-[11px] text-slate-300 flex-1">{t.label}</span>
                <span className="text-[9px] text-slate-500 bg-slate-800/60 rounded px-1.5 py-0.5">{t.tag}</span>
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
                  <span className="text-[11px] text-slate-300">{s.label}</span>
                  <p className="text-[9px] text-slate-500 truncate">{s.desc}</p>
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
                <span className="text-[11px] text-slate-300 flex-1">{f.label}</span>
                <span className="text-[9px] text-slate-500 bg-slate-800/60 rounded px-1.5 py-0.5">{f.tag}</span>
              </div>
            ))}
          </div>
          <p className="text-[9px] text-slate-500 mt-2">XGBoost (Tarbela/Mangla) or threshold fallback</p>
        </Section>

        <Section title="Rivers" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/></svg>} defaultOpen={false}>
          <div className="space-y-1.5">
            {Object.entries(RIVER_COLORS).map(([name, color]) => (
              <div key={name} className="flex items-center gap-2">
                <div className="w-6 h-1 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span className="text-[11px] text-slate-300">{name}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Asset Types" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="10" r="3"/><path d="M12 21.7C17.3 17 20 13 20 10a8 8 0 1 0-16 0c0 3 2.7 7 8 11.7z"/></svg>} defaultOpen={false}>
          <div className="space-y-1.5">
            {[{ color: '#94a3b8', label: 'Dam' }, { color: '#f59e0b', label: 'Barrage' }, { color: '#a78bfa', label: 'Headworks' }].map((a) => (
              <div key={a.label} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: a.color }} />
                <span className="text-[11px] text-slate-300">{a.label}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Visible Summary" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>} defaultOpen={true}>
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <span className="text-[11px] text-slate-400">Population at Risk</span>
              <span className="text-[11px] font-semibold text-amber-400">{(totalPopulation / 1000000).toFixed(1)}M</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-slate-400">Bridges</span>
              <span className="text-[11px] font-semibold text-slate-200">{totalBridges}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-slate-400">Hospitals</span>
              <span className="text-[11px] font-semibold text-slate-200">{totalHospitals}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[11px] text-slate-400">Segments Visible</span>
              <span className="text-[11px] font-semibold text-sky-400">{visibleSegments} / {totalSegments}</span>
            </div>
          </div>
        </Section>

        {selectedAssetId && (
          <Section title="Impact Analysis" icon={<Activity className="h-3 w-3" />} defaultOpen={true}>
            {calculating ? (
              <p className="text-[11px] text-slate-400 animate-pulse">Calculating downstream impact...</p>
            ) : impactSummary ? (
              <div className="space-y-2">
                <div className="rounded-lg bg-sky-500/5 border border-sky-500/20 px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Source</p>
                  <p className="text-xs font-semibold text-white">{impactSummary.source_asset}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-3 py-2">
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">Flow</p>
                    <p className="text-[11px] font-semibold text-sky-400">{impactSummary.release_flow_cusecs?.toLocaleString()} cusecs</p>
                  </div>
                  <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-3 py-2">
                    <p className="text-[9px] uppercase tracking-wider text-slate-500">Travel</p>
                    <p className="text-[11px] font-semibold text-sky-400">{impactSummary.total_travel_hours?.toFixed(1)}h</p>
                  </div>
                </div>
                <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-3 py-2">
                  <p className="text-[9px] uppercase tracking-wider text-slate-500 mb-1">Population Exposed</p>
                  <p className="text-lg font-bold text-amber-400">{(impactSummary.total_population_exposed / 1000000).toFixed(1)}M</p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-2 py-1.5 text-center">
                    <p className="text-[9px] text-slate-500">Bridges</p>
                    <p className="text-xs font-semibold text-slate-200">{impactSummary.total_bridges}</p>
                  </div>
                  <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-2 py-1.5 text-center">
                    <p className="text-[9px] text-slate-500">Hospitals</p>
                    <p className="text-xs font-semibold text-slate-200">{impactSummary.total_hospitals}</p>
                  </div>
                  <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-2 py-1.5 text-center">
                    <p className="text-[9px] text-slate-500">Segments</p>
                    <p className="text-xs font-semibold text-slate-200">{impactSummary.segments?.length}</p>
                  </div>
                </div>
                <div className="rounded-lg bg-slate-900/80 border border-slate-800 px-3 py-2">
                  <p className="text-[9px] uppercase tracking-wider text-slate-500">Furthest Asset</p>
                  <p className="text-xs font-semibold text-sky-400">{impactSummary.furthest_asset}</p>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-slate-500">No impact data</p>
            )}
          </Section>
        )}

        <Section title="Scenario Simulation" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20V10M18 20V4M6 20v-4"/></svg>} defaultOpen={false}>
          <div className="space-y-2">
            <div>
              <label className="text-[10px] text-slate-500 block mb-0.5">Source Asset</label>
              <select
                value={simAssetId}
                onChange={(e) => onSimAssetChange(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-[11px] text-white focus:outline-none focus:ring-1 focus:ring-sky-500"
              >
                {Object.entries(assetNames).map(([id, name]) => (
                  <option key={id} value={id}>{name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-slate-500 block mb-0.5">Flow (cusecs)</label>
              <input
                type="number"
                value={simFlow}
                onChange={(e) => onSimFlowChange(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-[11px] text-white focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>
            {simImpact && (
              <div className="mt-2 pt-2 border-t border-slate-800 space-y-1">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Estimated Impact</p>
                <div className="flex justify-between"><span className="text-[11px] text-slate-400">Segments</span><span className="text-[11px] font-semibold text-white">{simImpact.segments}</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-slate-400">Population</span><span className="text-[11px] font-semibold text-amber-400">{(simImpact.population / 1000000).toFixed(1)}M</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-slate-400">Bridges</span><span className="text-[11px] font-semibold text-white">{simImpact.bridges}</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-slate-400">Hospitals</span><span className="text-[11px] font-semibold text-white">{simImpact.hospitals}</span></div>
                <div className="flex justify-between"><span className="text-[11px] text-slate-400">Max Travel</span><span className="text-[11px] font-semibold text-sky-400">{simImpact.maxTravel.toFixed(1)}h</span></div>
              </div>
            )}
          </div>
        </Section>

        <Section title="Forecast Window" icon={<svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>} defaultOpen={false}>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-slate-500">Visible forecast</span>
              <span className="text-xs font-semibold text-sky-400">{timeSlider}h</span>
            </div>
            <input
              type="range"
              min={0}
              max={72}
              value={timeSlider}
              onChange={(e) => onTimeSliderChange(Number(e.target.value))}
              className="flood-slider w-full"
            />
            <div className="flex justify-between text-[9px] text-slate-500 mt-1">
              <span>0h</span><span>12h</span><span>24h</span><span>48h</span><span>72h</span>
            </div>
          </div>
        </Section>
      </div>
    </div>
  )
}
