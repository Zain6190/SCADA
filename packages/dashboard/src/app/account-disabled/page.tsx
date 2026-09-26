// packages/dashboard/src/app/account-disabled/page.tsx
// Account-disabled status: suspended, revoked, or inactive accounts.
'use client'

import Link from 'next/link'
import { ShieldOff, LogIn } from 'lucide-react'

export default function AccountDisabledPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 text-ink">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center shadow-2xl">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-crit-soft text-crit">
          <ShieldOff className="h-8 w-8" />
        </div>
        <h1 className="mt-5 text-xl font-semibold text-ink">Account Disabled</h1>
        <p className="mt-2 text-sm leading-6 text-ink-muted">
          This account has been suspended or disabled. If you believe this is an
          error, contact your administrator.
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