// packages/dashboard/src/features/water/mappers.ts
// Pure functions converting raw API contracts to safe view models.
import { normalizeSeverity, worstOf, SEVERITY_RANK, type SeverityLevel } from '@/lib/severity'
import type {
  WaterIndicator,
  WaterPrediction,
  WaterAlert,
  MapFeature,
  IndicatorVM,
  PredictionVM,
  AlertVM,
  MapFeatureVM,
  AssetSummaryVM,
  AssetTelemetryVM,
  OperationalNoteVM,
} from '@/features/water/types'

export function mapIndicator(raw: WaterIndicator): IndicatorVM {
  return {
    id: raw.id,
    regionId: raw.region_id,
    weekStart: raw.week_start_date,
    waiScore: raw.wai_score,
    severity: normalizeSeverity(raw.severity),
    surfaceWaterAreaKm2: raw.surface_water_area_km2,
    surfaceWaterChangePct: raw.surface_water_change_pct,
    rainfallMm30day: raw.rainfall_mm_30day,
    rainfallAnomaly: raw.rainfall_anomaly,
    etMm8day: raw.et_mm_8day,
    etAnomaly: raw.et_anomaly,
    dataSourceVersion: raw.data_source_version,
    dataStatus: raw.data_status,
    dataQuality: raw.data_quality,
    dataProvider: raw.data_provider,
    waiModelVersion: raw.wai_model_version,
    sourceObservedAt: raw.source_observed_at,
    lastValidatedAt: raw.last_validated_at,
  }
}

export function mapIndicatorList(raw: WaterIndicator[]): IndicatorVM[] {
  return (raw ?? []).map(mapIndicator)
}

export function mapPrediction(raw: any): PredictionVM {
  return {
    id: raw.id,
    regionId: raw.region_id,
    targetWeekStart: raw.target_week_start_date,
    modelType: raw.model_type,
    modelVersion: raw.model_version,
    predictedSeverity: normalizeSeverity(raw.predicted_severity),
    predictedWaiScore: raw.predicted_wai_score,
    confidence: raw.confidence,
  }
}

export function mapPredictionList(raw: any[]): PredictionVM[] {
  return (raw ?? []).map(mapPrediction)
}

export function mapAlert(raw: any): AlertVM {
  return {
    id: raw.id,
    regionId: raw.region_id,
    weekStartDate: raw.week_start_date,
    alertType: raw.alert_type,
    severity: normalizeSeverity(raw.severity),
    waiScore: raw.wai_score,
    rainfallAnomaly: raw.rainfall_anomaly,
    etAnomaly: raw.et_anomaly,
    surfaceWaterChangePct: raw.surface_water_change_pct,
    status: raw.status,
    createdAt: raw.created_at,
    acknowledgedAt: raw.acknowledged_at,
    resolvedAt: raw.resolved_at,
    notes: raw.notes,
  }
}

export function mapAlertList(raw: any[]): AlertVM[] {
  return (raw ?? []).map(mapAlert)
}

export function mapMapFeature(raw: MapFeature): MapFeatureVM {
  return {
    regionId: raw.properties.region_id,
    name: raw.properties.name,
    regionType: raw.properties.region_type,
    waiScore: raw.properties.wai_score,
    severity: normalizeSeverity(raw.properties.severity),
    rainfallMm30day: raw.properties.rainfall_mm_30day,
    etMm8day: raw.properties.et_mm_8day,
    geometry: raw.geometry,
  }
}

export function mapMapFeatureList(raw: MapFeature[]): MapFeatureVM[] {
  return (raw ?? []).map(mapMapFeature)
}

export function worstSeverityOf(levels: Array<SeverityLevel | null | undefined>): SeverityLevel {
  return worstOf(levels)
}

export function rankOf(level: SeverityLevel): number {
  return SEVERITY_RANK[level]
}

export function sortBySeverity<T>(
  items: T[],
  severityOf: (item: T) => SeverityLevel | null | undefined = (i: any) => i.severity,
  desc = true
): T[] {
  return [...items].sort((a, b) => {
    const diff =
      rankOf(severityOf(a) ?? 'Normal') - rankOf(severityOf(b) ?? 'Normal')
    return desc ? -diff : diff
  })
}

export function regionNameById(
  regions: Array<{ id: number; name: string }>,
  id: number | undefined
): string {
  if (!id) return '—'
  return regions.find((r) => r.id === id)?.name ?? `Region #${id}`
}

export function mapAssetTelemetry(raw: any): AssetTelemetryVM {
  return {
    id: raw.id,
    assetId: raw.asset_id,
    recordedAt: raw.recorded_at,
    reservoirLevelM: raw.reservoir_level_m,
    storagePct: raw.storage_pct,
    inflowCumecs: raw.inflow_cumecs,
    outflowCumecs: raw.outflow_cumecs,
    dischargeCumecs: raw.discharge_cumecs,
    dataStatus: raw.data_status,
    source: raw.source,
  }
}

export function mapAssetSummary(raw: any): AssetSummaryVM {
  return {
    id: raw.id,
    name: raw.name,
    assetType: raw.asset_type,
    regionId: raw.region_id,
    latest: raw.latest ? mapAssetTelemetry(raw.latest) : null,
  }
}

export function mapAssetSummaryList(raw: any[]): AssetSummaryVM[] {
  return (raw ?? []).map(mapAssetSummary)
}

export function mapAssetReadingsList(raw: any[]): AssetTelemetryVM[] {
  return (raw ?? []).map(mapAssetTelemetry)
}

export function mapOperationalNote(raw: any): OperationalNoteVM {
  return {
    id: raw.id,
    assetId: raw.asset_id,
    note: raw.note,
    createdByUserId: raw.created_by_user_id,
    createdAt: raw.created_at,
  }
}

export function mapOperationalNoteList(raw: any[]): OperationalNoteVM[] {
  return (raw ?? []).map(mapOperationalNote)
}
