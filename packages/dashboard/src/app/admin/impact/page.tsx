"use client";

import { useState, useEffect } from "react";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/ui/kpi";
import { MapPin, Clock, Users, Building2, RefreshCw, Calculator } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8100";

interface ImpactAsset {
  id: number;
  canonical_name: string;
  asset_type: string;
  latitude: number;
  longitude: number;
}

interface SegmentImpact {
  segment_order: number;
  river_name: string;
  upstream_asset: string;
  downstream_asset: string;
  distance_km: number;
  travel_time_hours: number;
  arrival_time: string;
  flow_at_arrival: number;
  population_exposed: number;
  village_count: number;
  town_count: number;
  bridges_count: number;
  hospitals_count: number;
  roads_km: number;
  confidence: string;
  notes: string;
}

interface ImpactResult {
  source_asset: string;
  release_flow_cusecs: number;
  release_time: string;
  chain_rivers: string[];
  segments: SegmentImpact[];
  total_population_exposed: number;
  total_villages: number;
  total_towns: number;
  total_bridges: number;
  total_hospitals: number;
  total_roads_km: number;
  furthest_asset: string;
  furthest_arrival: string | null;
  total_travel_hours: number;
}

function formatNumber(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(0) + "K";
  return n.toString();
}

function formatArrival(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function ImpactPage() {
  const [assets, setAssets] = useState<ImpactAsset[]>([]);
  const [result, setResult] = useState<ImpactResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);

  const [sourceId, setSourceId] = useState(1);
  const [flow, setFlow] = useState(400000);

  useEffect(() => {
    fetch(`${API_BASE}/water/impact/assets`)
      .then((r) => r.json())
      .then((data) => {
        setAssets(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const calculate = async () => {
    setCalculating(true);
    try {
      const res = await fetch(`${API_BASE}/water/impact/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_asset_id: sourceId,
          release_flow_cusecs: flow,
          release_time: new Date().toISOString(),
        }),
      });
      const data = await res.json();
      setResult(data);
    } catch {
    } finally {
      setCalculating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 text-sky-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Downstream Impact Calculator</h1>
          <p className="text-sm text-slate-400 mt-1">
            Estimate when a flood condition may move downstream and what could be exposed
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Calculator className="h-5 w-5 text-sky-400" />
            Calculate Impact
          </h2>
        </CardHeader>
        <CardBody>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Source Asset</label>
              <select
                value={sourceId}
                onChange={(e) => setSourceId(Number(e.target.value))}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white"
              >
                {assets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.canonical_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Release Flow (cusecs)</label>
              <input
                type="number"
                value={flow}
                onChange={(e) => setFlow(Number(e.target.value))}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-white"
                step={10000}
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={calculate}
                disabled={calculating}
                className="w-full bg-sky-600 hover:bg-sky-700 disabled:bg-slate-700 text-white font-medium py-2 px-4 rounded transition-colors"
              >
                {calculating ? "Calculating..." : "Calculate Impact"}
              </button>
            </div>
          </div>
        </CardBody>
      </Card>

      {result && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <KpiCard
              label="Population Exposed"
              value={formatNumber(result.total_population_exposed)}
              icon={Users}
              accent="bg-amber-500/10 text-amber-300"
            />
            <KpiCard
              label="Villages"
              value={result.total_villages.toString()}
              icon={MapPin}
            />
            <KpiCard
              label="Bridges"
              value={result.total_bridges.toString()}
              icon={Building2}
              accent="bg-red-500/10 text-red-300"
            />
            <KpiCard
              label="Hospitals"
              value={result.total_hospitals.toString()}
              icon={Building2}
              accent="bg-red-500/10 text-red-300"
            />
            <KpiCard
              label="Furthest Asset"
              value={result.furthest_asset}
              icon={MapPin}
            />
            <KpiCard
              label="Total Travel"
              value={`${result.total_travel_hours.toFixed(0)}h`}
              icon={Clock}
            />
          </div>

          <Card>
            <CardHeader>
              <h2 className="text-lg font-semibold text-white">
                {result.source_asset} → {result.furthest_asset}
              </h2>
              <p className="text-sm text-slate-400">
                {formatNumber(result.release_flow_cusecs)} cusecs release |{" "}
                {result.chain_rivers.join(" + ")} chain
              </p>
            </CardHeader>
            <CardBody className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700">
                      <th className="text-left p-3 text-slate-400 font-medium">Segment</th>
                      <th className="text-left p-3 text-slate-400 font-medium">Travel</th>
                      <th className="text-left p-3 text-slate-400 font-medium">Arrival</th>
                      <th className="text-right p-3 text-slate-400 font-medium">Flow</th>
                      <th className="text-right p-3 text-slate-400 font-medium">Population</th>
                      <th className="text-right p-3 text-slate-400 font-medium">Villages</th>
                      <th className="text-right p-3 text-slate-400 font-medium">Bridges</th>
                      <th className="text-right p-3 text-slate-400 font-medium">Hospitals</th>
                      <th className="text-center p-3 text-slate-400 font-medium">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.segments.map((seg) => (
                      <tr
                        key={seg.segment_order}
                        className="border-b border-slate-800 hover:bg-slate-800/50"
                      >
                        <td className="p-3">
                          <div className="text-white font-medium">{seg.upstream_asset}</div>
                          <div className="text-slate-500 text-xs">→ {seg.downstream_asset}</div>
                        </td>
                        <td className="p-3 text-sky-400 font-mono">{seg.travel_time_hours.toFixed(0)}h</td>
                        <td className="p-3 text-white">{formatArrival(seg.arrival_time)}</td>
                        <td className="p-3 text-right text-amber-400 font-mono">
                          {formatNumber(seg.flow_at_arrival)}
                        </td>
                        <td className="p-3 text-right text-white font-medium">
                          {formatNumber(seg.population_exposed)}
                        </td>
                        <td className="p-3 text-right text-slate-300">{seg.village_count}</td>
                        <td className="p-3 text-right text-red-400">{seg.bridges_count}</td>
                        <td className="p-3 text-right text-red-400">{seg.hospitals_count}</td>
                        <td className="p-3 text-center">
                          <Badge
                            variant={
                              seg.confidence === "HIGH"
                                ? "default"
                                : seg.confidence === "MEDIUM"
                                ? "secondary"
                                : "destructive"
                            }
                          >
                            {seg.confidence}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>

          {result.segments.length > 0 && (
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold text-white">Impact Timeline</h2>
              </CardHeader>
              <CardBody>
                <div className="relative">
                  <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-slate-700" />
                  {result.segments.map((seg) => (
                    <div key={seg.segment_order} className="relative pl-10 pb-6">
                      <div className="absolute left-2.5 top-1 w-3 h-3 rounded-full bg-sky-500 border-2 border-slate-900" />
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="text-white font-medium">{seg.downstream_asset}</div>
                          <div className="text-sm text-slate-400">
                            {seg.river_name} | {seg.distance_km}km | {seg.travel_time_hours.toFixed(0)}h travel
                          </div>
                          <div className="text-xs text-slate-500 mt-1">{seg.notes}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sky-400 font-mono text-sm">{formatArrival(seg.arrival_time)}</div>
                          <div className="text-amber-400 font-mono text-sm">{formatNumber(seg.flow_at_arrival)} cusecs</div>
                          <div className="text-white text-sm">{formatNumber(seg.population_exposed)} people</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
