// packages/dashboard/src/app/system/access-requests/page.tsx
// Review pending/rejected portal access requests and approve or deny them.
'use client'

import { Inbox, ShieldCheck, CheckCircle2, XCircle } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useAdminUsers, useUpdateUser } from '@/features/admin/hooks'
import { fmtDateTime } from '@/lib/format'
import type { AdminUser } from '@/features/admin/api'

const AMBER = 'bg-amber-500/10 text-amber-300'

export default function AccessRequestsPage() {
  const usersQuery = useAdminUsers()
  const updateUser = useUpdateUser()
  const users = usersQuery.data ?? []
  const requests = users.filter((u) => u.access_status === 'PENDING' || u.access_status === 'REJECTED')

  const decide = async (user: AdminUser, status: 'APPROVED' | 'ACTIVE' | 'REJECTED') => {
    await updateUser.mutateAsync({ userId: user.id, patch: { access_status: status } })
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Access Requests"
          description="Pending portal access requests awaiting administrator review."
          icon={<Inbox className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">{requests.length} pending</Badge>}
        />

        <Card>
          <CardHeader
            title="Requests"
            subtitle="Approve to grant portal access, or reject to keep the account gate-closed."
            icon={<ShieldCheck className="h-5 w-5" />}
            accent={AMBER}
          />
          <CardBody className="p-0">
            {usersQuery.isPending ? (
              <div className="p-8"><Spinner label="Loading requests" /></div>
            ) : usersQuery.isError ? (
              <div className="p-8">
                <ErrorState title="Requests unavailable" onRetry={() => usersQuery.refetch()} />
              </div>
            ) : requests.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No pending requests" message="All portal access has been decided." />
              </div>
            ) : (
              <div className="divide-y divide-slate-800/70">
                {requests.map((u) => (
                  <div
                    key={u.id}
                    className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-slate-200">{u.full_name}</p>
                        <Badge tone={u.access_status === 'REJECTED' ? 'red' : 'amber'}>
                          {u.access_status}
                        </Badge>
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-slate-500">{u.email}</p>
                      <p className="mt-0.5 text-[11px] text-slate-600">
                        Role {u.role} · requested {u.access_requested_at ? fmtDateTime(u.access_requested_at) : '—'}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <button
                        onClick={() => decide(u, 'APPROVED')}
                        disabled={updateUser.isPending}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25 disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-4 w-4" /> Approve
                      </button>
                      <button
                        onClick={() => decide(u, 'REJECTED')}
                        disabled={updateUser.isPending}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-medium text-red-200 transition-colors hover:bg-red-500/25 disabled:opacity-50"
                      >
                        <XCircle className="h-4 w-4" /> Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}