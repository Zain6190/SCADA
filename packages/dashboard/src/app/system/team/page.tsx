// packages/dashboard/src/app/system/team/page.tsx
// Supervisor team: field operators created/approved within the supervisor's
// own geographic scope. Backend clamps every create/update to the caller's
// region - the page only renders what the endpoint returns.
'use client'

import Link from 'next/link'
import { useState } from 'react'
import { Users, ShieldCheck, Globe, UserPlus, Check, Ban, Undo2 } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { useSupervisorTeam, useUpdateOperator } from '@/features/admin/hooks'

const AMBER = 'bg-amber-500/10 text-amber-300'

const ACCESS_TONE: Record<string, 'emerald' | 'sky' | 'amber' | 'red' | 'slate'> = {
  ACTIVE: 'emerald',
  APPROVED: 'sky',
  PENDING: 'amber',
  SUSPENDED: 'red',
  REVOKED: 'slate',
}

function ScopeLabel({ scope }: { scope: { scope_type: string | null; region_ids?: number[] | null } }) {
  if (!scope?.scope_type) return <span className="text-slate-600">No scope</span>
  if (scope.scope_type === 'NATIONAL')
    return (
      <span className="inline-flex items-center gap-1 text-emerald-300">
        <Globe className="h-3 w-3" /> National
      </span>
    )
  return <span className="font-mono text-[11px] text-slate-400">{scope.scope_type}</span>
}

export default function TeamPage() {
  const teamQuery = useSupervisorTeam()
  const updateOperator = useUpdateOperator()
  const [working, setWorking] = useState<number | null>(null)
  const [error, setError] = useState('')

  const team = teamQuery.data ?? []

  const act = async (userId: number, accessStatus: string) => {
    setWorking(userId)
    setError('')
    try {
      await updateOperator.mutateAsync({ userId, patch: { access_status: accessStatus } })
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Update failed')
    } finally {
      setWorking(null)
    }
  }

  const pending = team.filter((u) => u.access_status === 'PENDING').length

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="My Team"
          description="Field operators in your region. Assigned regions are locked to your own scope."
          icon={<Users className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">{team.length} operators</Badge>}
          action={
            <Link
              href="/system/team/new"
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500/15 px-4 py-2 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/25"
            >
              <UserPlus className="h-4 w-4" /> Add Operator
            </Link>
          }
        />

        {pending > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
            {pending} pending operator request{pending === 1 ? '' : 's'} awaiting your approval.
          </div>
        )}

        <Card>
          <CardHeader
            title="Operators & Requests"
            subtitle="Approve pending sign-ups, suspend accounts, or open the register to add new staff."
            icon={<ShieldCheck className="h-5 w-5" />}
            accent={AMBER}
          />
          <CardBody className="p-0">
            {teamQuery.isPending ? (
              <div className="p-8"><Spinner label="Loading team" /></div>
            ) : teamQuery.isError ? (
              <div className="p-8">
                <ErrorState title="Team unavailable" onRetry={() => teamQuery.refetch()} />
              </div>
            ) : team.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No operators yet" message="Add staff for your region to begin." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-5 py-3 font-medium">Operator</th>
                      <th className="px-5 py-3 font-medium">Role</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                      <th className="px-5 py-3 font-medium">Scope</th>
                      <th className="px-5 py-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {team.map((u) => (
                      <tr key={u.id} className="transition-colors hover:bg-slate-800/20">
                        <td className="px-5 py-3">
                          <p className="font-medium text-slate-200">{u.full_name}</p>
                          <p className="font-mono text-[11px] text-slate-500">{u.email}</p>
                        </td>
                        <td className="px-5 py-3">
                          <Badge tone="slate">{u.role}</Badge>
                        </td>
                        <td className="px-5 py-3">
                          <Badge tone={ACCESS_TONE[u.access_status] ?? 'slate'}>{u.access_status}</Badge>
                        </td>
                        <td className="px-5 py-3">
                          <ScopeLabel scope={u.region_scope} />
                        </td>
                        <td className="px-5 py-3 text-right">
                          <div className="inline-flex items-center gap-2">
                            {u.access_status === 'PENDING' && (
                              <button
                                onClick={() => act(u.id, 'ACTIVE')}
                                disabled={working === u.id}
                                className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
                              >
                                <Check className="h-3.5 w-3.5" /> Approve
                              </button>
                            )}
                            {u.access_status === 'ACTIVE' || u.access_status === 'APPROVED' ? (
                              <button
                                onClick={() => act(u.id, 'SUSPENDED')}
                                disabled={working === u.id}
                                className="inline-flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 transition-colors hover:bg-red-500/20 disabled:opacity-50"
                              >
                                <Ban className="h-3.5 w-3.5" /> Suspend
                              </button>
                            ) : null}
                            {(u.access_status === 'SUSPENDED' || u.access_status === 'REVOKED') && (
                              <button
                                onClick={() => act(u.id, 'ACTIVE')}
                                disabled={working === u.id}
                                className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700/60 disabled:opacity-50"
                              >
                                <Undo2 className="h-3.5 w-3.5" /> Restore
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div>
        )}
      </div>
    </AppShell>
  )
}