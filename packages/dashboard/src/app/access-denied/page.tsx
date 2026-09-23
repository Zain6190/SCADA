// packages/dashboard/src/app/access-denied/page.tsx
// Access-denied screen as a standalone route.
'use client'

import Link from 'next/link'
import { ShieldAlert, ArrowLeft } from 'lucide-react'

export default function AccessDeniedPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 text-ink">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center shadow-2xl">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-crit-soft text-crit">
          <ShieldAlert className="h-8 w-8" />
        </div>
        <h1 className="mt-5 text-xl font-semibold text-ink">Access Restricted</h1>
        <p className="mt-2 text-sm leading-6 text-ink-muted">
          Your current access does not grant entry to this area. Use the Command
          Center to reach a portal you have access to.
        </p>
        <Link
          href="/portal"
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface-alt px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface-alt"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Command Center
        </Link>
      </div>
    </div>
  )
}