// packages/dashboard/src/app/system/users/new/page.tsx
// Create a portal account: role + access status + name-based geo scope,
// with a live permission preview computed from the selected role.
'use client'

import { useState, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Plus, ShieldCheck, KeyRound, Globe } from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/state'
import { useCreateUser, useAdminRoles, useAdminRegions } from '@/features/admin/hooks'
import type { RegionOption } from '@/features/admin/api'

const AMBER = 'bg-amber-500/10 text-amber-300'
const ACCESS_STATUSES = ['ACTIVE', 'APPROVED', 'PENDING']
const SCOPE_TYPES = ['NATIONAL', 'PROVINCE', 'DISTRICT', 'ASSET']

const selectCls =
  'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-amber-400 focus:outline-none'
const inputCls =
  'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-amber-400 focus:outline-none'

export default function NewUserPage() {
  const router = useRouter()
  const createUser = useCreateUser()
  const rolesQuery = useAdminRoles()
  const regionsQuery = useAdminRegions()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('viewer')
  const [status, setStatus] = useState('ACTIVE')
  const [scopeType, setScopeType] = useState('NATIONAL')
  const [provinceId, setProvinceId] = useState('')
  const [districtId, setDistrictId] = useState('')
  const [tehsilId, setTehsilId] = useState('')
  const [assetIds, setAssetIds] = useState<number[]>([])
  const [error, setError] = useState('')

  const regions = regionsQuery.data ?? []
  const provinces = regions.filter((r) => r.type === 'province')
  const selectedProvince = regionById(provinceId, regions)
  const districts = regions.filter((r) => r.type === 'district')
  const selectedDistrict = regionById(districtId, regions)
  const tehsils = regions.filter((r) => r.type === 'tehsil')

  const roleInfo = rolesQuery.data?.find((r) => r.name === role)
  const permissions = roleInfo?.permissions ?? []

  // Reset dependent pickers when a parent changes.
  useEffect(() => {
    setDistrictId('')
    setTehsilId('')
    setAssetIds([])
  }, [provinceId])

  useEffect(() => {
    setTehsilId('')
    setAssetIds([])
  }, [districtId])

  const scopeConfig = useMemo(() => {
    if (scopeType === 'NATIONAL') return { scope_type: 'NATIONAL' as const }
    let regionId: number | null = null
    if (scopeType === 'PROVINCE') regionId = Number(provinceId) || null
    if (scopeType === 'DISTRICT') regionId = Number(districtId) || null
    if (scopeType === 'TEHSIL') regionId = Number(tehsilId) || null
    return { scope_type: scopeType, region_id: regionId }
  }, [scopeType, provinceId, districtId, tehsilId])

  const scopeValid =
    scopeType === 'NATIONAL' ||
    (scopeType === 'PROVINCE' && !!provinceId) ||
    (scopeType === 'DISTRICT' && !!districtId) ||
    (scopeType === 'TEHSIL' && !!tehsilId)

  const submitDisabled = !fullName.trim() || !email.trim() || !password || !scopeValid || createUser.isPending

  const handleSubmit = async () => {
    setError('')
    const payload = {
      full_name: fullName.trim(),
      email: email.trim(),
      password,
      role,
      access_status: status,
      scope: scopeConfig,
      asset_ids: scopeType === 'ASSET' && assetIds.length ? assetIds : undefined,
    }
    try {
      await createUser.mutateAsync(payload)
      router.push('/system/users')
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Account creation failed')
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Add Portal User"
          description="Provision a new account with role, lifecycle status, and geographic scope."
          icon={<Plus className="h-6 w-6" />}
          accent={AMBER}
          action={
            <button
              onClick={handleSubmit}
              disabled={submitDisabled}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500/15 px-4 py-2 text-sm font-medium text-amber-200 transition-colors hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-4 w-4" /> {createUser.isPending ? 'Creating…' : 'Create user'}
            </button>
          }
        />

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="grid gap-6">
            <Card>
              <CardHeader
                title="Identity"
                subtitle="Name, email and a temporary password. No access is granted below until a scope is set."
                icon={<KeyRound className="h-5 w-5" />}
                accent={AMBER}
              />
              <CardBody className="space-y-4">
                <Field label="Full name">
                  <input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Asif Raza"
                    className={inputCls}
                  />
                </Field>
                <Field label="Email">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="e.g. asif.raza@ibcp.gov.pk"
                    className={inputCls}
                  />
                </Field>
                <Field label="Temporary password">
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                    className={inputCls}
                  />
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
                title="Geographic Scope"
                subtitle="Pick regions by name. Fail-closed: no scope selection means no data access."
                icon={<Globe className="h-5 w-5" />}
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

                {scopeType === 'NATIONAL' && (
                  <p className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
                    NATIONAL grants access to every administrative region.
                  </p>
                )}

                {scopeType === 'PROVINCE' && (
                  <Field label="Province">
                    <select value={provinceId} onChange={(e) => setProvinceId(e.target.value)} className={selectCls}>
                      <option value="">Select a province…</option>
                      {provinces.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </Field>
                )}

                {scopeType === 'DISTRICT' && (
                  <>
                    <Field label="Province">
                      <select value={provinceId} onChange={(e) => setProvinceId(e.target.value)} className={selectCls}>
                        <option value="">Select a province…</option>
                        {provinces.map((p) => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                    </Field>
                    {provinceId && (
                      <Field label="District">
                        <select value={districtId} onChange={(e) => setDistrictId(e.target.value)} className={selectCls}>
                          <option value="">Select a district…</option>
                          {districts
                            .filter((d) => d.parent_region_id === selectedProvince?.id)
                            .map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                      </Field>
                    )}
                  </>
                )}

                {scopeType === 'TEHSIL' && (
                  <>
                    <Field label="Province">
                      <select value={provinceId} onChange={(e) => setProvinceId(e.target.value)} className={selectCls}>
                        <option value="">Select a province…</option>
                        {provinces.map((p) => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                    </Field>
                    {provinceId && (
                      <Field label="District">
                        <select value={districtId} onChange={(e) => setDistrictId(e.target.value)} className={selectCls}>
                          <option value="">Select a district…</option>
                          {districts
                            .filter((d) => d.parent_region_id === selectedProvince?.id)
                            .map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                      </Field>
                    )}
                    {districtId && (
                      <Field label="Tehsil">
                        <select value={tehsilId} onChange={(e) => setTehsilId(e.target.value)} className={selectCls}>
                          <option value="">Select a tehsil…</option>
                          {tehsils
                            .filter((d) => d.parent_region_id === selectedDistrict?.id)
                            .map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                        </select>
                      </Field>
                    )}
                  </>
                )}

                {!scopeValid && scopeType !== 'NATIONAL' && (
                  <p className="text-xs text-amber-300">
                    Finish the region selection above — an empty scope means the account cannot see any data.
                  </p>
                )}
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Role & Permissions"
              subtitle="Permission set is read live from the backend role, not hardcoded."
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
                      <span
                        key={p}
                        className="rounded-md border border-slate-700 bg-slate-800/60 px-2 py-1 font-mono text-[10px] text-slate-300"
                      >
                        {p}
                      </span>
                    ))
                  )}
                </div>
              </div>
              <p className="text-[11px] text-slate-500">
                Account is created atomically — user + role + scope in a single transaction. Non-ACTIVE accounts
                cannot sign in.
              </p>
            </CardBody>
          </Card>
        </div>

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div>
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

function regionById(id: string, regions: RegionOption[]): RegionOption | undefined {
  return regions.find((r) => r.id === Number(id))
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