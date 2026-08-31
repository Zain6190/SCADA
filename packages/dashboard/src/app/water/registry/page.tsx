// packages/dashboard/src/app/water/registry/page.tsx
// AquaVision Model Registry - Model lifecycle management with promote/demote workflow.
'use client'

import { useState, useEffect } from 'react'
import {
  Cpu, RefreshCw, ArrowUpCircle, ArrowDownCircle, CheckCircle,
  AlertTriangle, XCircle, BarChart3, TrendingUp, Database,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const STATUS_CONFIG: Record<string, { color: string; icon: any; label: string }> = {
  SHADOW: { color: 'emerald', icon: CheckCircle, label: 'Shadow' },
  EXPERIMENTAL: { color: 'sky', icon: AlertTriangle, label: 'Experimental' },
  REJECTED: { color: 'red', icon: XCircle, label: 'Rejected' },
}

const STATUS_TONE: Record<string, 'emerald' | 'sky' | 'red' | 'slate'> = {
  SHADOW: 'emerald',
  EXPERIMENTAL: 'sky',
  REJECTED: 'red',
}

const ASSET_NAMES: Record<number, string> = {
  1: 'Tarbela', 2: 'Mangla', 3: 'Chashma', 4: 'Kalabagh',
  5: 'Taunsa', 6: 'Guddu', 7: 'Sukkur', 8: 'Kotri',
  9: 'Kabul @ Nowshera', 10: 'Chenab @ Marala', 11: 'Panjnad',
}

interface RegistryModel {
  asset_id: number
  asset_name: string
  model_type: string
  model_version: string
  horizon: number
  metrics: {
    r2_log?: number
    mae_log?: number
    r2?: number
    mae?: number
    score?: number
    persistence_mae_log?: number
    mae_improvement_pct?: number
  }
  recommendation: string
  reasons: any[]
  validated_at: string
}

interface RegistrySummary {
  summary: Record<string, { count: number; avg_r2_log: number; avg_mae_log: number; avg_score: number }>
  total_on_disk: number
  total_validated: number
}

export default function ModelRegistryPage() {
  const queryClient = useQueryClient()
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined)
  const [filterAsset, setFilterAsset] = useState<number | undefined>(undefined)

  const { data: registry, isLoading: regLoading, refetch: refetchRegistry } = useQuery({
    queryKey: ['model-registry', filterStatus, filterAsset],
    queryFn: () => waterApi.getModelRegistry({ status: filterStatus, asset_id: filterAsset }),
  })

  const { data: summary, isLoading: sumLoading } = useQuery({
    queryKey: ['registry-summary'],
    queryFn: () => waterApi.getRegistrySummary(),
  })

  const promoteMutation = useMutation({
    mutationFn: (payload: { asset_id: number; model_type: string; horizon: number; status: string }) =>
      waterApi.promoteModel(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['model-registry'] })
      queryClient.invalidateQueries({ queryKey: ['registry-summary'] })
    },
  })

  const models: RegistryModel[] = registry?.models || []
  const stats: RegistrySummary | undefined = summary

  const uniqueAssets = [...new Set(models.map(m => m.asset_id))].sort((a, b) => a - b)

  const summaryCards = stats ? [
    {
      label: 'Total on Disk',
      value: stats.total_on_disk,
      icon: Database,
      color: 'text-slate-400',
    },
    {
      label: 'Validated',
      value: stats.total_validated,
      icon: BarChart3,
      color: 'text-sky-400',
    },
    {
      label: 'Shadow',
      value: stats.summary?.SHADOW?.count || 0,
      icon: CheckCircle,
      color: 'text-emerald-400',
    },
    {
      label: 'Experimental',
      value: stats.summary?.EXPERIMENTAL?.count || 0,
      icon: AlertTriangle,
      color: 'text-amber-400',
    },
    {
      label: 'Rejected',
      value: stats.summary?.REJECTED?.count || 0,
      icon: XCircle,
      color: 'text-red-400',
    },
  ] : []

  return (
    <AppShell>
      <PageHeader
        title="Model Registry"
        subtitle="Model lifecycle management — validate, promote, and demote models"
        icon={Cpu}
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        {sumLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}><CardBody className="p-4 text-center"><Spinner size="sm" /></CardBody></Card>
          ))
        ) : (
          summaryCards.map((s) => (
            <Card key={s.label}>
              <CardBody className="p-4 text-center">
                <s.icon className={`w-5 h-5 ${s.color} mx-auto mb-1`} />
                <div className="text-2xl font-bold text-slate-100">{s.value}</div>
                <div className="text-xs text-slate-400">{s.label}</div>
              </CardBody>
            </Card>
          ))
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <select
          value={filterStatus || ''}
          onChange={(e) => setFilterStatus(e.target.value || undefined)}
          className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-200"
        >
          <option value="">All Statuses</option>
          <option value="SHADOW">Shadow</option>
          <option value="EXPERIMENTAL">Experimental</option>
          <option value="REJECTED">Rejected</option>
        </select>
        <select
          value={filterAsset || ''}
          onChange={(e) => setFilterAsset(e.target.value ? Number(e.target.value) : undefined)}
          className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-200"
        >
          <option value="">All Assets</option>
          {uniqueAssets.map(aid => (
            <option key={aid} value={aid}>{ASSET_NAMES[aid] || `Asset ${aid}`}</option>
          ))}
        </select>
        <button
          onClick={() => refetchRegistry()}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm text-slate-200"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Model Table */}
      {regLoading ? (
        <Card><CardBody className="p-8 text-center"><Spinner /></CardBody></Card>
      ) : models.length === 0 ? (
        <Card><CardBody className="p-8 text-center">
          <EmptyState message="No validation reports found. Run batch validation first." />
        </CardBody></Card>
      ) : (
        <Card>
          <CardHeader title="Validated Models" />
          <CardBody className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-left">
                    <th className="px-4 py-2 text-slate-400 font-medium">Asset</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">Type</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">Horizon</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">R² (log)</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">MAE (log)</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">R² (raw)</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">Score</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">Status</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">Validated</th>
                    <th className="px-4 py-2 text-slate-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => {
                    const cfg = STATUS_CONFIG[m.recommendation] || STATUS_CONFIG.EXPERIMENTAL
                    return (
                      <tr key={i} className="border-b border-slate-800 hover:bg-slate-800/50">
                        <td className="px-4 py-2 text-slate-200 font-medium">
                          {ASSET_NAMES[m.asset_id] || `Asset ${m.asset_id}`}
                        </td>
                        <td className="px-4 py-2 text-slate-300">
                          {m.model_type === 'flood_predictor' ? 'Flood' : 'High-Flow'}
                        </td>
                        <td className="px-4 py-2 text-slate-300">{m.horizon}d</td>
                        <td className="px-4 py-2">
                          <span className={`font-mono ${(m.metrics?.r2_log || 0) >= 0.5 ? 'text-emerald-400' : (m.metrics?.r2_log || 0) >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
                            {(m.metrics?.r2_log || 0).toFixed(4)}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-slate-300 font-mono">
                          {(m.metrics?.mae_log || 0).toFixed(4)}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`font-mono ${(m.metrics?.r2 || 0) >= 0.5 ? 'text-emerald-400' : (m.metrics?.r2 || 0) >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
                            {(m.metrics?.r2 || 0).toFixed(4)}
                          </span>
                        </td>
                        <td className="px-4 py-2">
                          <span className={`font-mono font-bold ${(m.metrics?.score || 0) >= 70 ? 'text-emerald-400' : (m.metrics?.score || 0) >= 35 ? 'text-amber-400' : 'text-slate-400'}`}>
                            {m.metrics?.score || 0}
                          </span>
                        </td>
                        <td className="px-4 py-2">
                          <Badge tone={STATUS_TONE[m.recommendation] || 'slate'}>
                            {cfg.label}
                          </Badge>
                        </td>
                        <td className="px-4 py-2 text-slate-400 text-xs">
                          {m.validated_at ? new Date(m.validated_at).toLocaleDateString() : '—'}
                        </td>
                        <td className="px-4 py-2">
                          <div className="flex gap-1">
                            {m.recommendation !== 'SHADOW' && (
                              <button
                                onClick={() => promoteMutation.mutate({
                                  asset_id: m.asset_id,
                                  model_type: m.model_type,
                                  horizon: m.horizon,
                                  status: 'SHADOW',
                                })}
                                className="p-1 rounded hover:bg-emerald-500/20 text-emerald-400"
                                title="Promote to Shadow"
                              >
                                <ArrowUpCircle className="w-4 h-4" />
                              </button>
                            )}
                            {m.recommendation !== 'REJECTED' && (
                              <button
                                onClick={() => promoteMutation.mutate({
                                  asset_id: m.asset_id,
                                  model_type: m.model_type,
                                  horizon: m.horizon,
                                  status: 'REJECTED',
                                })}
                                className="p-1 rounded hover:bg-red-500/20 text-red-400"
                                title="Demote to Rejected"
                              >
                                <ArrowDownCircle className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}
    </AppShell>
  )
}
