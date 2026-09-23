// packages/dashboard/src/app/admin/assets/page.tsx
// Asset Management - view all water infrastructure assets and their readings.
'use client'

import { useState } from 'react'
import { Workflow, Search, ExternalLink, Bell } from 'lucide-react'
import Link from 'next/link'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, EmptyState } from '@/components/ui/state'
import { useWaterAssets } from '@/features/water/hooks'
import { fmtNumber, timeAgo } from '@/lib/format'
import type { AssetSummaryVM } from '@/features/water/types'

const AMBER = 'bg-warn-soft text-warn'

export default function AdminAssetsPage() {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('ALL')

  const assetsQuery = useWaterAssets()
  const assets = assetsQuery.data ?? []

  const types = Array.from(new Set(assets.map((a) => a.assetType))).sort()

  const filtered = assets.filter((a) => {
    if (typeFilter !== 'ALL' && a.assetType !== typeFilter) return false
    if (search && !a.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Asset Management"
          description="View all water infrastructure assets and their current readings."
          icon={<Workflow className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="slate">{assets.length} assets</Badge>}
        />

        {/* Search + type filter */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search assets..."
              className="w-full rounded-lg border border-line bg-surface pl-9 pr-3 py-2 text-xs text-ink-muted placeholder:text-ink-subtle focus:border-brand/25 focus:outline-none"
            />
          </div>
          <div className="flex gap-1.5">
            <button
              onClick={() => setTypeFilter('ALL')}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                typeFilter === 'ALL'
                  ? 'bg-brand-soft text-brand border border-brand/25'
                  : 'text-ink-muted hover:bg-surface-alt border border-transparent'
              }`}
            >
              All
            </button>
            {types.map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition ${
                  typeFilter === t
                    ? 'bg-brand-soft text-brand border border-brand/25'
                    : 'text-ink-muted hover:bg-surface-alt border border-transparent'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Asset list */}
        <Card>
          <CardHeader
            title="Assets"
            subtitle={`${filtered.length} assets showing`}
            icon={<Workflow className="h-5 w-5" />}
            accent={AMBER}
          />
          <CardBody className="p-0">
            {assetsQuery.isPending ? (
              <div className="p-8"><Spinner /></div>
            ) : filtered.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No assets" message="No assets match the current filters." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-line text-[11px] uppercase tracking-wider text-ink-subtle">
                      <th className="px-5 py-3 font-medium">Asset</th>
                      <th className="px-5 py-3 font-medium">Type</th>
                      <th className="px-5 py-3 font-medium">Level</th>
                      <th className="px-5 py-3 font-medium">Storage</th>
                      <th className="px-5 py-3 font-medium">Inflow</th>
                      <th className="px-5 py-3 font-medium">Discharge</th>
                      <th className="px-5 py-3 font-medium">Freshness</th>
                      <th className="px-5 py-3 font-medium"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {filtered.map((asset) => (
                      <AssetRow key={asset.id} asset={asset} />
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

function AssetRow({ asset }: { asset: AssetSummaryVM }) {
  const latest = asset.latest
  return (
    <tr className="transition-colors hover:bg-surface-alt">
      <td className="px-5 py-3">
        <p className="font-medium text-ink">{asset.name}</p>
      </td>
      <td className="px-5 py-3">
        <Badge tone="slate">{asset.assetType}</Badge>
      </td>
      <td className="px-5 py-3 font-mono text-ink-muted">
        {latest?.reservoirLevelM != null ? `${fmtNumber(latest.reservoirLevelM)} m` : '—'}
      </td>
      <td className="px-5 py-3 font-mono text-ink-muted">
        {latest?.storagePct != null ? `${fmtNumber(latest.storagePct)}%` : '—'}
      </td>
      <td className="px-5 py-3 font-mono text-ink-muted">
        {latest?.inflowCumecs != null ? `${fmtNumber(latest.inflowCumecs)} m³/s` : '—'}
      </td>
      <td className="px-5 py-3 font-mono text-ink-muted">
        {latest?.dischargeCumecs != null ? `${fmtNumber(latest.dischargeCumecs)} m³/s` : '—'}
      </td>
      <td className="px-5 py-3 text-xs text-ink-subtle">
        {timeAgo(latest?.recordedAt)}
      </td>
      <td className="px-5 py-3">
        <Link
          href={`/water/operator/assets/${asset.id}`}
          className="text-ink-subtle hover:text-brand transition"
        >
          <ExternalLink className="h-4 w-4" />
        </Link>
      </td>
    </tr>
  )
}
