// packages/dashboard/src/app/account-disabled/page.tsx
// Account-disabled status: suspended, revoked, or inactive accounts.
'use client'

import Link from 'next/link'
import { ShieldOff, LogIn } from 'lucide-react'

export default function AccountDisabledPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 text-slate-200">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center shadow-2xl">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 text-red-400">
          <ShieldOff className="h-8 w-8" />
        </div>
        <h1 className="mt-5 text-xl font-semibold text-slate-100">Account Disabled</h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          This account has been suspended or disabled. If you believe this is an
          error, contact your administrator.
        </p>
        <Link
          href="/login"
          className="mt-6 inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700/60"
        >
          <LogIn className="h-4 w-4" /> Back to Login
        </Link>
      </div>
    </div>
  )
}