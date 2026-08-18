"use client";

import { useState, useEffect } from "react";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/ui/kpi";
import { BarChart3, AlertTriangle, CheckCircle, XCircle, Info, RefreshCw } from "lucide-react";

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
    mae: number;
    rmse: number;
    r2: number;
    mape: number;
    persistence_mae: number;
    beats_persistence: boolean;
    high_flow_mae: number;
    high_flow_r2: number;
    walk_forward_mae: number;
  };
  data_info: {
    total_samples: number;
    real_samples: number;
    synthetic_samples: number;
    train_samples: number;
    val_samples: number;
    test_samples: number;
  };
  recommendation: string;
  reasons: string[];
  validated_at: string;
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
    case "PRODUCTION": return <CheckCircle className="h-4 w-4 text-emerald-400" />;
    case "APPROVED": return <CheckCircle className="h-4 w-4 text-sky-400" />;
    case "SHADOW": return <Info className="h-4 w-4 text-amber-400" />;
    case "EXPERIMENTAL": return <AlertTriangle className="h-4 w-4 text-amber-400" />;
    case "REJECTED": return <XCircle className="h-4 w-4 text-red-400" />;
    default: return <Info className="h-4 w-4 text-slate-400" />;
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
        fetch(`${API_BASE}/water/validation/reports?limit=50`),
      ]);
      const sumData = await sumRes.json();
      const repData = await repRes.json();
      setSummary(sumData);
      setReports(repData.value || []);
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        Loading validation reports...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">ML Validation Reports</h1>
          <p className="text-sm text-slate-500 mt-1">
            Walk-forward backtesting results for all assets
          </p>
        </div>
        <button
          onClick={runValidation}
          disabled={running}
          className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
          {running ? "Running..." : "Re-run Validation"}
        </button>
      </div>

      {/* Status Banner */}
      <div className={`rounded-lg border p-4 ${
        summary?.overall_status === "REJECTED"
          ? "border-red-500/30 bg-red-500/10"
          : "border-amber-500/30 bg-amber-500/10"
      }`}>
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
          <span className="font-medium text-slate-200">Model Status: {summary?.overall_status}</span>
        </div>
        <p className="mt-1 text-sm text-slate-400">
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
          accent="bg-emerald-500/10 text-emerald-300"
        />
        <KpiCard
          label="Worst Asset"
          value={summary?.worst_asset || "N/A"}
          icon={XCircle}
          accent="bg-red-500/10 text-red-300"
        />
        <KpiCard
          label="Overall Status"
          value={summary?.overall_status || "UNKNOWN"}
          icon={AlertTriangle}
          accent="bg-amber-500/10 text-amber-300"
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
                  <div className="mt-1 text-xs text-slate-500">
                    {summary?.recommendations?.[status] || 0} models
                  </div>
                </div>
                {i < 3 && <div className="w-8 h-px bg-slate-700 mx-3" />}
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Detailed Reports */}
      <Card>
        <CardHeader title="Asset Validation Details" subtitle="Per-asset walk-forward backtesting results" />
        <CardBody>
          <div className="space-y-4">
            {reports.map((r) => (
              <div key={r.id} className="border border-slate-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(r.recommendation)}
                    <div>
                      <h3 className="font-medium text-slate-200">Asset #{r.asset_id} — {r.model_version}</h3>
                      <p className="text-xs text-slate-500">
                        Horizon: {r.horizon}d | Samples: {r.data_info.total_samples} ({r.data_info.real_samples} real)
                      </p>
                    </div>
                  </div>
                  <Badge tone={getStatusTone(r.recommendation)}>
                    {r.recommendation}
                  </Badge>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <div className="text-slate-500 text-xs">MAE</div>
                    <div className="font-mono text-slate-300">
                      {r.metrics.mae.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">R²</div>
                    <div className={`font-mono ${r.metrics.r2 > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {r.metrics.r2.toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">Persistence MAE</div>
                    <div className="font-mono text-slate-300">
                      {r.metrics.persistence_mae.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">Beats Persistence</div>
                    <div className={r.metrics.beats_persistence ? "text-emerald-400 font-medium" : "text-red-400 font-medium"}>
                      {r.metrics.beats_persistence ? "YES" : "NO"}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">High-Flow MAE</div>
                    <div className="font-mono text-slate-300">
                      {r.metrics.high_flow_mae.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">High-Flow R²</div>
                    <div className={`font-mono ${r.metrics.high_flow_r2 > 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {r.metrics.high_flow_r2.toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">Walk-Forward MAE</div>
                    <div className="font-mono text-slate-300">
                      {r.metrics.walk_forward_mae.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 text-xs">Train / Val / Test</div>
                    <div className="font-mono text-slate-300">
                      {r.data_info.train_samples}/{r.data_info.val_samples}/{r.data_info.test_samples}
                    </div>
                  </div>
                </div>

                {/* Reasons */}
                {r.reasons && r.reasons.length > 0 && (
                  <div className="mt-3 text-sm">
                    <div className="font-medium text-slate-500 text-xs">Reasons:</div>
                    <ul className="list-disc list-inside space-y-1 mt-1">
                      {r.reasons.map((reason, i) => (
                        <li key={i} className="text-slate-400 text-xs">{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Data Requirements */}
      <Card>
        <CardHeader title="Data Requirements for Model Promotion" />
        <CardBody>
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-3 gap-4 font-medium text-slate-500 text-xs">
              <div>Requirement</div>
              <div>Current</div>
              <div>Status</div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-slate-300 text-sm">
              <div>Real observations per asset</div>
              <div>25 days</div>
              <div className="text-red-400">Need 90+ days</div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-slate-300 text-sm">
              <div>Beats persistence baseline</div>
              <div>{summary?.recommendations?.REJECTED || 0} / {summary?.total_reports} assets</div>
              <div className="text-red-400">Majority fail</div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-slate-300 text-sm">
              <div>R² &gt; 0.5</div>
              <div>0 / {summary?.total_reports} assets</div>
              <div className="text-red-400">None pass</div>
            </div>
            <div className="grid grid-cols-3 gap-4 text-slate-300 text-sm">
              <div>High-flow recall</div>
              <div>Not evaluated</div>
              <div className="text-amber-400">Need more data</div>
            </div>
          </div>
          <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm text-slate-300">
            <strong>Conclusion:</strong> With only 25 real observations per asset, models cannot learn meaningful patterns.
            Need 6+ months of real IRSA data for production-ready models. Synthetic data is not used for final validation.
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
