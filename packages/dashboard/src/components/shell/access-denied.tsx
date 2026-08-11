// packages/dashboard/src/components/shell/access-denied.tsx
'use client'

import Link from 'next/link'
import { ShieldAlert, ArrowLeft } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { moduleForPath, type NavSectionId } from '@/lib/navigation'
import { ALL_MODULES } from '@/lib/rbac'

const SECTION_LABEL: Record<NavSectionId, string> = {
  command: 'Command Center',
  aqua: 'AquaVision',
  crop: 'Crop Yield',
  geo: 'GeoVision',
  system: 'System',
}

export function AccessDenied({
  module,
  pathname,
}: {
  module: NavSectionId
  pathname: string
}) {
  const label = SECTION_LABEL[module] ?? module
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <Card className="max-w-md p-8 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 text-red-400">
          <ShieldAlert className="h-8 w-8" />
        </div>
        <h2 className="mt-5 text-xl font-semibold text-slate-100">Access Restricted</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Your current role does not grant access to the{' '}
          <span className="font-semibold text-slate-300">{label}</span> portal
          ({pathname}).
        </p>
        <div className="mt-4 flex justify-center">
          <Badge tone="red">Role-based access control</Badge>
        </div>
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700/60"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Command Center
        </Link>
      </Card>
    </div>
  )
}

export { ALL_MODULES }