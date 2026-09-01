# AquaVision Complete Architecture Reference

## Design Principles
- AquaVision is an **application-side** water intelligence and operations platform
- Connected to external data sources and future read-only OT telemetry
- **No PLC/RTU/gate/pump control** in current scope — decision support only
- OT and Application layers strictly separated per CISA guidelines
- Every observation carries full provenance (source, URL, hash, parser version, timestamps)

---

## Level 0 — Physical Water System
- **Dams and Reservoirs**: Tarbela, Mangla — level, storage, inflow, outflow
- **Barrages**: Chashma, Kalabagh, Taunsa, Guddu, Sukkur, Kotri — discharge, gate status
- **Rivers and Gauges**: Indus, Kabul, Chenab, Jhelum — discharge, gauge level, flood status
- **Canals and Irrigation Zones**: Withdrawals, flow monitoring
- **Pumps and Water-Control Stations**: Out of scope
- **Agricultural Fields**: Water demand (separate crop module)

## Level 1 — Field Devices and Control
- Sensors: Level, Flow, Pressure, Rainfall, Temperature, Gate Position
- PLCs, RTUs, Gate Controllers, Pump Controllers, Actuators
- **All out of scope** — external systems

### RTU vs PLC

| | PLC | RTU |
|---|---|---|
| Purpose | Local **control** | Remote **telemetry** |
| Location | Manned facility, panel | Unmanned field site |
| Scan rate | 10–100 ms | 1–60 min |
| Power | Mains | Solar / battery |
| Comms | Wired, reliable | Radio / cellular, intermittent |
| Buffering | Minimal | **Store-and-forward** (essential) |
| Protocol | Modbus TCP, EtherNet/IP | DNP3, IEC 60870-5-104 |
| In this system | Barrage gate control (Sukkur, Guddu, Taunsa) | River gauges (Kabul @ Nowshera, Chenab @ Marala) |

### Signal classes and where they land

Every field tag belongs to one of four classes. **AquaVision consumes AI and DI only** —
AO and DO are commands, and they stay in the utility's SCADA. This is an architectural
choice, not an omission.

| Class | Meaning | Signal | Column | Cadence |
|---|---|---|---|---|
| **AI** | Analog input — continuous measurement (4–20 mA) | Reservoir / gauge level | `water_level_ft` | 15 min |
| **AI** | | Inflow (rating curve) | `inflow_cusecs` | 1 h |
| **AI** | | Outflow (gate position + rating) | `outflow_cusecs` | 1 h |
| **AI** | | River discharge | `discharge_cusecs` | 15 min |
| **DI** | Discrete input — on/off status (dry contact) | Gate limit switch, pump running, power fail | *not modelled* | On change |
| **AO** | Analog output — continuous command | Gate opening setpoint, VFD speed | **out of scope** | — |
| **DO** | Discrete output — on/off command | Start pump, open gate, siren | **out of scope** | — |

A real SCADA tag is never a bare number — it is a triple of **value, timestamp, quality**.
AquaVision models all three: the value columns above, `observed_at`, and
`quality_status` (`VALID | PARTIAL | SUSPECT | STALE | INVALID | MISSING`).

### Telemetry-class ingestion

`POST /water/sensors/ingest` accepts AI readings from three registered authorities.
All three write at `source_priority=4`, behind IRSA (1) and FFD/PMD (2), so telemetry
can never displace the official record in `v_best_observations`.

| Authority | Feed | `data_origin` | Adapter |
|---|---|---|---|
| `SENSOR_API` | Live devices (future OT) | `REAL` | — direct POST |
| `SENSOR_REPLAY` | BATADAL C-Town SCADA | `SYNTHETIC` | `infrastructure/ingestion/sensor_replay.py` |
| `USGS_NWIS` | USGS instantaneous values | `SYNTHETIC` | `infrastructure/ingestion/usgs_nwis.py` |

Both replay adapters exist because IRSA and FFD/PMD publish **daily**, while several
threshold rules are written for sub-daily data. `_eval_rate_of_change` looks back 6
hours; with daily-only data that lookback resolves to the previous day's reading, so a
~24 h change is compared against a 6 h threshold and reported as "in 6h". Hourly or
15-minute telemetry is what makes `RAPID_RISE` behave as designed.

Replayed rows are **simulated signals, not Pakistani hydrology**. They validate the
ingestion path, threshold engine and alerting chain end to end at realistic cadence.
They do not validate any model against real basin behaviour.

## Level 2 — SCADA Operations
- SCADA Servers, HMI Workstations, SCADA Alarm Server, Engineering Workstation
- **All external** — AquaVision receives data, does not control

## Level 3 — OT Operations and Historian
- Industrial Historian, OT Reports, OT Monitoring, OT Backup
- **All external**

## Level 3.5 — Industrial DMZ
- OT Firewall, Read-only OPC UA Gateway, Historian Replica
- Read-only Telemetry Collector, Telemetry Message Broker
- OT Integration API, Controlled SFTP/File Exchange, Privileged Jump Host
- **Future build** — requires physical OT network

