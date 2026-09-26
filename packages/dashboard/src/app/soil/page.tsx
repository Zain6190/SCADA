// packages/dashboard/src/app/soil/page.tsx
'use client'

import Navigation from '@/components/shared/Navigation'
import { Sprout, AlertTriangle, Gauge, Droplets } from 'lucide-react'

export default function SoilPage() {
  return (
    <div className="min-h-screen bg-surface">
      <Navigation />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <h1 className="text-2xl font-bold text-ink">Soil Monitoring</h1>
        <p className="text-sm text-ink-subtle mb-6">Salinity Tracking & Land Degradation Monitoring</p>
        
        <div className="bg-white rounded-xl border border-line p-6 shadow-sm">
          <div className="flex items-center justify-center py-12">
            <div className="text-center text-ink-subtle">
              <Sprout className="w-16 h-16 mx-auto text-warn" />
              <p className="text-sm">Soil Health Dashboard</p>
              <p className="text-xs text-ink-muted">(Coming soon)</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}