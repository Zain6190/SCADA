// packages/dashboard/src/app/system/users/[id]/client.tsx
// Edit a user's role, access lifecycle, active flag, and regional scope.
'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Save, UserCog, ShieldCheck } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState } from '@/components/ui/state'
import { useAdminUsers, useUpdateUser } from '@/features/admin/hooks'
import { fmtDateTime } from '@/lib/format'

const AMBER = 'bg-amber-500/10 text-amber-300'

const ACCESS_STATUSES = ['ACTIVE', 'APPROVED', 'PENDING', 'REJECTED', 'SUSPENDED', 'REVOKED']
const ROLES = ['admin', 'aquavision_analyst', 'crop_analyst', 'geo_analyst', 'field_officer', 'viewer', 'water_supervisor']
const SCOPE_TYPES = ['NATIONAL', 'PROVINCE', 'DISTRICT']

export function UserDetailClient() {
  const params = useParams()
  const router = useRouter()
  const userId = Number(params.id)
  const { data: users, isPending, isError, refetch } = useAdminUsers()
  const updateUser = useUpdateUser()

  const user = users?.find((u) => u.id === userId)
  const [role, setRole] = useState<string>(user?.role ?? 'viewer')
  const [status, setStatus] = useState<string>(user?.access_status ?? 'ACTIVE')
  const [isActive, setIsActive] = useState<boolean>(user?.is_active ?? true)
  const [scopeType, setScopeType] = useState<string>(user?.region_scope?.scope_type ?? 'NATIONAL')
  const [regionId, setRegionId] = useState<string>(user?.region_ids?.[0]?.toString() ?? '')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  // Sync local form state when the user loads (first fetch/navigation).
  useEffect(() => {
    if (!user) return
    setRole(user.role)
    setStatus(user.access_status)
    setIsActive(user.is_active)
    setScopeType(user.region_scope?.scope_type ?? 'NATIONAL')
    setRegionId(user.region_ids?.[0]?.toString() ?? '')
    setMessage('')
    setError('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, user?.id])

  const handleSave = async () => {
    if (!user) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const patch: Record<string, unknown> = { role, access_status: status.toUpperCase(), is_active: isActive }
      if (scopeType === 'NATIONAL') {
        patch.scope = { scope_type: 'NATIONAL' }
      } else if (scopeType === 'PROVINCE' || scopeType === 'DISTRICT') {
        if (!regionId) {
          setError('A region id is required for a regional scope.')
          setSaving(false)
          return
        }
        patch.scope = { scope_type: scopeType, region_id: Number(regionId), asset_id: null }
      } else {
        patch.scope = null
      }
      await updateUser.mutateAsync({ userId, patch })
      setMessage('User updated successfully.')
      refetch()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Edit Portal Access"
          description={user ? `${user.full_name} · ${user.email}` : 'Loading user…'}
          icon={<UserCog className="h-6 w-6" />}
          accent={AMBER}
          action={
            <button
              onClick={handleSave}
              disabled={saving || !user}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500/15 px-4 py-2 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-4 w-4" /> {saving ? 'Saving…' : 'Save changes'}
            </button>
          }
        />

        {isPending ? (
          <div className="p-8"><Spinner label="Loading user" /></div>
        ) : isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : !user ? (
          <Card>
            <CardBody className="p-8 text-center text-sm text-slate-500">
              User #{userId} not found.
            </CardBody>
          </Card>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Identity & Lifecycle"
                subtitle="Account status and portal access state"
                icon={<ShieldCheck className="h-5 w-5" />}
                accent={AMBER}
              />
              <CardBody className="space-y-4">
                <Field label="Role">
                  <select value={role} onChange={(e) => setRole(e.target.value)} className={selectCls}>
                    {ROLES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Access status">
                  <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectCls}>
                    {ACCESS_STATUSES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Account enabled">
                  <label className="flex items-center gap-2 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={isActive}
                      onChange={(e) => setIsActive(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-700 bg-slate-900 accent-amber-400"
                    />
                    is_active
                  </label>
                </Field>
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-[11px] text-slate-500">
                  Last granted: {user.access_requested_at ? fmtDateTime(user.access_requested_at) : '—'}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Regional Scope"
                subtitle="Fail-closed geographic access. No scope = no data."
                icon={<ShieldCheck className="h-5 w-5" />}
                accent={AMBER}
              />
              <CardBody className="space-y-4">
                <Field label="Scope type">
                  <select value={scopeType} onChange={(e) => setScopeType(e.target.value)} className={selectCls}>
                    {SCOPE_TYPES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                {scopeType === 'NATIONAL' ? (
                  <p className="text-xs text-slate-500">
                    NATIONAL grants access to every region (default for administrators).
                  </p>
                ) : (
                  <Field label="Region id">
                    <input
                      type="number"
                      value={regionId}
                      onChange={(e) => setRegionId(e.target.value)}
                      placeholder="e.g. 6"
                      className={inputCls}
                    />
                  </Field>
                )}
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] uppercase tracking-wider text-slate-500">Current</span>
                    <Badge tone="slate">{user.region_scope?.scope_type ?? 'NONE'}</Badge>
                  </div>
                  <p className="mt-2 font-mono text-[11px] text-slate-500">
                    {user.region_scope?.region_ids?.join(', ') ?? 'NATIONAL'}
                  </p>
                </div>
              </CardBody>
            </Card>
          </div>
        )}

        {message && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
            {message}
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <button
          onClick={() => router.push('/system/users')}
          className="inline-flex items-center gap-2 text-sm text-slate-400 transition-colors hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Portal Access
        </button>
      </div>
    </AppShell>
  )
}

const selectCls =
  'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-amber-400 focus:outline-none'
const inputCls =
  'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-amber-400 focus:outline-none'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </label>
      {children}
    </div>
  )
}