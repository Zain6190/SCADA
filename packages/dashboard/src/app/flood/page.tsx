//  path  packages/dashboard/src/app/flood/page.tsx
'use client'

import Navigation from '@/components/shared/Navigation'
import { Droplets, AlertTriangle, Clock, Radio, Gauge } from 'lucide-react'

export default function FloodPage() {
  return (
    <div className="min-h-screen bg-surface">
      <Navigation />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <h1 className="text-2xl font-bold text-ink">Flood SCADA</h1>
        <p className="text-sm text-ink-subtle mb-6">Automated Barrage Gate Control & Flood Diversion</p>
        
        <div className="bg-white rounded-xl border border-line p-6 shadow-sm">
          <div className="flex items-center justify-center py-12">
            <div className="text-center text-ink-subtle">
              <Droplets className="w-16 h-16 mx-auto text-brand" />
              <p className="text-sm">Flood Monitoring Dashboard</p>
              <p className="text-xs text-ink-muted">(Coming soon)</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}