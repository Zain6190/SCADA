// packages/dashboard/src/app/access-pending/page.tsx
// Access-request status: the account exists but portal access awaits approval.
'use client'

import Link from 'next/link'
import { Hourglass, LogIn } from 'lucide-react'

export default function AccessPendingPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 text-ink">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center shadow-2xl">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-warn-soft text-warn">
          <Hourglass className="h-8 w-8" />
        </div>
        <h1 className="mt-5 text-xl font-semibold text-ink">Access Pending</h1>
        <p className="mt-2 text-sm leading-6 text-ink-muted">
          Your account exists but portal access has not been granted yet. An
          administrator will review your request. You will be able to sign in
          once your access is approved.
        </p>
        <Link
          href="/login"
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-line-strong bg-surface-alt px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface-alt"
        >
          <LogIn className="h-4 w-4" /> Back to Login
        </Link>
      </div>
    </div>
  )
}