---

## External Data Sources
| Source | Data |
|--------|------|
| IRSA | Dam level, inflow, outflow, barrage discharge |
| PMD/FFD | River discharge, flood status, trend, forecast |
| Google Earth Engine | Rainfall, ET, NDVI, surface water, flood features |
| Weather APIs | Temperature, humidity, wind, forecast |
| Census/Population | Population, villages, towns, cities |
| PDMA/NDMA | Hazard maps, emergency data |
| Kaggle/Open Data | Historical research datasets |
| OT (future) | Sensor level, flow, gate position, pump status |

---

## AquaVision Ingestion Layer
```
IRSA → PDF Downloader/Parser → Raw Archive → Normalize → Validate → Quarantine
FFD  → HTML/Bulletin Parser  → Raw Archive → Normalize → Validate → Quarantine
GEE  → Feature Extractor     → Raw Archive → Normalize → Validate → Quarantine
Weather → Adapter            → Raw Archive → Normalize → Validate → Quarantine
OT   → Read-only Adapter     → Raw Archive → Normalize → Validate → Quarantine
CSV/SFTP → Adapter           → Raw Archive → Normalize → Validate → Quarantine
```

Each raw record stores: source, source_url, source_document, source_timestamp, retrieved_timestamp, parser_version, content_hash, data_origin.

---

## AquaVision Data Platform

### Tables Required
**Source data**: water_sources, raw_source_records, telemetry_sources, telemetry_tags

**Water observations**: water_assets, water_observations, water_ffd_observations, water_ffd_forecasts, water_gee_features, weather_observations, telemetry_observations

**Geography and impact**: regions, water_river_network, water_travel_time_models, water_downstream_impacts, affected_communities, critical_infrastructure

**Rules and alerts**: water_asset_thresholds, water_thresholds, water_operational_alerts, water_alert_episodes, water_alert_audit_log, notification_deliveries

**ML**: water_ml_training_examples, water_asset_forecasts, water_predictions_weekly, model_versions, validation_reports, prediction_errors, feature_definitions, dataset_versions

**Operations**: pipeline_runs, pipeline_run_stages, scheduler_heartbeats, data_quality_log, water_observation_quarantine, audit_logs

---

## AquaVision Water Intelligence

### Water Balance Engine
```
water_balance = inflow + rainfall - outflow - evaporation - other withdrawals ± storage_change
```
Display: Water gain, Water loss, Net balance, Reason for change, Confidence

### Threshold Engine
Alert categories: LEVEL_ABOVE_WARNING, LEVEL_ABOVE_DANGER, LEVEL_ABOVE_CRITICAL, HIGH_INFLOW, HIGH_DISCHARGE, RAPID_RISE, RISING_LEVEL, HIGH_INFLOW_LOW_OUTFLOW, FFD_FLOOD_HIGH, FFD_FLOOD_MEDIUM, FFD_RISING_TREND, FORECAST_DANGER_24H, FORECAST_DANGER_7D, DATA_STALE, SENSOR_ANOMALY, INVALID_DATA

Alert severity: NORMAL, WATCH, ADVISORY, WARNING, CRITICAL

### Trend and Rate-of-change Engine
- Rising/falling detection
- Rate of level rise, rate of inflow rise
- High discharge + rising trend
- High upstream flow + low downstream flow
- Upstream alert + expected travel time

### FFD Status and Forecast Engine
- Interpret FFD bulletins (20 stations per bulletin)
- Flood status classification
- Rising trend detection
- Forecast interpretation

### Evaporation/ET Analysis
- Reference ET, actual ET, potential ET
- Open water evaporation, crop ET
- ET anomaly, ET percentile
- ETc = Kc × ET0

### Rainfall and Anomaly Analysis
- Hourly, daily, 7-day, 30-day, seasonal rainfall
- Rainfall anomaly, percentile
- Upstream catchment rainfall
- Rainfall intensity
- Causes: higher inflow, reservoir rise, flash-flood risk, soil saturation, reduced infiltration

### Storage and Availability Analysis
- Reservoir storage percentage
- Dead level, normal level, warning level, danger level, critical level
- Storage condition assessment

### River Flow and Network Analysis
- Upstream/downstream discharge
- Gauge level, flow trend
- Canal withdrawals
- Historical maximum
- Travel time between assets

### Downstream Impact Engine
- Upstream → downstream asset mapping
- River segment, distance
- Flow band, travel time (min/expected/max)
- Expected arrival window
- Affected villages, towns, cities, population
- Bridges, hospitals, roads, canals, critical infrastructure
- Impact confidence

### Alert Workflow
NEW → ACKNOWLEDGED → INVESTIGATING → ESCALATED → ACTION_REQUIRED → WAITING_FOR_VERIFICATION → RESOLVED

---

## AquaVision ML Platform

### Dataset Builder
- Source-aware: SENSOR_API=1 > IRSA=1 > FFD/PMD=2 > Kaggle=3 > SYNTHETIC=4
- REAL + SYNTHETIC data separation
- Chronological splits (never leak future)

