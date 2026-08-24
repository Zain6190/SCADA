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

// ─── Operational (IRSA-based) Types ────────────────────────────────────────

export interface OperationalAsset {
  id: number
  canonical_name: string
  asset_type: string
  river?: string | null
  province?: string | null
  latitude?: number | null
  longitude?: number | null
  capacity_maf?: number | null
  normal_level_ft?: number | null
  warning_level_ft?: number | null
  critical_level_ft?: number | null
  is_active: boolean
  current_level_ft?: number | null
  current_inflow?: number | null
  current_outflow?: number | null
  current_discharge?: number | null
  last_observed_at?: string | null
  data_age_hours?: number | null
  active_alert_count: number
  highest_severity?: string | null
}

export interface OperationalObservation {
  id: number
  asset_id: number
  observed_at: string
  water_level_ft?: number | null
  inflow_cusecs?: number | null
  outflow_cusecs?: number | null
  discharge_cusecs?: number | null
  upstream_discharge_cusecs?: number | null
  downstream_discharge_cusecs?: number | null
  data_status: string
  quality_flag?: string | null
}

export interface OperationalAlert {
  id: number
  asset_id: number
  asset_name?: string | null
  alert_type: string
  severity: string
  status: string
  message: string
  triggered_value?: number | null
  threshold_value?: number | null
  reading_level_ft?: number | null
  reading_inflow_cusecs?: number | null
  reading_outflow_cusecs?: number | null
  reading_discharge_cusecs?: number | null
  rate_of_change_ft_6h?: number | null
  created_at: string
  acknowledged_at?: string | null
  resolved_at?: string | null
  notes?: string | null
  episode_id?: number | null
  alert_source?: string | null
  // Downstream impact
  downstream_impact_summary?: string | null
  downstream_population_exposed?: number | null
  downstream_bridges_at_risk?: number | null
  downstream_hospitals_at_risk?: number | null
  downstream_furthest_asset?: string | null
  downstream_furthest_arrival_hours?: number | null
  // Flood classification
  flood_probability?: number | null
  flood_severity?: string | null
  flood_confidence?: number | null
  flood_recommendation?: string | null
}

export interface OperationalThreshold {
  id: number
  asset_id: number
  asset_name?: string | null
  warning_level_ft?: number | null
  danger_level_ft?: number | null
  critical_level_ft?: number | null
  warning_inflow?: number | null
  danger_inflow?: number | null
  warning_discharge?: number | null
  danger_discharge?: number | null
  level_rise_watch_6h?: number | null
  level_rise_warning_6h?: number | null
  level_rise_critical_6h?: number | null
  stale_hours_warning: number
  stale_hours_critical: number
  is_active: boolean
  notes?: string | null
}

// ─── Downstream Impact Types ────────────────────────────────────────────────

export interface DownstreamSegment {
  segment_id: number
  river_name: string
  upstream_asset_id: number
  upstream_asset_name: string
  downstream_asset_id: number
  downstream_asset_name: string
  distance_km?: number | null
  segment_order: number
  travel_time_min_hours?: number | null
  travel_time_max_hours?: number | null
  travel_time_expected_hours?: number | null
  travel_time_confidence?: string | null
  arrival_window_min?: string | null
  arrival_window_expected?: string | null
  arrival_window_max?: string | null
  downstream_level_ft?: number | null
  downstream_discharge?: number | null
  downstream_alert_severity?: string | null
  segment_status: string
  data_source: string
}

export interface DownstreamImpact {
  source_asset_id: number
  source_asset_name: string
  source_release_cusecs?: number | null
  source_level_ft?: number | null
  river_name: string
  chain: DownstreamSegment[]
  total_distance_km?: number | null
  total_travel_time_hours?: number | null
}

// ─── FFD/PMD Flood Bulletin Types ──────────────────────────────────────────

export interface FFDObservation {
  id: number
  asset_id?: number | null
  station_name: string
  river_name?: string | null
  observed_at: string
  gauge_level_ft?: number | null
  discharge_cusecs?: number | null
  flood_status: string
  forecast_trend: string
  forecast_range?: string | null
  historical_max?: number | null
  created_at: string
}

export interface FFDIngestResult {
  date: string
  parsed: number
  stored: number
  skipped: number
  error?: string | null
}

export interface MLPrediction {
  asset_id: number
  asset_name: string
  prediction_date: string
  horizon_days: number
  predicted_level_ft?: number | null
  lower_bound?: number | null
  upper_bound?: number | null
  risk_score: number
  risk_level: string
  exceeds_warning: boolean
  exceeds_danger: boolean
  model_version: string
  model_status: string
  feature_importance: Record<string, number>
}

export interface MLTrainResult {
  models_trained: number
  results: Array<{
    asset_id?: number
    horizon?: number
    samples?: number
    mae?: number
    rmse?: number
    r2?: number
    error?: string
  }>
}

export interface MLAnomaly {
  asset_id: number
  asset_name: string
  observed_at: string
  anomaly_score: number
  is_anomaly: boolean
  anomaly_features: string[]
  severity: string
  model_version: string
  model_status: string
  details: {
    level_ft: number
    inflow_cusecs: number
    outflow_cusecs: number
  }
}

export interface MLAnomalyTrainResult {
  models_trained: number
  results: Array<{
    asset_id: number
    asset_name: string
    samples: number
    features: number
    anomalies_detected: number
  }>
}

// ─── Weekly Observation Summary (Analyst Workspace) ──────────────────────

export interface WeeklyObservationRow {
  asset_id: number
  asset_name: string
  river?: string | null
  province?: string | null
  week_start: string
  observations: number
  avg_level_ft?: number | null
  avg_inflow?: number | null
  avg_outflow?: number | null
  avg_discharge?: number | null
  max_inflow?: number | null
  min_inflow?: number | null
  data_sources: string[]
  data_origins: string[]
}

export interface AssetWeeklySummary {
  asset_id: number
  asset_name: string
  river?: string | null
  province?: string | null
  total_observations: number
  date_range: string
  weeks: WeeklyObservationRow[]
}

// ─── Model Performance (Analyst Workspace) ───────────────────────────────

export interface ModelPerformance {
  asset_id: number
  asset_name: string
  model_type: string
  model_status: string
  trained_at?: string | null
  saved_at?: string | null
  samples?: number | null
  train_samples?: number | null
  test_samples?: number | null
  r2?: number | null
  mae?: number | null
  rmse?: number | null
  mape?: number | null
  accuracy?: number | null
  auc?: number | null
  f1?: number | null
  precision?: number | null
  recall?: number | null
  feature_importance: Record<string, number>
  horizon_days?: number | null
  model_version?: string | null
  model_file: string
}

// ─── Admin Types ──────────────────────────────────────────────────────────

export interface PipelineHealth {
  api_status: string
  scheduler_status: string
  last_irsa_run: {
    status: string | null
    run_id: string | null
    completed_at: string | null
    records_stored: number | null
  } | null
  last_ffd_run: {
    status: string | null
    run_id: string | null
    completed_at: string | null
    records_stored: number | null
  } | null
  data_freshness: {
    irsa_hours: number | null
    ffd_hours: number | null
  }
}