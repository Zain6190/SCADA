"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/ui/kpi";
import { Database, CheckCircle, XCircle, Info, AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/shell/app-shell";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/state";
import { useAuth } from "@/context/AuthContext";
import { PERMISSIONS } from "@/lib/permissions";
import { waterApi, type ModelVersionRow } from "@/features/water/api";

const STATUSES = ["ALL", "EXPERIMENTAL", "SHADOW", "APPROVED", "PRODUCTION", "REJECTED"] as const;
type StatusFilter = (typeof STATUSES)[number];

function statusTone(status: string): "emerald" | "sky" | "amber" | "red" | "slate" {
  switch (status) {
    case "PRODUCTION": return "emerald";
    case "APPROVED": return "sky";
    case "SHADOW":
    case "EXPERIMENTAL": return "amber";
    case "REJECTED": return "red";
    default: return "slate";
  }
}

function statusIcon(status: string) {
  switch (status) {
    case "PRODUCTION": return <CheckCircle className="h-4 w-4 text-ok" />;
    case "APPROVED": return <ShieldCheck className="h-4 w-4 text-brand" />;
    case "SHADOW":
    case "EXPERIMENTAL": return <Info className="h-4 w-4 text-warn" />;
    case "REJECTED": return <XCircle className="h-4 w-4 text-crit" />;
    default: return <Info className="h-4 w-4 text-ink-muted" />;
  }
}

function actionLabel(action: string): string {
  switch (action) {
    case "APPROVED": return "Approve";
    case "PRODUCTION": return "Promote";
    case "REJECTED": return "Reject";
    default: return action;
  }
}

function actionVariant(action: string): "primary" | "danger" {
  return action === "REJECTED" ? "danger" : "primary";
}

function metricSummary(row: ModelVersionRow): string {
  const m = row.metrics || {};
  const parts: string[] = [];
  if (typeof m.r2 === "number") parts.push(`R² ${m.r2.toFixed(2)}`);
  if (typeof m.mae === "number") parts.push(`MAE ${m.mae.toFixed(1)}`);
  if (typeof m.auc === "number") parts.push(`AUC ${m.auc.toFixed(2)}`);
  if (typeof m.f1 === "number") parts.push(`F1 ${m.f1.toFixed(2)}`);
  if (typeof m.score === "number") parts.push(`Score ${m.score.toFixed(0)}`);
  return parts.length ? parts.join(" · ") : "—";
}

export default function RegistryPage() {
  const { hasPermission } = useAuth();
  const canApprove = hasPermission(PERMISSIONS.AQUAVISION_APPROVE_REPORT);

  const [rows, setRows] = useState<ModelVersionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<StatusFilter>("ALL");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await waterApi.getRegistryModels({ limit: 500 }));
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load model registry");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const runTransition = async (row: ModelVersionRow, action: string) => {
    setBusyId(row.id);
    setError(null);
    try {
      const updated = await waterApi.transitionModel(row.id, action as "approve" | "promote" | "reject");
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (e: any) {
      setError(e?.response?.data?.detail || `Failed to ${action} ${row.version}`);
      await load();
    } finally {
      setBusyId(null);
    }
  };

  const counts = STATUSES.reduce((acc, s) => {
    if (s !== "ALL") acc[s] = rows.filter((r) => r.status === s).length;
    return acc;
  }, {} as Record<string, number>);

  const visible = filter === "ALL" ? rows : rows.filter((r) => r.status === filter);

  if (loading) {
    return (
      <AppShell>
        <Spinner label="Loading model registry" />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          title="Model Registry"
          description="Lifecycle of trained models: EXPERIMENTAL → SHADOW → APPROVED → PRODUCTION."
          icon={<Database className="h-6 w-6" />}
          action={
            <Button variant="secondary" size="sm" onClick={load} loading={loading}>
              {!loading && <RefreshCw className="h-3.5 w-3.5" />}
              Refresh
            </Button>
          }
        />

        {error && (
          <div className="rounded-lg border border-crit/25 bg-crit-soft p-4 text-sm text-crit">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KpiCard label="Registered Versions" value={rows.length} icon={Database} />
          <KpiCard label="Approved" value={counts.APPROVED || 0} icon={ShieldCheck} accent="bg-brand-soft text-brand" />
          <KpiCard label="In Production" value={counts.PRODUCTION || 0} icon={CheckCircle} accent="bg-ok-soft text-ok" />
          <KpiCard label="Rejected" value={counts.REJECTED || 0} icon={XCircle} accent="bg-crit-soft text-crit" />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`rounded border px-3 py-1.5 text-xs font-semibold transition-colors ${
                filter === s
                  ? "border-brand/40 bg-brand-soft text-brand"
                  : "border-line bg-surface text-ink-muted hover:text-ink"
              }`}
            >
              {s}
              {s !== "ALL" && (
                <span className="ml-1.5 text-ink-subtle">{counts[s] || 0}</span>
              )}
            </button>
          ))}
        </div>

        <Card>
          <CardHeader
            title="Model Versions"
            subtitle={
              canApprove
                ? "Approve shadow models after review; promote approved models to production."
                : "Read-only view — approval requires the AQUAVISION_APPROVE_REPORT permission."
            }
          />
          <CardBody>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase text-ink-subtle">
                    <th className="py-2 pr-4">Model</th>
                    <th className="py-2 pr-4">Version</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Validation</th>
                    <th className="py-2 pr-4">Metrics</th>
                    <th className="py-2 pr-4">Approved</th>
                    <th className="py-2 pr-4">Trained</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-6 text-center text-ink-muted">
                        No model versions registered yet.
                      </td>
                    </tr>
                  )}
                  {visible.map((row) => (
                    <tr key={row.id} className="border-b border-line/60 last:border-0">
                      <td className="py-3 pr-4">
                        <div className="font-medium text-ink">{row.model_type}</div>
                        <div className="text-xs text-ink-subtle">
                          {row.asset_id ? `Asset #${row.asset_id}` : "Global"}
                        </div>
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-ink-muted">{row.version}</td>
                      <td className="py-3 pr-4">
                        <span className="inline-flex items-center gap-1.5">
                          {statusIcon(row.status)}
                          <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        {row.validation_recommendation ? (
                          <Badge tone={statusTone(row.validation_recommendation)}>
                            {row.validation_recommendation}
                          </Badge>
                        ) : (
                          <span className="text-xs text-ink-subtle">—</span>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-xs text-ink-muted">{metricSummary(row)}</td>
                      <td className="py-3 pr-4 text-xs text-ink-muted">
                        {row.approved_by ? (
                          <>
                            <div>{row.approved_by}</div>
                            {row.approved_at && (
                              <div className="text-ink-subtle">
                                {new Date(row.approved_at).toLocaleDateString()}
                              </div>
                            )}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 pr-4 text-xs text-ink-muted">
                        {row.trained_at ? new Date(row.trained_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          {canApprove &&
                            row.allowed_transitions.map((action) => (
                              <Button
                                key={action}
                                variant={actionVariant(action)}
                                size="sm"
                                loading={busyId === row.id}
                                disabled={busyId !== null && busyId !== row.id}
                                onClick={() => runTransition(row, action)}
                              >
                                {actionLabel(action)}
                              </Button>
                            ))}
                          {!canApprove && (
                            <span className="inline-flex items-center gap-1 text-xs text-ink-subtle">
                              <AlertTriangle className="h-3.5 w-3.5" />
                              Read-only
                            </span>
                          )}
                          {canApprove && row.allowed_transitions.length === 0 && (
                            <span className="text-xs text-ink-subtle">Terminal</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      </div>
    </AppShell>
  );
}
