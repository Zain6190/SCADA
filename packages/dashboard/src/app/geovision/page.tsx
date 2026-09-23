// packages/dashboard/src/app/geovision/page.tsx
'use client'

import Navigation from '@/components/shared/Navigation'
import { 
  Map, 
  TrendingUp, 
  AlertTriangle, 
  Droplets,
  Activity,
  CloudRain,
  Thermometer,
  RefreshCw
} from 'lucide-react'
import { useState } from 'react'

export default function GeoVisionPage() {
  const [selectedTehsil, setSelectedTehsil] = useState('All')

  const stats = [
    { label: 'Drought Severity', value: 'Moderate', change: '+2%', icon: AlertTriangle, color: 'text-warn', bg: 'bg-warn-soft' },
    { label: 'Flood Risk', value: 'Low', change: '-5%', icon: Droplets, color: 'text-ok', bg: 'bg-ok-soft' },
    { label: 'Vegetation Health', value: 'Good', change: '+8%', icon: TrendingUp, color: 'text-ok', bg: 'bg-ok-soft' },
    { label: 'Tehsils Monitored', value: '148', change: '', icon: Map, color: 'text-brand', bg: 'bg-brand-soft' },
  ]

  return (
    <div className="min-h-screen bg-surface">
      <Navigation />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-ink">GeoVision AI</h1>
            <p className="text-sm text-ink-subtle">AI-Powered Remote Sensing Platform</p>
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-brand text-white rounded-lg text-sm font-medium hover:bg-brand transition-colors shadow-sm">
            <RefreshCw className="w-4 h-4" />
            Refresh Data
          </button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {stats.map((stat, i) => (
            <div key={i} className="bg-white rounded-xl border border-line p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <div className={`${stat.bg} p-2 rounded-lg`}>
                  <stat.icon className={`w-5 h-5 ${stat.color}`} />
                </div>
                {stat.change && (
                  <span className={`text-xs font-medium ${stat.change.startsWith('+') ? 'text-ok' : 'text-crit'}`}>
                    {stat.change}
                  </span>
                )}
              </div>
              <div className="mt-3">
                <div className="text-2xl font-bold text-ink">{stat.value}</div>
                <div className="text-xs text-ink-subtle">{stat.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Main Content - Map + Predictions */}
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Map Section */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-line p-4 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-ink">Drought Severity Map</h3>
              <select 
                className="text-sm border border-line rounded-lg px-3 py-1 bg-white"
                value={selectedTehsil}
                onChange={(e) => setSelectedTehsil(e.target.value)}
              >
                <option value="All">All Tehsils</option>
                <option value="Lahore">Lahore</option>
                <option value="Multan">Multan</option>
                <option value="Faisalabad">Faisalabad</option>
              </select>
            </div>
            <div className="h-80 bg-surface-alt rounded-lg flex items-center justify-center">
              <div className="text-center text-ink-subtle">
                <Map className="w-12 h-12 mx-auto text-ink-muted" />
                <p className="text-sm">Drought Map Visualization</p>
                <p className="text-xs text-ink-muted">(Map component coming soon)</p>
              </div>
            </div>
          </div>

          {/* Prediction Panel */}
          <div className="bg-white rounded-xl border border-line p-4 shadow-sm">
            <h3 className="font-semibold text-ink mb-4">Predictions</h3>
            <div className="space-y-3">
              {[
                { tehsil: 'Lahore', severity: 'Moderate', score: 65, color: 'bg-warn' },
                { tehsil: 'Multan', severity: 'Severe', score: 25, color: 'bg-crit' },
                { tehsil: 'Faisalabad', severity: 'Normal', score: 85, color: 'bg-ok' },
              ].map((item, i) => (
                <div key={i} className="p-3 bg-surface rounded-lg">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-ink">{item.tehsil}</span>
                    <span className={`text-sm font-medium ${item.severity === 'Severe' ? 'text-crit' : item.severity === 'Moderate' ? 'text-warn' : 'text-ok'}`}>
                      {item.severity}
                    </span>
                  </div>
                  <div className="mt-2 h-2 bg-surface-alt rounded-full overflow-hidden">
                    <div className={`h-full ${item.color} rounded-full transition-all`} style={{ width: `${item.score}%` }}></div>
                  </div>
                  <div className="flex justify-between text-xs text-ink-subtle mt-1">
                    <span>Score: {item.score}%</span>
                    <span>{item.severity}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}