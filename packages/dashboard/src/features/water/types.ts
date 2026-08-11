// packages/dashboard/src/features/water/types.ts
// Raw contract types mirroring the AquaVision FastAPI DTOs.
import type { SeverityLevel } from '@/lib/severity'

export interface WaterOverview {
  week_start_date: string | null
  regions_monitored: number
  avg_wai_score: number
  critical_regions: number
  active_alerts: number
  national_status: string
}

export interface WaterIndicator {
  id: number
  region_id: number
  week_start_date: string
  week_number?: number | null
  year?: number | null
  surface_water_area_km2?: number | null
  surface_water_change_pct?: number | null
  rainfall_mm_30day?: number | null
  rainfall_anomaly?: number | null
  et_mm_8day?: number | null
  et_anomaly?: number | null
  wai_score?: number | null
  severity?: string | null
  data_source_version?: string | null
  data_status?: string | null
  data_quality?: string | null
  data_provider?: string | null
  wai_model_version?: string | null
  source_observed_at?: string | null
  last_validated_at?: string | null
}

export interface WaterPrediction {
  id: number
  region_id: number
  target_week_start_date: string
  model_type?: string | null
  model_version: string
  predicted_severity?: string | null
  predicted_wai_score?: number | null
  confidence?: number | null
}

export type AlertStatus = 'New' | 'Acknowledged' | 'Resolved'

export interface WaterAlert {
  id: number
  region_id: number
  week_start_date: string
  alert_type: string
  severity: string
  wai_score?: number | null
  rainfall_anomaly?: number | null
  et_anomaly?: number | null
  surface_water_change_pct?: number | null
  status: AlertStatus
  assigned_to_user_id?: number | null
  created_at: string
  acknowledged_at?: string | null
  resolved_at?: string | null
  notes?: string | null
}

export interface WaterReport {
  id: number
  week_start_date: string
  title: string
  scope: string
  region_id?: number | null
  file_path?: string | null
  generated_by_user_id?: number | null
  generated_at: string
  status: string
}

export interface WaterThreshold {
  id: number
  threshold_name: string
  value: number
  description?: string | null
  updated_at: string
}

export interface Region {
  id: number
  name: string
  code?: string | null
  type: string
  parent_region_id?: number | null
}

export interface MapFeature {
  type: string
  geometry: {
    type: string
    coordinates: any
  }
  properties: {
    region_id: number
    name: string
    region_type: string
    wai_score?: number | null
    severity?: string | null
    rainfall_mm_30day?: number | null
    et_mm_8day?: number | null
    surface_water_change_pct?: number | null
    [key: string]: any
  }
}

export interface WaterMap {
  type: string
  week?: string | null
  features: MapFeature[]
}

// View models (Post-mapper, far safer for the UI)
export interface RegionVM {
  id: number
  name: string
  code?: string | null
  type: string
}

export interface IndicatorVM {
  id: number
  regionId: number
  weekStart: string
  waiScore?: number | null
  severity?: SeverityLevel | null
  surfaceWaterAreaKm2?: number | null
  surfaceWaterChangePct?: number | null
  rainfallMm30day?: number | null
  rainfallAnomaly?: number | null
  etMm8day?: number | null
  etAnomaly?: number | null
  dataSourceVersion?: string | null
  dataStatus?: string | null
  dataQuality?: string | null
  dataProvider?: string | null
  waiModelVersion?: string | null
  sourceObservedAt?: string | null
  lastValidatedAt?: string | null
}

export interface PredictionVM {
  id: number
  regionId: number
  targetWeekStart: string
  modelType?: string | null
  modelVersion: string
  predictedSeverity?: SeverityLevel | null
  predictedWaiScore?: number | null
  confidence?: number | null
}

export interface AlertVM {
  id: number
  regionId: number
  weekStartDate: string
  alertType: string
  severity: SeverityLevel
  waiScore?: number | null
  rainfallAnomaly?: number | null
  etAnomaly?: number | null
  surfaceWaterChangePct?: number | null
  status: WaterAlert['status']
  createdAt: string
  acknowledgedAt?: string | null
  resolvedAt?: string | null
  notes?: string | null
}

export interface MapFeatureVM {
  regionId: number
  name: string
  regionType: string
  waiScore?: number | null
  severity?: SeverityLevel | null
  rainfallMm30day?: number | null
  etMm8day?: number | null
  geometry: { type: string; coordinates: any }
}

// Operational telemetry / asset view models (WATER_OPERATOR surface)
export interface AssetTelemetryVM {
  id: number
  assetId: number
  recordedAt: string
  reservoirLevelM?: number | null
  storagePct?: number | null
  inflowCumecs?: number | null
  outflowCumecs?: number | null
  dischargeCumecs?: number | null
  dataStatus?: string | null
  source?: string | null
}

export interface AssetSummaryVM {
  id: number
  name: string
  assetType: string
  regionId?: number | null
  latest?: AssetTelemetryVM | null
}

export interface OperationalNoteVM {
  id: number
  assetId: number
  note: string
  createdByUserId: string
  createdAt: string
}