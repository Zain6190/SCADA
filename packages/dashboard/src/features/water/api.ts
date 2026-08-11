// packages/dashboard/src/features/water/api.ts
// Typed HTTP client for the AquaVision service (/water/* endpoints).
import axios from 'axios'
import { API_BASE_URL } from '@/lib/config'
import type {
  WaterOverview,
  WaterIndicator,
  WaterPrediction,
  WaterAlert,
  WaterReport,
  WaterThreshold,
  Region,
  WaterMap,
  AssetSummaryVM as AssetSummary,
  AssetTelemetryVM as AssetReading,
  OperationalNoteVM as AssetOperationalNote,
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
    const { data } = await waterClient.get('/alerts', { params })
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

  getThresholds: async (): Promise<WaterThreshold[]> => {
    const { data } = await waterClient.get('/thresholds')
    return data
  },

  createIndicator: async (payload: IndicatorIngestPayload): Promise<WaterIndicator> => {
    const { data } = await waterClient.post('/indicators', payload)
    return data
  },

  acknowledgeAlert: async (alertId: number, notes?: string): Promise<WaterAlert> => {
    const { data } = await waterClient.patch(`/alerts/${alertId}`, {
      status: 'Acknowledged',
      notes: notes || null,
    })
    return data
  },

  resolveAlert: async (alertId: number, notes?: string): Promise<WaterAlert> => {
    const { data } = await waterClient.patch(`/alerts/${alertId}`, {
      status: 'Resolved',
      notes: notes || null,
    })
    return data
  },

  getAssets: async (): Promise<AssetSummary[]> => {
    const { data } = await waterClient.get('/assets')
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
}