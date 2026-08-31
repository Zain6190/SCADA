// packages/dashboard/src/features/water/api.ts
// Typed HTTP client for the AquaVision service (/water/* endpoints).
import axios from 'axios'
import { API_BASE_URL } from '@/lib/config'
import type {
  WaterOverview,
  WaterIndicator,
  WaterPrediction,
  WaterReport,
  Region,
  WaterMap,
  AssetSummaryVM as AssetSummary,
  AssetTelemetryVM as AssetReading,
  OperationalNoteVM as AssetOperationalNote,
  OperationalAsset,
  OperationalObservation,
  OperationalAlert,
  OperationalThreshold,
  DownstreamImpact,
  FFDObservation,
  FFDIngestResult,
  MLPrediction,
  MLTrainResult,
  MLAnomaly,
  MLAnomalyTrainResult,
  PipelineHealth,
  AssetWeeklySummary,
  ModelPerformance,
} from '@/features/water/types'

export const waterClient = axios.create({
  baseURL: `${API_BASE_URL}/water`,
  headers: { 'Content-Type': 'application/json' },
})

waterClient.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('access_token') : null
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export interface IndicatorParams {
  region_id?: number
  severity?: string
  week_start_date?: string
  limit?: number
}

export interface IndicatorIngestPayload {
  region_id: number
  week_start_date: string
  surface_water_area_km2?: number | null
  surface_water_change_pct?: number | null
  rainfall_mm_30day?: number | null
  rainfall_anomaly?: number | null
  et_mm_8day?: number | null
  et_anomaly?: number | null
  wai_score: number
  data_source_version?: string | null
  data_status?: string | null
  data_quality?: string | null
  data_provider?: string | null
  wai_model_version?: string | null
}

