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
    { label: 'Drought Severity', value: 'Moderate', change: '+2%', icon: AlertTriangle, color: 'text-yellow-500', bg: 'bg-yellow-50' },
    { label: 'Flood Risk', value: 'Low', change: '-5%', icon: Droplets, color: 'text-green-500', bg: 'bg-green-50' },
    { label: 'Vegetation Health', value: 'Good', change: '+8%', icon: TrendingUp, color: 'text-emerald-500', bg: 'bg-emerald-50' },
    { label: 'Tehsils Monitored', value: '148', change: '', icon: Map, color: 'text-blue-500', bg: 'bg-blue-50' },
  ]

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">GeoVision AI</h1>
            <p className="text-sm text-gray-500">AI-Powered Remote Sensing Platform</p>
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
            <RefreshCw className="w-4 h-4" />
            Refresh Data
          </button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {stats.map((stat, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200/50 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <div className={`${stat.bg} p-2 rounded-lg`}>
                  <stat.icon className={`w-5 h-5 ${stat.color}`} />
                </div>
                {stat.change && (
                  <span className={`text-xs font-medium ${stat.change.startsWith('+') ? 'text-green-500' : 'text-red-500'}`}>
                    {stat.change}
                  </span>
                )}
              </div>
              <div className="mt-3">
                <div className="text-2xl font-bold text-gray-900">{stat.value}</div>
                <div className="text-xs text-gray-500">{stat.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Main Content - Map + Predictions */}
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Map Section */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200/50 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">Drought Severity Map</h3>
              <select 
                className="text-sm border border-gray-200 rounded-lg px-3 py-1 bg-white"
                value={selectedTehsil}
                onChange={(e) => setSelectedTehsil(e.target.value)}
              >
                <option value="All">All Tehsils</option>
                <option value="Lahore">Lahore</option>
                <option value="Multan">Multan</option>
                <option value="Faisalabad">Faisalabad</option>
              </select>
            </div>
            <div className="h-80 bg-gradient-to-br from-gray-100 to-gray-200 rounded-lg flex items-center justify-center">
              <div className="text-center text-gray-500">
                <Map className="w-12 h-12 mx-auto text-gray-300" />
                <p className="text-sm">Drought Map Visualization</p>
                <p className="text-xs text-gray-400">(Map component coming soon)</p>
              </div>
            </div>
          </div>

          {/* Prediction Panel */}
          <div className="bg-white rounded-xl border border-gray-200/50 p-4 shadow-sm">
            <h3 className="font-semibold text-gray-900 mb-4">Predictions</h3>
            <div className="space-y-3">
              {[
                { tehsil: 'Lahore', severity: 'Moderate', score: 65, color: 'bg-yellow-500' },
                { tehsil: 'Multan', severity: 'Severe', score: 25, color: 'bg-red-500' },
                { tehsil: 'Faisalabad', severity: 'Normal', score: 85, color: 'bg-green-500' },
              ].map((item, i) => (
                <div key={i} className="p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-gray-900">{item.tehsil}</span>
                    <span className={`text-sm font-medium ${item.severity === 'Severe' ? 'text-red-500' : item.severity === 'Moderate' ? 'text-yellow-500' : 'text-green-500'}`}>
                      {item.severity}
                    </span>
                  </div>
                  <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div className={`h-full ${item.color} rounded-full transition-all`} style={{ width: `${item.score}%` }}></div>
                  </div>
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
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