### Feature Engineering
- Lags (1h, 6h, 12h, 24h, 48h, 7d)
- Rolling averages (6h, 24h, 7d)
- Rate of change
- Seasonal features (month, day_of_year, monsoon flag)
- FFD features (flood status, trend)
- GEE features (rainfall, ET, NDVI)
- Upstream flow features
- Threshold proximity

### Models
- **XGBoost Forecasts**: Level, inflow, outflow, discharge
- **High-Flow XGBoost**: Trains on 75th+ percentile for flood events
- **Isolation Forest**: Anomaly detection
- **Flood Classification**: Threshold exceedance probability
- **Persistence Baseline**: Naive comparison

### Validation
- Walk-forward backtesting (expanding window)
- Persistence baseline comparison
- High-flow specific evaluation
- Model registry (EXPERIMENTAL → SHADOW → APPROVED → PRODUCTION → REJECTED → RETIRED)
- Data drift and model drift monitoring

---

## Application Services
- **Notifications**: Email (SMTP), SMS (future), Slack webhook, Webhook (future)
- **Reports and Exports**: PDF, CSV generation
- **GIS Map Service**: Leaflet, asset overlay, river network, risk zones
- **Audit Service**: Alert actions, data changes, user actions
- **Search and Filters**: Full-text search across observations

---

## AquaVision Backend (FastAPI :8100)

### API Groups
- **Authentication API**: Login, JWT, session management
- **Operational API**: Assets, alerts, thresholds, observations, FFD, impact
- **Forecast and ML API**: Predictions, anomalies, flood classification, training
- **Admin API**: Pipelines, validation, models, thresholds, assets
- **Health and Pipeline API**: Health checks, pipeline status, freshness
- **WebSocket/SSE Live Updates**: Real-time push for alerts and observations

---

## PostgreSQL 16 + PostGIS

### Schemas
- **shared**: Users, roles, permissions, regions, shared assets, datasets
- **aquavision**: All water intelligence tables (operational, analytics, GIS, pipeline, audit)
- **crop**: Crop features, models, predictions, alerts, reports (isolated)
- **geo**: Geo overlays, system status (isolated)
- **system**: Pipeline runs, audit logs

---

## Scheduler and Workers
- Docker-based scheduler with advisory locks
- Heartbeat monitoring
- Retry and exponential backoff
- Jobs: IRSA daily, FFD daily, GEE weekly, ML training, freshness checks

---

## Security and Administration
- **Identity**: JWT authentication, MFA (future TOTP)
- **RBAC/ABAC**: 6 roles, 13 permissions, geographic scope (NATIONAL/PROVINCE/DISTRICT/ASSET)
- **Admin Dashboard**: Users, thresholds, models, pipelines, audit
- **Secrets Management**: Environment variables, Docker secrets
- **Alembic Migrations**: Schema versioning
- **Observability**: Structured logging (structlog), metrics (future), traces (future)

---

## AquaVision Frontend (Next.js :3000)

### Required Pages
| Page | Purpose |
|------|---------|
| **Command Center** | National water overview, critical alerts, data freshness, forecast summary |
| **Water Overview** | KPI and regional status |
| **Operator Dashboard** | Assigned assets, alerts, actions |
| **Asset Detail** | Level, inflow, outflow, trends, history, thresholds |
| **Dam and Reservoir View** | Storage %, inflow/outflow balance, level thresholds, rate of rise |
| **River and Barrage View** | Flow, discharge, flood status, trend, canal withdrawals |
| **Rainfall and Evaporation** | ET, anomalies, water balance, seasonal analysis |
| **FFD Intelligence** | Status, trend, forecast, station comparison |
| **Alert Center** | Acknowledge, investigate, escalate, resolve |
| **Prediction Dashboard** | Forecast, intervals, model confidence, comparison |
| **Anomaly Dashboard** | Anomaly scores, unusual patterns |
| **Downstream Impact** | Travel time, population exposure, infrastructure |
| **GIS Map** | Assets, rivers, risk zones, real-time overlay |
| **Reports and Exports** | Generated reports, data exports |
| **Admin Dashboard** | Users, thresholds, pipelines, models, audit |
| **ML Validation** | Model performance, walk-forward results, drift |
| **Supervisor Dashboard** | Multi-region oversight, operator assignments |

---

## Final Responsibility Model
- **Sensors**: Measure water conditions
- **PLC/RTU**: Collect and locally control equipment
- **SCADA**: Supervises physical operations
- **Historian**: Stores high-frequency OT data
- **AquaVision**: Collects, validates, analyzes, predicts, alerts, maps, reports, and coordinates
- **Operator**: Investigates alerts and performs authorized actions in SCADA
- **Supervisor**: Directs operators, reviews regional risks, verifies responses
- **Admin**: Manages users, thresholds, data sources, models, pipelines, audit
- **Public/Emergency Authority**: Approves official public warnings