export const waterApi = {
  getOverview: async (): Promise<WaterOverview> => {
    const { data } = await waterClient.get('/overview')
    return data
  },

  getIndicators: async (params: IndicatorParams = {}): Promise<WaterIndicator[]> => {
    const { data } = await waterClient.get('/indicators', { params })
    return data
  },

  getPredictions: async (params: { region_id?: number; limit?: number } = {}): Promise<any[]> => {
    const { data } = await waterClient.get('/predictions', { params })
    return data
  },

  getAlerts: async (params: { status?: string; severity?: string; limit?: number } = {}): Promise<any[]> => {
    const { data } = await waterClient.get('/operational/alerts', { params })
    return data
  },

  getMapData: async (params: { week?: string; region_type?: string } = {}): Promise<WaterMap> => {
    const { data } = await waterClient.get('/map-data', { params })
    return data
  },

  getRegions: async (): Promise<Region[]> => {
    const { data } = await waterClient.get('/regions')
    return data
  },

  getReports: async (params: { scope?: string } = {}): Promise<any[]> => {
    const { data } = await waterClient.get('/reports', { params })
    return data
  },

  generateReport: async (): Promise<WaterReport> => {
    const { data } = await waterClient.post('/reports/generate')
    return data
  },

  downloadReport: async (reportId: number): Promise<Blob> => {
    const { data } = await waterClient.get(`/reports/${reportId}/download`, { responseType: 'blob' })
    return data
  },

  exportIndicatorsCsv: async (params: IndicatorParams = {}): Promise<Blob> => {
    const { data } = await waterClient.get('/export/indicators.csv', { params, responseType: 'blob' })
    return data
  },

  exportIndicatorsGeoJson: async (params: IndicatorParams = {}): Promise<Blob> => {
    const { data } = await waterClient.get('/export/indicators.geojson', { params, responseType: 'blob' })
    return data
  },

  exportRegionsGeoJson: async (): Promise<Blob> => {
    const { data } = await waterClient.get('/export/regions.geojson', { responseType: 'blob' })
    return data
  },

  createIndicator: async (payload: IndicatorIngestPayload): Promise<WaterIndicator> => {
    const { data } = await waterClient.post('/indicators', payload)
    return data
  },

  getAssets: async (): Promise<OperationalAsset[]> => {
    const { data } = await waterClient.get('/operational/assets')
    return data
  },

  getAssetReadings: async (assetId: number, limit = 60): Promise<AssetReading[]> => {
    const { data } = await waterClient.get(`/assets/${assetId}/readings`, { params: { limit } })
    return data
  },

  getAssetNotes: async (assetId: number): Promise<AssetOperationalNote[]> => {
    const { data } = await waterClient.get(`/assets/${assetId}/notes`)
    return data
  },

  addAssetNote: async (assetId: number, note: string): Promise<AssetOperationalNote> => {
    const { data } = await waterClient.post(`/assets/${assetId}/notes`, { note })
    return data
  },

  // ─── Operational (IRSA-based) API ──────────────────────────────────────

  getOperationalAssets: async (params: { asset_type?: string } = {}): Promise<OperationalAsset[]> => {
    const { data } = await waterClient.get('/operational/assets', { params })
    return data
  },

  getOperationalAsset: async (assetId: number): Promise<OperationalAsset> => {
    const { data } = await waterClient.get(`/operational/assets/${assetId}`)
    return data
  },

  getOperationalObservations: async (assetId: number, days = 7): Promise<OperationalObservation[]> => {
    const { data } = await waterClient.get(`/operational/assets/${assetId}/observations`, { params: { days } })
    return data
  },

  getOperationalAlerts: async (params: { status?: string; severity?: string; asset_id?: number; limit?: number } = {}): Promise<OperationalAlert[]> => {
    const { data } = await waterClient.get('/operational/alerts', { params })
    return data
  },

  ackOperationalAlert: async (alertId: number, performedBy = 'Operator', notes?: string): Promise<OperationalAlert> => {
    const { data } = await waterClient.post(`/operational/alerts/${alertId}/ack`, { performed_by: performedBy, notes })
    return data
  },

  resolveOperationalAlert: async (alertId: number, performedBy = 'Operator', notes?: string): Promise<OperationalAlert> => {
    const { data } = await waterClient.post(`/operational/alerts/${alertId}/resolve`, { performed_by: performedBy, notes })
    return data
  },

  investigateOperationalAlert: async (alertId: number, performedBy = 'Operator', notes?: string): Promise<OperationalAlert> => {
    const { data } = await waterClient.post(`/operational/alerts/${alertId}/investigate`, { performed_by: performedBy, notes })
    return data
  },

  escalateOperationalAlert: async (alertId: number, performedBy = 'Operator', notes?: string): Promise<OperationalAlert> => {
    const { data } = await waterClient.post(`/operational/alerts/${alertId}/escalate`, { performed_by: performedBy, notes })
    return data
  },

  getOperationalThresholds: async (): Promise<OperationalThreshold[]> => {
    const { data } = await waterClient.get('/operational/thresholds')
    return data
  },

  updateOperationalThreshold: async (thresholdId: number, payload: Partial<OperationalThreshold>): Promise<OperationalThreshold> => {
    const { data } = await waterClient.put(`/operational/thresholds/${thresholdId}`, payload)
    return data
  },

  evaluateThresholds: async (): Promise<{ assets_checked: number; new_alerts: number; alerts: Record<string, any[]> }> => {
    const { data } = await waterClient.post('/operational/evaluate')
    return data
  },

  getDownstreamImpact: async (assetId: number): Promise<DownstreamImpact> => {
    const { data } = await waterClient.get(`/operational/impact/${assetId}`)
    return data
  },

  // ─── FFD/PMD Flood Bulletin ─────────────────────────────────────────────

  getFFDObservations: async (params: { asset_id?: number; target_date?: string } = {}): Promise<FFDObservation[]> => {
    const { data } = await waterClient.get('/operational/ffd', { params })
    return data
  },

  triggerFFDIngest: async (targetDate?: string): Promise<FFDIngestResult> => {
    const params: Record<string, string> = {}
    if (targetDate) params.target_date = targetDate
    const { data } = await waterClient.post('/operational/ffd/ingest', null, { params })
    return data
  },

  // ─── ML Predictions ────────────────────────────────────────────────────────

  getMLPredictions: async (assetId: number, horizons = '7'): Promise<MLPrediction[]> => {
    const { data } = await waterClient.get(`/ml/predictions/${assetId}`, { params: { horizons } })
    return data
  },

  triggerMLTrain: async (horizons: number[] = [7]): Promise<MLTrainResult> => {
    const { data } = await waterClient.post('/ml/train', { horizons })
    return data
  },

  // ─── ML Anomaly Detection ──────────────────────────────────────────────────

  getMLAnomalies: async (assetId: number, topN = 5): Promise<MLAnomaly[]> => {
    const { data } = await waterClient.get(`/ml/anomalies/${assetId}`, { params: { top_n: topN } })
    return data
  },

  trainAnomalyDetectors: async (): Promise<MLAnomalyTrainResult> => {
    const { data } = await waterClient.post('/ml/anomalies/train')
    return data
  },

  // ─── Admin: Pipeline Health ───────────────────────────────────────────────

  getPipelineHealth: async (): Promise<PipelineHealth> => {
    const { data } = await axios.get(`${API_BASE_URL}/api/v1/admin/pipeline-health`)
    return data
  },

  // ─── Weekly Observation Summary (Analyst) ────────────────────────────────

  getWeeklySummary: async (weeks = 16, assetId?: number): Promise<AssetWeeklySummary[]> => {
    const params: Record<string, any> = { weeks }
    if (assetId) params.asset_id = assetId
    const { data } = await waterClient.get('/operational/weekly-summary', { params })
    return data
  },

  // ─── Model Performance (Analyst) ─────────────────────────────────────────

  getModelPerformance: async (): Promise<ModelPerformance[]> => {
    const { data } = await waterClient.get('/ml/model-performance')
    return data
  },

  // ─── WAI Stress Alerts ───────────────────────────────────────────────────

  getStressAlerts: async (params: { status?: string; severity?: string; region_id?: number; limit?: number } = {}): Promise<any[]> => {
    const { data } = await waterClient.get('/stress-alerts', { params })
    return data
  },

  ackStressAlert: async (id: number, performedBy = 'Operator'): Promise<any> => {
    const { data } = await waterClient.post(`/stress-alerts/${id}/ack`, { performed_by: performedBy })
    return data
  },

  resolveStressAlert: async (id: number, performedBy = 'Operator'): Promise<any> => {
    const { data } = await waterClient.post(`/stress-alerts/${id}/resolve`, { performed_by: performedBy })
    return data
  },

  // ─── ML Model Management ──────────────────────────────────────────────

  getModelMetadata: async (): Promise<any> => {
    const { data } = await waterClient.get('/ml/model-metadata')
    return data
  },

  getModelStatus: async (): Promise<any> => {
    const { data } = await waterClient.get('/ml/model-status')
    return data
  },

  trainAllModels: async (): Promise<any> => {
    const { data } = await waterClient.post('/ml/train-all')
    return data
  },

  validateAllModels: async (): Promise<any> => {
    const { data } = await waterClient.post('/ml/validate-all')
    return data
  },

  getValidationReports: async (params: { asset_id?: number; model_type?: string; limit?: number } = {}): Promise<any> => {
    const { data } = await waterClient.get('/ml/validation-reports', { params })
    return data
  },

  // ─── Model Registry ────────────────────────────────────────────────────

  getModelRegistry: async (params: { asset_id?: number; status?: string } = {}): Promise<any> => {
    const { data } = await waterClient.get('/ml/registry', { params })
    return data
  },

  getRegistrySummary: async (): Promise<any> => {
    const { data } = await waterClient.get('/ml/registry/summary')
    return data
  },

  promoteModel: async (payload: { asset_id: number; model_type?: string; horizon?: number; status: string; performed_by?: string }): Promise<any> => {
    const { data } = await waterClient.post('/ml/registry/promote', payload)
    return data
  },

  // ─── Persisted Predictions ─────────────────────────────────────────────

  getPredictionSummary: async (): Promise<any> => {
    const { data } = await waterClient.get('/ml/prediction-summary')
    return data
  },

  getDBPredictions: async (params: { asset_id?: number; horizon?: number; limit?: number } = {}): Promise<any> => {
    const { data } = await waterClient.get('/ml/predictions', { params })
    return data
  },

  runPredictions: async (): Promise<any> => {
    const { data } = await waterClient.post('/ml/run-predictions')
    return data
  },
}