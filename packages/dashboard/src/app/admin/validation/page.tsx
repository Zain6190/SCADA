"use client";

import { useState, useEffect } from "react";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/ui/kpi";
import { BarChart3, AlertTriangle, CheckCircle, XCircle, Info, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/shell/app-shell";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/state";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8100";

interface ValidationSummary {
  total_reports: number;
  assets_validated: number;
  recommendations: Record<string, number>;
  best_asset: string | null;
  worst_asset: string | null;
  overall_status: string;
}

interface ValidationReport {
  id: number;
  asset_id: number;
  model_type: string;
  model_version: string;
  horizon: number;
  metrics: {
    mae?: number | null;
    rmse?: number | null;
    r2?: number | null;
    mape?: number | null;
    persistence_mae?: number | null;
    beats_persistence?: boolean;
    high_flow_mae?: number | null;
    high_flow_r2?: number | null;
    walk_forward_mae?: number | null;
    auc?: number | null;
    brier?: number | null;
    baseline_brier?: number | null;
    accuracy?: number | null;
    precision?: number | null;
    recall?: number | null;
    f1?: number | null;
    score?: number | null;
  };
  data_info: {
    total_samples: number;
    real_samples?: number;
    synthetic_samples?: number;
    train_samples?: number;
    val_samples?: number;
    test_samples?: number;
    n_folds?: number;
  };
  recommendation: string;
  reasons: string[];
  validated_at: string;
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtFixed(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

function getStatusTone(status: string): "emerald" | "sky" | "amber" | "red" | "slate" {
  switch (status) {
    case "PRODUCTION": return "emerald";
    case "APPROVED": return "sky";
    case "SHADOW": return "amber";
    case "EXPERIMENTAL": return "amber";
    case "REJECTED": return "red";
    default: return "slate";
  }
}

function getStatusIcon(status: string) {
  switch (status) {
    case "PRODUCTION": return <CheckCircle className="h-4 w-4 text-ok" />;
    case "APPROVED": return <CheckCircle className="h-4 w-4 text-brand" />;
    case "SHADOW": return <Info className="h-4 w-4 text-warn" />;
    case "EXPERIMENTAL": return <AlertTriangle className="h-4 w-4 text-warn" />;
    case "REJECTED": return <XCircle className="h-4 w-4 text-crit" />;
    default: return <Info className="h-4 w-4 text-ink-muted" />;
  }
}

export default function ValidationPage() {
  const [summary, setSummary] = useState<ValidationSummary | null>(null);
  const [reports, setReports] = useState<ValidationReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [sumRes, repRes] = await Promise.all([
        fetch(`${API_BASE}/water/validation/reports/summary`),
        fetch(`${API_BASE}/water/validation/reports?limit=100`),
      ]);
      const sumData = await sumRes.json();
      const repData = await repRes.json();
      setSummary(sumData);
      const rows: ValidationReport[] = Array.isArray(repData)
        ? repData
        : repData.value || [];
      const seen = new Set<string>();
      setReports(
        rows.filter((r) => {
          const key = `${r.model_type}:${r.asset_id}:${r.horizon}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        })
      );
    } catch (e) {
      console.error("Failed to fetch validation data", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const runValidation = async () => {
    setRunning(true);
    try {
      await fetch(`${API_BASE}/water/validation/run?horizon=7`, { method: "POST" });
      await fetchData();
    } finally {
      setRunning(false);
    }
  };

  const regReports = reports.filter(
    (r) => r.model_type !== "flood_classifier" && r.metrics.mae != null
  );
  const clfReports = reports.filter((r) => r.model_type === "flood_classifier");
  const beatsCount = regReports.filter((r) => r.metrics.beats_persistence).length;
  const r2PassCount = regReports.filter((r) => (r.metrics.r2 ?? 0) > 0.5).length;
  const maxReal = reports.reduce((m, r) => Math.max(m, r.data_info.real_samples ?? 0), 0);
  const clfRecalls = clfReports
    .map((r) => r.metrics.recall)
    .filter((v): v is number => typeof v === "number");
  const avgRecall = clfRecalls.length
    ? clfRecalls.reduce((a, b) => a + b, 0) / clfRecalls.length
    : null;
  const toneFor = (ratio: number): string =>
    ratio >= 0.7 ? "text-ok" : ratio >= 0.4 ? "text-warn" : "text-crit";

  if (loading) {
    return (
      <AppShell>
        <Spinner label="Loading validation reports" />
      </AppShell>
    );
  }

  return (
    <AppShell>
    <div className="space-y-5">
      <PageHeader
        title="ML Validation Reports"
        description="Walk-forward backtesting results for all assets."
        icon={<BarChart3 className="h-6 w-6" />}
        action={
          <Button variant="primary" size="sm" onClick={runValidation} loading={running}>
            {!running && <RefreshCw className="h-3.5 w-3.5" />}
            {running ? "Running…" : "Re-run Validation"}
          </Button>
        }
      />

      {/* Status Banner */}
      <div className={`rounded-lg border p-4 ${
        summary?.overall_status === "REJECTED"
          ? "border-crit/25 bg-crit-soft"
          : "border-warn/25 bg-warn-soft"
      }`}>
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-warn" />
          <span className="font-medium text-ink">Model Status: {summary?.overall_status}</span>
        </div>
        <p className="mt-1 text-sm text-ink-muted">
          {summary?.overall_status === "REJECTED"
            ? "All models rejected. Insufficient real training data. Models are advisory-only."
            : "Models are experimental. Do not use for operational decisions without human review."}
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KpiCard
          label="Assets Validated"
          value={summary?.assets_validated || 0}
          icon={BarChart3}
        />
        <KpiCard
          label="Best Asset"
          value={summary?.best_asset || "N/A"}
          icon={CheckCircle}
          accent="bg-ok-soft text-ok"
        />
        <KpiCard
          label="Worst Asset"
          value={summary?.worst_asset || "N/A"}
          icon={XCircle}
          accent="bg-crit-soft text-crit"
        />
        <KpiCard
          label="Overall Status"
          value={summary?.overall_status || "UNKNOWN"}
          icon={AlertTriangle}
          accent="bg-warn-soft text-warn"
        />
      </div>

      {/* Model Status Lifecycle */}
      <Card>
        <CardHeader title="Model Status Lifecycle" subtitle="Models must pass each stage before promotion" />
        <CardBody>
          <div className="flex items-center justify-between">
            {["EXPERIMENTAL", "SHADOW", "APPROVED", "PRODUCTION"].map((status, i) => (
              <div key={status} className="flex items-center">
                <div className="text-center">
                  <Badge tone={getStatusTone(status)}>{status}</Badge>
                  <div className="mt-1 text-xs text-ink-subtle">
                    {summary?.recommendations?.[status] || 0} models
                  </div>
                </div>
                {i < 3 && <div className="w-8 h-px bg-surface-sunken mx-3" />}
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Detailed Reports */}
      <Card>
        <CardHeader title="Asset Validation Details" subtitle="Per-model walk-forward backtesting results" />
        <CardBody>
          <div className="space-y-4">
            {reports.length === 0 && (
              <div className="text-sm text-ink-muted">No validation reports yet.</div>
            )}
            {reports.map((r) => {
              const isClassifier = r.model_type === "flood_classifier";
              const brierSkill =
                r.metrics.baseline_brier && r.metrics.brier != null
                  ? ((r.metrics.baseline_brier - r.metrics.brier) / r.metrics.baseline_brier) * 100
                  : null;
              return (
              <div key={r.id} className="border border-line rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(r.recommendation)}
                    <div>
                      <h3 className="font-medium text-ink">Asset #{r.asset_id} — {r.model_version}</h3>
                      <p className="text-xs text-ink-subtle">
                        {isClassifier ? "Flood classifier" : "Regression"} | Horizon: {r.horizon}d | Samples:{" "}
                        {r.data_info.total_samples}
                        {isClassifier
                          ? ` | Folds: ${r.data_info.n_folds ?? "—"}`
                          : ` (${r.data_info.real_samples ?? "—"} real)`}
                      </p>
                    </div>
                  </div>
                  <Badge tone={getStatusTone(r.recommendation)}>
                    {r.recommendation}
                  </Badge>
                </div>

                {/* Metrics Grid */}
                {isClassifier ? (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <div className="text-ink-subtle text-xs">AUC</div>
                      <div className={`font-mono ${(r.metrics.auc ?? 0) > 0.7 ? "text-ok" : "text-crit"}`}>
                        {fmtFixed(r.metrics.auc)}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Brier Skill vs Baseline</div>
                      <div className={`font-mono ${(brierSkill ?? 0) > 0 ? "text-ok" : "text-crit"}`}>
                        {brierSkill === null ? "—" : `${brierSkill.toFixed(1)}%`}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Accuracy</div>
                      <div className="font-mono text-ink-muted">
                        {r.metrics.accuracy == null ? "—" : `${(r.metrics.accuracy * 100).toFixed(1)}%`}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">F1</div>
                      <div className="font-mono text-ink-muted">{fmtFixed(r.metrics.f1)}</div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Precision</div>
                      <div className="font-mono text-ink-muted">{fmtFixed(r.metrics.precision)}</div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Recall</div>
                      <div className={`font-mono ${(r.metrics.recall ?? 0) >= 0.3 ? "text-ok" : "text-warn"}`}>
                        {fmtFixed(r.metrics.recall)}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Validation Score</div>
                      <div className={`font-mono ${(r.metrics.score ?? 0) >= 70 ? "text-ok" : "text-ink-muted"}`}>
                        {fmt(r.metrics.score, 0)} / 100
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Brier (baseline)</div>
                      <div className="font-mono text-ink-muted">
                        {fmtFixed(r.metrics.brier)} ({fmtFixed(r.metrics.baseline_brier)})
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <div className="text-ink-subtle text-xs">MAE</div>
                      <div className="font-mono text-ink-muted">{fmt(r.metrics.mae)}</div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">R²</div>
                      <div className={`font-mono ${(r.metrics.r2 ?? 0) > 0 ? "text-ok" : "text-crit"}`}>
                        {fmtFixed(r.metrics.r2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Persistence MAE</div>
                      <div className="font-mono text-ink-muted">{fmt(r.metrics.persistence_mae)}</div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Beats Persistence</div>
                      <div className={r.metrics.beats_persistence ? "text-ok font-medium" : "text-crit font-medium"}>
                        {r.metrics.beats_persistence ? "YES" : "NO"}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">High-Flow MAE</div>
                      <div className="font-mono text-ink-muted">{fmt(r.metrics.high_flow_mae)}</div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">High-Flow R²</div>
                      <div className={`font-mono ${(r.metrics.high_flow_r2 ?? 0) > 0 ? "text-ok" : "text-crit"}`}>
                        {fmtFixed(r.metrics.high_flow_r2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Walk-Forward MAE</div>
                      <div className="font-mono text-ink-muted">{fmt(r.metrics.walk_forward_mae)}</div>
                    </div>
                    <div>
                      <div className="text-ink-subtle text-xs">Train / Val / Test</div>
                      <div className="font-mono text-ink-muted">
                        {r.data_info.train_samples ?? "—"}/{r.data_info.val_samples ?? "—"}/
                        {r.data_info.test_samples ?? "—"}
                      </div>
                    </div>
                  </div>
                )}

                {/* Reasons */}
                {r.reasons && r.reasons.length > 0 && (
                  <div className="mt-3 text-sm">
                    <div className="font-medium text-ink-subtle text-xs">Reasons:</div>
                    <ul className="list-disc list-inside space-y-1 mt-1">
                      {r.reasons.map((reason, i) => (
                        <li key={i} className="text-ink-muted text-xs">{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              );
            })}
          </div>
        </CardBody>
      </Card>

      {/* Data Requirements */}
      <Card>
        <CardHeader
          title="Promotion Readiness"
          subtitle="Computed from the latest walk-forward reports on this page"
        />
        <CardBody>
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-3 gap-4 font-medium text-ink-subtle text-xs">
              <div>Requirement</div>
              <div>Current</div>
              <div>Status</div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-ink-muted text-sm">
              <div>Real observations (best-fed model)</div>
              <div className="font-mono">{maxReal}</div>
              <div className={maxReal >= 90 ? "text-ok" : "text-crit"}>
                {maxReal >= 90 ? "Meets 90+ day bar" : "Need 90+ days"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-ink-muted text-sm">
              <div>Beats persistence baseline</div>
              <div className="font-mono">
                {beatsCount} / {regReports.length || 0}
              </div>
              <div className={regReports.length ? toneFor(beatsCount / regReports.length) : "text-ink-subtle"}>
                {!regReports.length
                  ? "No reports"
                  : beatsCount / regReports.length >= 0.7
                    ? "Majority pass"
                    : beatsCount / regReports.length >= 0.4
                      ? "Mixed"
                      : "Majority fail"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-ink-muted text-sm">
              <div>R² &gt; 0.5</div>
              <div className="font-mono">
                {r2PassCount} / {regReports.length || 0}
              </div>
              <div className={regReports.length ? toneFor(r2PassCount / regReports.length) : "text-ink-subtle"}>
                {!regReports.length
                  ? "No reports"
                  : r2PassCount / regReports.length >= 0.7
                    ? "Majority pass"
                    : r2PassCount / regReports.length >= 0.4
                      ? "Mixed"
                      : "Majority fail"}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-ink-muted text-sm">
              <div>Classifier recall (avg)</div>
              <div className="font-mono">
                {avgRecall === null ? "—" : `${(avgRecall * 100).toFixed(1)}%`}
              </div>
              <div className={avgRecall === null ? "text-ink-subtle" : avgRecall >= 0.6 ? "text-ok" : avgRecall >= 0.3 ? "text-warn" : "text-crit"}>
                {avgRecall === null
                  ? "Not evaluated"
                  : avgRecall >= 0.6
                    ? "Operational"
                    : avgRecall >= 0.3
                      ? "Improving"
                      : "Needs review"}
              </div>
            </div>
          </div>
          <div className="mt-4 p-3 bg-surface-sunken border border-line rounded-lg text-sm text-ink-muted">
            <strong>How promotion works:</strong> every model is backtested with walk-forward
            folds, then moves EXPERIMENTAL → SHADOW → APPROVED → PRODUCTION. Regression reports
            are judged on MAE / R² vs the persistence baseline; classifier reports on AUC,
            Brier skill and precision/recall. SHADOW models serve live traffic with scoring
            before any human approval step.
          </div>
        </CardBody>
      </Card>
    </div>
    </AppShell>
  );
}
