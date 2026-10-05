// packages/dashboard/src/app/water/anomalies/page.tsx
// AquaVision Anomaly Detection - real Isolation Forest scores + regional anomalies.
'use client'

import { useState } from 'react'
import { ShieldAlert, FlaskConical, RefreshCw, HelpCircle, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AppShell } from '@/components/shell/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RestrictedState } from '@/components/ui/state'
import { waterApi } from '@/features/water/api'
import { useAuth } from '@/context/AuthContext'
import { PERMISSIONS, canSeeAnalysis } from '@/lib/permissions'
import Link from 'next/link'
import { AssetAnomalyTab } from './asset-tab'
import { RegionalAnomalyTab } from './regional-tab'

type Tab = 'assets' | 'regional'

const TABS: Array<[Tab, string]> = [
  ['assets', 'Asset anomalies'],
  ['regional', 'Regional anomalies'],
]

export default function AnomaliesPage() {
  const { user, hasPermission } = useAuth()
  const analyst = canSeeAnalysis(user?.permissions)
  const canRetrain = hasPermission(PERMISSIONS.AQUAVISION_MANAGE_DATA)
  const [tab, setTab] = useState<Tab>('assets')
  const [showHelp, setShowHelp] = useState(true)
  const queryClient = useQueryClient()

  const trainMutation = useMutation({
    mutationFn: () => waterApi.trainAnomalyDetectors(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-anomaly-summary'] })
      queryClient.invalidateQueries({ queryKey: ['ml-anomaly-history'] })
      queryClient.invalidateQueries({ queryKey: ['ml-anomalies'] })
    },
  })

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Anomaly Detection"
          description="Isolation Forest scores on live observations, plus regional rainfall and evapotranspiration anomalies."
          icon={<ShieldAlert className="h-6 w-6" />}
          badge={
            <Badge tone="amber">
              <FlaskConical className="mr-1 inline h-3 w-3" />
              EXPERIMENTAL
            </Badge>
          }
          action={
            canRetrain ? (
              <Button
                variant="danger"
                size="sm"
                loading={trainMutation.isPending}
                onClick={() => trainMutation.mutate()}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${trainMutation.isPending ? 'animate-spin' : ''}`} />
                {trainMutation.isPending ? 'Training…' : 'Retrain Detectors'}
              </Button>
            ) : undefined
          }
        />

        {!analyst ? (
          <RestrictedState
            title="Analyst access required"
            message="Anomaly scores and analysis fields are served to Analyst roles and above. Ask an administrator to upgrade your access."
          />
        ) : (
          <>
            {trainMutation.isSuccess && (
              <div className="rounded-xl border border-ok/25 bg-ok-soft px-4 py-3 text-sm text-ok">
                Training complete: {trainMutation.data.models_trained} detectors trained.
              </div>
            )}
            {trainMutation.isError && (
              <div className="rounded-xl border border-crit/25 bg-crit-soft px-4 py-3 text-sm text-crit">
                Training failed. Check the API logs and try again.
              </div>
            )}

            {showHelp && (
              <Card className="border-info/30 bg-info-soft/40">
                <div className="flex items-start gap-3 p-4">
                  <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-info" />
                  <div className="flex-1 space-y-1.5 text-xs leading-5 text-ink-muted">
                    <p className="text-sm font-semibold text-ink">How to read this page</p>
                    <p>
                      <strong className="text-ink">Asset anomalies:</strong> an Isolation Forest scores
                      every observation against the asset&apos;s own history. Scores below 0 are flagged;
                      severity bands are HIGH &lt; −0.30, MODERATE &lt; −0.15, otherwise LOW. The
                      contributing features are the inputs that deviated most (lags, rolling means,
                      rate-of-change).
                    </p>
                    <p>
                      <strong className="text-ink">Regional anomalies:</strong> real hydrological
                      deviations — rainfall ≤ −30% vs normal, evapotranspiration ≥ +25% vs normal
                      (thresholds from <code className="text-ink">water_thresholds</code>).
                    </p>
                    <p>
                      Scores are advisory: review the raw readings before acting.{' '}
                      <Link href="/key-terms" className="font-medium text-brand hover:underline">
                        Glossary →
                      </Link>
                    </p>
                  </div>
                  <button
                    onClick={() => setShowHelp(false)}
                    aria-label="Dismiss help"
                    className="rounded p-1 text-ink-subtle hover:bg-surface-alt hover:text-ink"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            )}

            <div className="flex w-fit rounded-lg border border-line bg-surface p-1">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTab(key)}
                  className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                    tab === key ? 'bg-brand-soft text-brand' : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {tab === 'assets' ? <AssetAnomalyTab /> : <RegionalAnomalyTab />}
          </>
        )}
      </div>
    </AppShell>
  )
}
