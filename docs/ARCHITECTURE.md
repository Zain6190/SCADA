# IBCP-SCADA: Complete Data & ML Architecture
# IRSA + FFD + GEE Pipeline: Storage, Processing, ML, Display

Last updated: 2026-08-15

---

## 1. Data Sources Overview

### IRSA (Indus River System Authority)
- **What**: Dam levels, inflow/outflow, river discharge, canal withdrawals, provincial releases
- **Format**: PDF daily reports
- **URL**: `http://pakirsa.gov.pk/Doc/Data{DD-MM-YYYY}.pdf`
- **Frequency**: Daily (~06:00 PKT)
- **Assets**: 11 (Tarbela, Mangla, Chashma, Kalabagh, Taunsa, Guddu, Sukkur, Kotri, Kabul@Nowshera, Chenab@Marala, Panjnad)
- **Status**: ✅ Pipeline built and tested (154 observations stored)

### PMD/FFD (Pakistan Meteorological Department - Flood Forecasting Division)
- **What**: River gauge levels, flood bulletins, discharge forecasts
- **Format**: HTML bulletins (concatenated text)
- **URL**: `https://ffd.pmd.gov.pk/bulletin/bulletin`
- **Frequency**: Daily (~06:00 PKT)
- **Assets**: 11 stations (Tarbela, Kalabagh, Chashma, Taunsa, Guddu, Sukkur, Kotri, Nowshera, Mangla, Marala, Panjnad)
- **Data**: Inflow (K cusecs), outflow (ft), flood status, forecast range, historical max
- **Status**: ✅ Pipeline built and tested (11 observations stored)

### GEE (Google Earth Engine)
- **What**: Satellite-derived features — rainfall, evapotranspiration, surface water extent, vegetation indices
- **Format**: Python API → GeoTIFF/CSV per region
- **Frequency**: Weekly (Monday 02:00 PKT)
- **Datasets**: CHIRPS, MOD16, JRC GSW, MODIS NDVI/EVI, MODIS LST, Sentinel-1 SAR
- **Status**: ❌ Not built (needs GEE account + service key)

---

## 2. Data Storage Architecture

### 2.1 IRSA Data (Operational)
```
water_assets (11 canonical assets)
    ├── water_observations (per-asset readings)
    │   ├── water_level_ft, inflow_cusecs, outflow_cusecs
    │   ├── discharge_cusecs, data_status = 'OBSERVED'
    │   └── raw_record_id → raw_source_records
    ├── raw_source_records (immutable archive)
    │   ├── raw_content (PDF bytes), content_hash (SHA-256)
    │   └── parser_version, retrieved_at
    └── water_thresholds (asset-specific limits)
        ├── warning_level_ft, danger_level_ft, critical_level_ft
        └── rate_rules, relationship_rules (JSON)
```

### 2.2 FFD/PMD Data (Flood Bulletins)
```
water_ffd_observations (per-station daily bulletins)
    ├── asset_id → water_assets
    ├── station_name, river_name
    ├── gauge_level_ft, discharge_cusecs
    ├── flood_status (BELOW_LOW|LOW|MEDIUM|HIGH|VERY_HIGH|EXCEPTIONALLY_HIGH)
    ├── forecast_trend (RISING|FALLING|STEADY)
    └── bulletin_url, content_hash
```

### 2.3 Threshold & Alert System
```
water_asset_thresholds (per-asset alert rules)
    ├── Level thresholds: warning, danger, critical
    ├── Inflow thresholds: warning, danger
    ├── Rate-of-change: watch, warning, critical (6h)
    └── Data freshness: stale_hours

water_operational_alerts (generated alerts)
    ├── alert_type, severity, status, message
    ├── triggered_value, threshold_value, reading values
    └── Workflow: NEW → ACKNOWLEDGED → INVESTIGATING → RESOLVED
```

