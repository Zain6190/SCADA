// packages/dashboard/src/app/reports/page.tsx
// AquaVision Reports - weekly PDF documents + CSV / GeoJSON data exports.
'use client'

import { useState } from 'react'
import {
  FileText, Layers, Map, Building2, Globe2, Download, FileJson,
  FileSpreadsheet, RefreshCw, ShieldCheck, FileCheck2,
} from 'lucide-react'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardHeader, CardBody } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { KpiCard } from '@/components/ui/kpi'
import { Spinner, ErrorState, EmptyState } from '@/components/ui/state'
import {
  useWaterReports,
  useGenerateReport,
  useDownloadReport,
} from '@/features/water/hooks'
import { waterApi } from '@/features/water/api'
import { fmtNumber, fmtDate, fmtDateTime } from '@/lib/format'
import { useAuth } from '@/context/AuthContext'
import { PERMISSIONS } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import type { WaterReport } from '@/features/water/types'

const AMBER = 'bg-amber-500/10 text-amber-300'

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function scopeKey(scope: string): string {
  return scope.toLowerCase()
}

export default function ReportsPage() {
  const { user, hasPermission } = useAuth()
  const reportsQuery = useWaterReports()
  const generateReport = useGenerateReport()
  const downloadReport = useDownloadReport()

  const [exporting, setExporting] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const reports = (reportsQuery.data as WaterReport[] | undefined) ?? []
  const canExport = hasPermission(PERMISSIONS.AQUAVISION_EXPORT)

  const national = reports.filter((r) => scopeKey(r.scope) === 'national').length
  const province = reports.filter((r) => scopeKey(r.scope) === 'province').length
  const district = reports.filter((r) => scopeKey(r.scope) === 'district').length

  const handleGenerate = async () => {
    setExportError(null)
    try {
      const report = await generateReport.mutateAsync()
      const blob = await downloadReport.mutateAsync(report.id)
      saveBlob(blob, `aquavision-weekly-${report.week_start_date}.pdf`)
    } catch (e: any) {
      setExportError(e?.response?.data?.detail || e?.message || 'Report generation failed')
    }
  }

  const handleExport = async (kind: 'csv' | 'indicators-geojson' | 'regions-geojson') => {
    setExporting(kind)
    setExportError(null)
    try {
      const stamp = new Date().toISOString().slice(0, 10)
      if (kind === 'csv') {
        const blob = await waterApi.exportIndicatorsCsv({ limit: 10000 })
        saveBlob(blob, `aquavision-indicators-${stamp}.csv`)
      } else if (kind === 'indicators-geojson') {
        const blob = await waterApi.exportIndicatorsGeoJson({ limit: 10000 })
        saveBlob(blob, `aquavision-indicators-${stamp}.geojson`)
      } else {
        const blob = await waterApi.exportRegionsGeoJson()
        saveBlob(blob, `aquavision-severity-${stamp}.geojson`)
      }
    } catch (e: any) {
      setExportError(e?.response?.data?.detail || e?.message || 'Export failed')
    } finally {
      setExporting(null)
    }
  }

  const handleDownload = async (report: WaterReport) => {
    setExportError(null)
    try {
      const blob = await downloadReport.mutateAsync(report.id)
      saveBlob(blob, `aquavision-weekly-${report.week_start_date}.pdf`)
    } catch (e: any) {
      setExportError(e?.response?.data?.detail || e?.message || 'Download failed')
    }
  }

  const busy = generateReport.isPending || exporting !== null

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Reports"
          description="Generated AquaVision intelligence documents and downloadable data exports."
          icon={<FileText className="h-6 w-6" />}
          accent={AMBER}
          badge={<Badge tone="amber">{reports.length} on file</Badge>}
          updatedAt={reports.length ? reports[0].generated_at : undefined}
          action={
            canExport ? (
              <button
                onClick={handleGenerate}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-lg bg-amber-500/20 px-4 py-2 text-xs font-medium text-amber-300 transition-colors hover:bg-amber-500/30 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {generateReport.isPending ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileCheck2 className="h-3.5 w-3.5" />
                )}
                Generate Weekly PDF
              </button>
            ) : undefined
          }
        />

        {exportError && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-300">
            {exportError}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Total Reports"
            value={fmtNumber(reports.length, 0)}
            detail="Across all scopes"
            icon={FileText}
            accent={AMBER}
          />
          <KpiCard
            label="National"
            value={fmtNumber(national, 0)}
            detail="Country-level summaries"
            icon={Globe2}
            accent={AMBER}
          />
          <KpiCard
            label="Province"
            value={fmtNumber(province, 0)}
            detail="Provincial breakdowns"
            icon={Building2}
            accent={AMBER}
          />
          <KpiCard
            label="District"
            value={fmtNumber(district, 0)}
            detail="District-level deep dives"
            icon={Map}
            accent={AMBER}
          />
        </div>

        <Card>
          <CardHeader
            title="Data Exports"
            subtitle={canExport ? 'Download raw indicators as CSV or GeoJSON (access-level filtered)' : 'AQUAVISION_EXPORT required'}
            icon={<Layers className="h-5 w-5" />}
            accent={canExport ? AMBER : 'bg-slate-500/10 text-slate-400'}
          />
          <CardBody className="space-y-4">
            {!canExport ? (
              <div className="flex items-center gap-3 text-sm text-slate-500">
                <ShieldCheck className="h-5 w-5 text-slate-600" />
                Your role does not include export privileges.{' '}
                {user?.role ?? 'Viewer'} accounts can browse the archive but not download data.
              </div>
            ) : (
              <>
                <p className="text-xs leading-5 text-slate-500">
                  Exports honour your geographic scope and access level — viewer-level
                  accounts never receive rainfall/ET analysis fields, even in bulk files.
                </p>
                <div className="flex flex-wrap gap-3">
                  <ExportButton
                    label="Indicators CSV"
                    icon={<FileSpreadsheet className="h-3.5 w-3.5" />}
                    kind="csv"
                    busy={busy}
                    exporting={exporting}
                    onClick={handleExport}
                  />
                  <ExportButton
                    label="Indicators GeoJSON"
                    icon={<FileJson className="h-3.5 w-3.5" />}
                    kind="indicators-geojson"
                    busy={busy}
                    exporting={exporting}
                    onClick={handleExport}
                  />
                  <ExportButton
                    label="Severity Choropleth GeoJSON"
                    icon={<Map className="h-3.5 w-3.5" />}
                    kind="regions-geojson"
                    busy={busy}
                    exporting={exporting}
                    onClick={handleExport}
                  />
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Report Archive"
            subtitle="Latest reports first"
            icon={<Layers className="h-5 w-5" />}
            accent={AMBER}
            action={<Badge tone="slate">{fmtNumber(reports.length, 0)} records</Badge>}
          />
          <CardBody className="p-0">
            {reportsQuery.isPending ? (
              <div className="p-8"><Spinner label="Loading reports" /></div>
            ) : reportsQuery.isError ? (
              <div className="p-8">
                <ErrorState
                  title="Reports unavailable"
                  message="Could not reach the AquaVision service. Check the backend connection."
                  onRetry={() => reportsQuery.refetch()}
                />
              </div>
            ) : reports.length === 0 ? (
              <div className="p-8">
                <EmptyState title="No reports generated" message="Generate the weekly PDF report to produce documents." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-800/70 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="px-5 py-3 font-medium">Title</th>
                      <th className="px-5 py-3 font-medium">Week</th>
                      <th className="px-5 py-3 font-medium">Scope</th>
                      <th className="px-5 py-3 font-medium">Status</th>
                      <th className="px-5 py-3 font-medium">Generated At</th>
                      <th className="px-5 py-3 font-medium">File</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {reports.map((report) => (
                      <ReportRow
                        key={report.id}
                        report={report}
                        onDownload={() => handleDownload(report)}
                        disabled={busy}
                      />
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

function ExportButton({
  label,
  icon,
  kind,
  busy,
  exporting,
  onClick,
}: {
  label: string
  icon: React.ReactNode
  kind: 'csv' | 'indicators-geojson' | 'regions-geojson'
  busy: boolean
  exporting: string | null
  onClick: (kind: 'csv' | 'indicators-geojson' | 'regions-geojson') => void
}) {
  const active = exporting === kind
  return (
    <button
      onClick={() => onClick(kind)}
      disabled={busy}
      className={cn(
        'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        active
          ? 'bg-amber-500/30 text-amber-200'
          : 'bg-amber-500/15 text-amber-300 hover:bg-amber-500/25'
      )}
    >
      {active ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : icon}
      {label}
    </button>
  )
}

function ReportRow({
  report,
  onDownload,
  disabled,
}: {
  report: WaterReport
  onDownload: () => void
  disabled: boolean
}) {
  const done = /generated|success|done|complete/i.test(report.status)
  const hasFile = !!report.file_path && done
  return (
    <tr className="transition-colors hover:bg-slate-800/20">
      <td className="px-5 py-3 font-medium text-slate-200">{report.title}</td>
      <td className="px-5 py-3 text-slate-400">{fmtDate(report.week_start_date)}</td>
      <td className="px-5 py-3"><Badge tone="slate">{report.scope}</Badge></td>
      <td className="px-5 py-3">
        <Badge tone={done ? 'emerald' : 'amber'}>{report.status}</Badge>
      </td>
      <td className="px-5 py-3 font-mono text-xs text-slate-500">{fmtDateTime(report.generated_at)}</td>
      <td className="px-5 py-3">
        {hasFile ? (
          <button
            onClick={onDownload}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-300 transition-colors hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            PDF
          </button>
        ) : (
          <span className="text-xs text-slate-600">—</span>
        )}
      </td>
    </tr>
  )
}