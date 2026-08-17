// packages/dashboard/src/features/water/hooks.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { waterApi } from '@/features/water/api'
import {
  mapIndicatorList,
  mapPredictionList,
  mapAlertList,
  mapMapFeatureList,
  mapAssetSummaryList,
  mapAssetReadingsList,
  mapOperationalNoteList,
} from '@/features/water/mappers'
import type { IndicatorParams, IndicatorIngestPayload } from '@/features/water/api'
import { REFRESH_INTERVAL } from '@/lib/config'

export const waterKeys = {
  all: ['water'] as const,
  overview: () => [...waterKeys.all, 'overview'] as const,
  indicators: (params: IndicatorParams) => [...waterKeys.all, 'indicators', params] as const,
  predictions: () => [...waterKeys.all, 'predictions'] as const,
  alerts: (params: Record<string, unknown> = {}) => [...waterKeys.all, 'alerts', params] as const,
  map: () => [...waterKeys.all, 'map'] as const,
  regions: () => [...waterKeys.all, 'regions'] as const,
  reports: () => [...waterKeys.all, 'reports'] as const,
  thresholds: () => [...waterKeys.all, 'thresholds'] as const,
  alertsAll: () => [...waterKeys.all, 'alerts', 'all'] as const,
  assets: () => [...waterKeys.all, 'assets'] as const,
  assetReadings: (assetId: number | null | undefined) =>
    [...waterKeys.all, 'assets', assetId, 'readings'] as const,
  assetNotes: (assetId: number | null | undefined) =>
    [...waterKeys.all, 'assets', assetId, 'notes'] as const,
}

export function useWaterOverview() {
  return useQuery({
    queryKey: waterKeys.all,
    queryFn: waterApi.getOverview,
    refetchInterval: REFRESH_INTERVAL,
  })
}

export function useWaterIndicators(params: IndicatorParams = {}) {
  return useQuery({
    queryKey: waterKeys.indicators(params),
    queryFn: async () => mapIndicatorList(await waterApi.getIndicators(params)),
    refetchInterval: REFRESH_INTERVAL,
  })
}

export function useWaterPredictions() {
  return useQuery({
    queryKey: waterKeys.predictions(),
    queryFn: async () => mapPredictionList(await waterApi.getPredictions()),
    refetchInterval: REFRESH_INTERVAL,
  })
}

export function useWaterAlerts(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: waterKeys.alerts(params),
    queryFn: async () => mapAlertList(await waterApi.getAlerts(params)),
    refetchInterval: 30_000,
  })
}

export function useWaterMapData(params: { week?: string; region_type?: string } = {}) {
  return useQuery({
    queryKey: waterKeys.map(),
    queryFn: async () => mapMapFeatureList((await waterApi.getMapData(params)).features),
    refetchInterval: REFRESH_INTERVAL,
  })
}

export function useWaterRegions() {
  return useQuery({
    queryKey: waterKeys.regions(),
    queryFn: waterApi.getRegions,
    staleTime: 5 * 60 * 1000,
  })
}

export function useWaterReports() {
  return useQuery({
    queryKey: waterKeys.reports(),
    queryFn: async () => waterApi.getReports(),
  })
}

export function useGenerateReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => waterApi.generateReport(),
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: waterKeys.reports() })
      return report
    },
  })
}

export function useDownloadReport() {
  return useMutation({
    mutationFn: waterApi.downloadReport,
  })
}

export function useWaterThresholds() {
  return useQuery({
    queryKey: waterKeys.thresholds(),
    queryFn: waterApi.getThresholds,
  })
}

export function useAcknowledgeWaterAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { alertId: number; notes?: string }) =>
      waterApi.acknowledgeAlert(payload.alertId, payload.notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: waterKeys.all })
    },
  })
}

export function useResolveWaterAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { alertId: number; notes?: string }) =>
      waterApi.resolveAlert(payload.alertId, payload.notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: waterKeys.all })
    },
  })
}

export function useWaterAssets() {
  return useQuery({
    queryKey: waterKeys.assets(),
    queryFn: async () => mapAssetSummaryList(await waterApi.getAssets()),
    refetchInterval: REFRESH_INTERVAL,
  })
}

export function useAssetReadings(assetId: number | null | undefined) {
  return useQuery({
    queryKey: waterKeys.assetReadings(assetId),
    queryFn: async () => mapAssetReadingsList(await waterApi.getAssetReadings(assetId as number)),
    enabled: !!assetId,
    refetchInterval: REFRESH_INTERVAL,
  })
}

export function useAssetNotes(assetId: number | null | undefined) {
  return useQuery({
    queryKey: waterKeys.assetNotes(assetId),
    queryFn: async () => mapOperationalNoteList(await waterApi.getAssetNotes(assetId as number)),
    enabled: !!assetId,
    refetchInterval: 30_000,
  })
}

export function useAddAssetNote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { assetId: number; note: string }) =>
      waterApi.addAssetNote(payload.assetId, payload.note),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: waterKeys.assetNotes(vars.assetId) })
    },
  })
}

export function useCreateIndicator() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: IndicatorIngestPayload) => waterApi.createIndicator(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: waterKeys.all })
    },
  })
}

// ─── Admin Hooks ──────────────────────────────────────────────────────────

export const adminKeys = {
  pipelineHealth: () => [...waterKeys.all, 'admin', 'pipeline-health'] as const,
}

export function usePipelineHealth() {
  return useQuery({
    queryKey: adminKeys.pipelineHealth(),
    queryFn: waterApi.getPipelineHealth,
    refetchInterval: 30_000,
  })
}