### 2.4 River Network & Travel Times
```
water_river_network (8 segments)
    ├── upstream_asset_id, downstream_asset_id
    ├── river_name, segment_order, distance_km

water_travel_time_models (26 flow-band models)
    ├── flow_min_cusecs, flow_max_cusecs
    ├── travel_time_min/max/expected_hours
    └── confidence: MEDIUM, source: IRSA/PDMA
```

---

## 3. Processing Pipelines

### 3.1 IRSA Daily Pipeline
```
06:30 PKT: Download PDF → Archive (SHA-256) → Parse → Store → Threshold Engine → Alerts
```

### 3.2 FFD Daily Pipeline
```
06:00 PKT: Fetch HTML → Parse concatenated text → Match assets → Store → Check flood_status → Alerts
```

### 3.3 Threshold Evaluation Pipeline
```
After each ingestion: Check absolute/rate/relationship/FFD/freshness thresholds → Generate alerts
```

---

## 4. Downstream Impact Mapping

### 4.1 River Network
```
Indus: Tarbela → Kalabagh → Taunsa → Guddu → Sukkur → Kotri → Arabian Sea
Kabul: Nowshera → joins Indus at Kalabagh
Jhelum: Mangla → joins Chenab
Chenab: Marala → Khanki → Qadirabad → Trimmu → Panjnad → joins Indus
```

### 4.2 Travel Time Estimates (Flow-Band-Based)
| Segment | Flow Band (K cusecs) | Travel Time (hours) |
|---------|---------------------|---------------------|
| Tarbela → Kalabagh | 200-300 | 12-18 (expected 15) |
| Kalabagh → Taunsa | 200-300 | 20-30 (expected 25) |
| Taunsa → Guddu | 200-300 | 24-36 (expected 30) |
| Guddu → Sukkur | 100-200 | 24-36 (expected 30) |
| Sukkur → Kotri | 100-200 | 24-36 (expected 30) |
| Mangla → Marala | 40-60 | 12-18 (expected 15) |
| Marala → Panjnad | 40-60 | 24-36 (expected 30) |

---

## 5. Alert System

### 5.1 Alert Types
| Alert Type | Trigger | Severity |
|------------|---------|----------|
| LEVEL_ABOVE_WARNING | Level > warning_level_ft | WARNING |
| LEVEL_ABOVE_DANGER | Level > danger_level_ft | CRITICAL |
| HIGH_INFLOW | Inflow > 250,000 cusecs | WATCH |
| RAPID_RISE | Level rise > 1.0 ft in 6h | WARNING |
| FFD_STATUS_HIGH | FFD reports HIGH flood | CRITICAL |
| FFD_STATUS_MEDIUM | FFD reports MEDIUM flood | WARNING |
| FFD_RISING_TREND | FFD RISING + level near warning | WATCH |
| DATA_STALE | No observation in 48h | WATCH |

### 5.2 Alert Severity
| Severity | Action |
|----------|--------|
| WATCH | Monitor closely |
| ADVISORY | Supervisor review |
| WARNING | Operational action |
| CRITICAL | Emergency coordination |

---

## 6. System Status (August 2026)

| Component | Status |
|-----------|--------|
| IRSA PDF Parser | ✅ Complete (154 observations stored) |
| FFD Bulletin Parser | ✅ Complete (11 observations stored) |
| Threshold Engine | ✅ Complete (6 check types, 11 thresholds) |
| River Network | ✅ Complete (8 segments, 26 travel-time models) |
| Downstream Impact API | ✅ Complete |
| Scheduler | ✅ Complete (FFD 06:00, IRSA 06:30) |
| Frontend: Assets | ✅ Complete (mobile-friendly) |
| Frontend: Alerts | ✅ Complete |
| Frontend: FFD | ✅ Complete |
| Frontend: Asset Detail | ✅ Complete |
| GEE Pipeline | ❌ Not started |
| ML Forecasting | ❌ Not started |
| Intelligence Layer | ❌ Not started |
