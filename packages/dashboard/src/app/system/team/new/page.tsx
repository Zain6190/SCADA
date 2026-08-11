// packages/dashboard/src/app/system/team/new/page.tsx
// Supervisors provision field operators. The region dropdown only lists the
// districts inside the supervisor's own scope (fetched via the scoped
// /water/regions endpoint) and the role list is the backend's delegated
// allowlist - out-of-scope regions and privileged roles are impossible.
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, UserPlus, KeyRound, MapPin, ShieldCheck } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/state'
import { useCreateOperator, useOperatorRoles, useAdminRegions } from '@/features/admin/hooks'

const AMBER = 'bg-amber-500/10 text-amber-300'
const ACCESS_STATUSES = ['ACTIVE', 'PENDING']

const selectCls =
  'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-amber-400 focus:outline-none'
const inputCls =
  'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-amber-400 focus:outline-none'

export default function NewOperatorPage() {
  const router = useRouter()
  const createOperator = useCreateOperator()
  const rolesQuery = useOperatorRoles()
  const regionsQuery = useAdminRegions()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('field_officer')
  const [status, setStatus] = useState('ACTIVE')
  const [regionId, setRegionId] = useState('')
  const [error, setError] = useState('')

  const districts = (regionsQuery.data ?? []).filter((r) => r.type === 'district')
  const roleInfo = rolesQuery.data?.find((r) => r.name === role)
  const permissions = roleInfo?.permissions ?? []

  const submitDisabled =
    !fullName.trim() || !email.trim() || !password || !regionId || createOperator.isPending

  const handleSubmit = async () => {
    setError('')
    try {
      await createOperator.mutateAsync({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role,
        access_status: status,
        region_id: Number(regionId),
      })
      router.push('/system/team')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Operator creation failed')
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Add Operator"
          description="Provision a field operator. The assigned district is locked to your managed scope."
          icon={<UserPlus className="h-6 w-6" />}
          accent={AMBER}
          action={
            <button
              onClick={handleSubmit}
              disabled={submitDisabled}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500/15 px-4 py-2 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <UserPlus className="h-4 w-4" /> {createOperator.isPending ? 'Creating…' : 'Create operator'}
            </button>
          }
        />

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="grid gap-6">
            <Card>
              <CardHeader
                title="Identity"
                subtitle="Name, email and a temporary password."
                icon={<KeyRound className="h-5 w-5" />}
                accent={AMBER}
              />
              <CardBody className="space-y-4">
                <Field label="Full name">
                  <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="e.g. Riaz Ahmed" className={inputCls} />
                </Field>
                <Field label="Email">
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e.g. riaz.ahmed@ibcp.gov.pk" className={inputCls} />
                </Field>
                <Field label="Temporary password">
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Minimum 8 characters" className={inputCls} />
                </Field>
                <Field label="Lifecycle status">
                  <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectCls}>
                    {ACCESS_STATUSES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </Field>
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Assigned District"
                subtitle="Derived from your own scope - only districts you manage are listed."
                icon={<MapPin className="h-5 w-5" />}
                accent={AMBER}
              />
              <CardBody className="space-y-4">
                <Field label="District">
                  {regionsQuery.isPending ? (
                    <div className="py-2"><Spinner label="Loading districts" /></div>
                  ) : (
                    <select value={regionId} onChange={(e) => setRegionId(e.target.value)} className={selectCls}>
                      <option value="">Select a district…</option>
                      {districts.map((d) => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                      ))}
                    </select>
                  )}
                </Field>
                <p className="text-[11px] text-slate-500">
                  The operator will see water data for this district only. Out-of-scope regions cannot be assigned.
                </p>
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Role & Permissions"
              subtitle="Delegated roles only - read live from the backend."
              icon={<ShieldCheck className="h-5 w-5" />}
              accent={AMBER}
            />
            <CardBody className="space-y-4">
              <Field label="Role">
                {rolesQuery.isPending ? (
                  <div className="py-2"><Spinner label="Loading roles" /></div>
                ) : (
                  <select value={role} onChange={(e) => setRole(e.target.value)} className={selectCls}>
                    {(rolesQuery.data ?? []).map((r) => (
                      <option key={r.name} value={r.name}>{r.name}</option>
                    ))}
                  </select>
                )}
              </Field>
              <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] uppercase tracking-wider text-slate-500">Permission preview</span>
                  <Badge tone="amber">{role}</Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {permissions.length === 0 ? (
                    <span className="text-xs text-slate-600">No permissions resolved for this role.</span>
                  ) : (
                    permissions.map((p) => (
                      <span key={p} className="rounded-md border border-slate-700 bg-slate-800/60 px-2 py-1 font-mono text-[10px] text-slate-300">
                        {p}
                      </span>
                    ))
                  )}
                </div>
              </div>
              <p className="text-[11px] text-slate-500">
                Every operator account is created with a DISTRICT scope granted by you. PENDING accounts cannot
                sign in until approved on the team page.
              </p>
            </CardBody>
          </Card>
        </div>

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div>
        )}

        <button
          onClick={() => router.push('/system/team')}
          className="inline-flex items-center gap-2 text-sm text-slate-400 transition-colors hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" /> Back to My Team
        </button>
      </div>
    </AppShell>
  )
}

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