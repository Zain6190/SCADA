// packages/dashboard/src/app/system/users/page.tsx
// Portal access administration - list every user with role, status and scope.
'use client'

import Link from 'next/link'
import { Users, ShieldCheck, Globe, ArrowRight, UserPlus } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useAdminUsers } from '@/features/admin/hooks'
import { fmtDateTime } from '@/lib/format'
import type { AdminUser } from '@/features/admin/api'

const AMBER = 'bg-amber-500/10 text-amber-300'

const ACCESS_TONE: Record<string, 'emerald' | 'sky' | 'amber' | 'violet' | 'red' | 'slate'> = {
  ACTIVE: 'emerald',
  APPROVED: 'sky',
  PENDING: 'amber',
  REJECTED: 'red',
  SUSPENDED: 'red',
  REVOKED: 'slate',
}

function ScopeLabel({ user }: { user: AdminUser }) {
  const scope = user.region_scope
  if (!scope?.access) return <span className="text-slate-600">No scope</span>
  if (scope.scope_type === 'NATIONAL')
    return (
      <span className="inline-flex items-center gap-1 text-emerald-300">
        <Globe className="h-3 w-3" /> National
      </span>
    )
  return <span className="font-mono text-[11px] text-slate-400">{scope.scope_type}</span>
}

export default function SystemUsersPage() {
  const usersQuery = useAdminUsers()
  const users = usersQuery.data ?? []

  const byStatus = (s: string) => users.filter((u) => u.access_status === s).length

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Portal Access"
          description="User provisioning, roles, permission sets, and geographic scope."
          icon={<Users className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">{users.length} users</Badge>}
          action={
            <Link
              href="/system/users/new"
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500/15 px-4 py-2 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/25"
            >
              <UserPlus className="h-4 w-4" /> Add User
            </Link>
          }
        />

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <SummaryBox label="Active" value={byStatus('ACTIVE') + byStatus('APPROVED')} />
          <SummaryBox label="Pending" value={byStatus('PENDING')} />
          <SummaryBox label="Suspended / Revoked" value={byStatus('SUSPENDED') + byStatus('REVOKED')} />
          <SummaryBox label="Rejected" value={byStatus('REJECTED')} />
        </div>

        <Card>
          <CardHeader
            title="Users & Access Status"
            subtitle="Review and edit role, lifecycle status, and regional scope."
            icon={<ShieldCheck className="h-5 w-5" />}
            accent={AMBER}
          />
          <CardBody className="p-0">
            {usersQuery.isPending ? (
              <div className="p-8"><Spinner label="Loading users" /></div>
            ) : usersQuery.isError ? (
              <div className="p-8">
                <ErrorState title="Users unavailable" onRetry={() => usersQuery.refetch()} />
              </div>
            ) : users.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No users" message="Provision accounts to begin." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-5 py-3 font-medium">User</th>
                      <th className="px-5 py-3 font-medium">Role</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                      <th className="px-5 py-3 font-medium">Scope</th>
                      <th className="px-5 py-3 font-medium">Permissions</th>
                      <th className="px-5 py-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {users.map((u) => (
                      <UserRow key={u.id} user={u} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </AppShell>
  )
}

function SummaryBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <p className="text-2xl font-semibold text-slate-100">{value}</p>
      <p className="mt-1 text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
    </div>
  )
}

function UserRow({ user }: { user: AdminUser }) {
  return (
    <tr className="transition-colors hover:bg-slate-800/20">
      <td className="px-5 py-3">
        <p className="font-medium text-slate-200">{user.full_name}</p>
        <p className="font-mono text-[11px] text-slate-500">{user.email}</p>
      </td>
      <td className="px-5 py-3">
        <Badge tone="slate">{user.role}</Badge>
      </td>
      <td className="px-5 py-3">
        <Badge tone={ACCESS_TONE[user.access_status] ?? 'slate'}>{user.access_status}</Badge>
      </td>
      <td className="px-5 py-3">
        <ScopeLabel user={user} />
      </td>
      <td className="px-5 py-3">
        <p className="font-mono text-[10px] leading-4 text-slate-500">
          {user.permissions.length ? user.permissions.join(', ') : '—'}
        </p>
      </td>
      <td className="px-5 py-3 text-right">
        <Link
          href={`/system/users/${user.id}`}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700/60"
        >
          Edit <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </td>
    </tr>
  )
}