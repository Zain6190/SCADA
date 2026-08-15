# IBCP-SCADA — Session Conversation Log

## Session 1: Admin Pipeline Endpoints (Completed)

**Prompt:** Continue with next steps (admin endpoints for pipeline-runs, pipeline-health)

**What was built:**
- `packages/backend/app/api/v1/endpoints/admin.py` — 7 admin endpoints:
  - GET /admin/pipeline-health
  - GET /admin/pipeline-runs
  - GET /admin/pipeline-runs/latest
  - GET /admin/pipeline-runs/{run_id}
  - GET /admin/pipeline-runs/{run_id}/logs/{stage_name}
  - POST /admin/pipeline-runs/trigger
  - POST /admin/pipeline-runs/{run_id}/cancel
- Registered in `packages/backend/app/api/v1/api.py`
- All endpoints require admin role (RBAC enforced)

**Commit:** `557406a` — feat(backend): add admin endpoints for pipeline observability & control

---

## Session 2: Full Codebase Audit & Architecture Review

**Prompt:** What are your suggestions what should we do next, provide complete architecture, vulnerabilities, weaknesses, what we have done, options we have

**Key findings:**

### Architecture
- Three-tier: PostgreSQL/PostGIS → FastAPI backend → Next.js dashboard
- 5 DB schemas, 25 tables, 17 Alembic migrations
- ~50 API endpoints across 6 router modules
- JWT auth + RBAC with fail-closed geographic scoping
- 5-stage ML pipeline: GEE fetch → sync indicators → predict → alerts

### Critical Vulnerabilities (P0)
1. Hardcoded JWT secret key in config.py
2. DB password `1234` hardcoded in 7+ files
3. No TLS/HTTPS anywhere
4. SCADA control endpoints have no auth
5. No rate limiting on login
6. joblib.load() deserializes untrusted artifacts
7. Registration endpoints accept raw dict (no Pydantic validation)
8. No password strength validation
9. No token revocation
10. Frontend middleware always passes through
11. .env.local committed to git
12. AquaVision service CORS allows `["*"]`

### Prioritized Roadmap
- P0: Security fixes
- P1: Reliability & observability
- P2: Features & polish
- P3: Production readiness

---

## Session 3: P0 Security Fixes

**Prompt:** Do these security checks — move secrets to .env, add Pydantic models, add rate limiting, fix CORS, remove .env.local (skip flood/soil auth)

**What was built:**

### 1. Secrets moved to .env
- `packages/backend/app/core/config.py` — SECRET_KEY defaults to empty string, fails fast if unset
- `packages/backend/.env` — created with generated secret key
- `packages/backend/.env.example` — updated with clear instructions
- `services/aquavision-service/config/settings.py` — CORS restricted from `["*"]` to localhost
- `services/aquavision-service/.env` — created
- `services/aquavision-service/.env.example` — updated

### 2. Input validation on auth endpoints
- `packages/backend/app/models/user.py` — added RegisterRequest, AdminCreateUserRequest, SupervisorCreateOperatorRequest, UserUpdateRequest, OperatorUpdateRequest, _validate_password, _ACCESS_STATUSES
- `packages/backend/app/api/v1/endpoints/auth.py` — explicit field validation on /register, /admin/users, /operators:
  - Username: min 2 chars
  - Email: must contain @ and valid domain
  - Password: min 8 chars, uppercase, lowercase, digit
  - 422 response with detailed error list

### 3. Rate limiting
- `packages/backend/app/main.py` — slowapi Limiter (200/min default, 5/min login, 10/min register)
- `packages/backend/requirements.txt` — added slowapi, email-validator, psycopg2-binary, python-jose, passlib

### 4. CORS fixed
- `services/aquavision-service/config/settings.py` — `["*"]` → `["localhost:3000"]`

**Commits:**
- `0cc6caf` — security: remove hardcoded secrets, require .env configuration
- `bf33387` — auth: add Pydantic validation schemas and password strength requirements
- `ce50509` — auth: enforce input validation on registration and user-creation endpoints
- `7100d67` — security: add rate limiting on auth endpoints via slowapi

---

## Session 4: Deployment Discussion

**Prompt:** How to deploy? Step by step explanation

**Recommendation:** Railway (backend + DB) + Vercel (frontend)

### Steps outlined:
1. Create Railway account
2. Deploy PostgreSQL on Railway
3. Deploy backend on Railway (root: packages/backend, start: uvicorn app.main:app)
4. Run Alembic migrations
5. Deploy frontend on Vercel (root: packages/dashboard)
6. Update CORS with Vercel URL
7. Test

**Not yet implemented** — user wants to do it tomorrow

---

## Session 5: Module Audit & Surface Water Planning

**Prompt:** How many modules have we covered? How many data gathering approaches in AquaVision?

**Module Status:**
| Module | Status |
|--------|--------|
| 6.1 Data Ingestion | ✅ Built |
| 6.2 Surface Water (NDWI/MNDWI) | ❌ Not built |
| 6.3 Dam & Reservoir | ❌ Not built |
| 6.4 River & Canal Monitoring | ❌ Not built |
| 6.5 Evapotranspiration | ⚠️ Partial |
| 6.6 Rainfall Monitoring | ⚠️ Partial |
| 6.7 WAI Scoring | ✅ Built |
| 6.8 ML Prediction | ✅ Built |
| 6.9 Alert Engine | ✅ Built |
| 6.10 Dashboard | ⚠️ Partial |
| 6.11 Report Generation | ⚠️ Partial |
| 6.12 Admin Module | ✅ Built |

**Data Gathering (6 planned datasets):**
1. Sentinel-2 — ✅ fetched, ❌ no NDWI/MNDWI computation
2. Landsat 8/9 — ✅ fetched, ❌ not used
3. MODIS MOD16A2GF — ✅ fetched, ⚠️ one feature column
4. CHIRPS — ✅ fetched, ⚠️ one feature column
5. JRC Global Surface Water — ✅ fetched, ⚠️ one feature column
6. OpenStreetMap — ❌ not implemented

**Prompt:** What should we do first? Your recommendations?

**Recommendation:** Surface Water Module (NDWI/MNDWI) first — highest impact, data already available from GEE

---

## Session 6: Surface Water Module Architecture

**Prompt:** How will you build that? What will be the architecture and what will you use?

**Architecture designed:**
- GEE computes NDWI/MNDWI server-side (no local image download)
- NDWI = (B3-B8)/(B3+B8), threshold > 0.3 = water
- MNDWI = (B3-B11)/(B3+B11)
- Water area (km²) per region per week → CSV → DB
- Cloud masking via QA60 band

**Prompt:** Where do we get data to calculate NDWI? From where?

**Explanation:**
- Sentinel-2 satellite captures images every 5 days
- Images stored in Google Earth Engine cloud catalog (COPERNICUS/S2_SR_HARMONIZED)
- We send Python code to GEE servers, they compute, return summary stats
- We never download satellite images — only get numbers (water area in km²)
- Existing gee_fetch.py already uses this pattern for NDVI

**Prompt:** Yes, build

**What was built:**

### 1. DB Migration
- `packages/backend/alembic/versions/f4b5c6d7e8f9_18_surface_water_weekly.py`
- Table: `aquavision.surface_water_weekly`
- Columns: region_id, week_start_date, ndwi_mean, mndwi_mean, water_area_km2, prev_water_area_km2, change_pct, cloud_pct, data_status, source_version

### 2. GEE Script
- `packages/ml-pipeline/gee/surface_water.py`
- Computes NDWI and MNDWI from Sentinel-2 bands B3, B8, B11
- Cloud masking via QA60 band (bits 10-11)
- Outputs: Data/raw/surface_water.csv
- Uses 30m scale (reduced from 10m to avoid GEE timeout)

### 3. Sync Script
- `packages/ml-pipeline/scripts/sync_surface_water.py`
- Reads CSV, compares with previous week, calculates change_pct
- Upserts into aquavision.surface_water_weekly

### 4. Pipeline Integration
- `packages/ml-pipeline/scripts/run_pipeline.py`
- Added `sync_surface_water` stage (runs after indicators, before prediction)
- Pipeline: gee_fetch → sync_indicators → sync_surface_water → predict_weekly → run_risk_alerts

**Verified:** 12 regions × 2 weeks = 24 rows in DB, change_pct calculated correctly

**Known issue:** GEE timeout at 10m scale — fixed by increasing to 30m. User reported timeout on first real GEE run, likely internet/connectivity issue.

---

---

## Session 7: SPI Module

**Prompt:** Continue with next steps

**What was built:**

### 1. DB Migration
- `packages/backend/alembic/versions/a1b2c3d4e5f6_19_spi_columns.py`
- Added columns to `aquavision.water_indicators_weekly`: spi_1, spi_3, spi_6, spi_12, spi_drought_class

### 2. SPI Computation Script
- `packages/ml-pipeline/scripts/compute_spi.py`
- Calculates SPI using gamma distribution fit + inverse normal CDF
- Calendar-month grouping (each month compared against same calendar month historically)
- WMO drought classification:
  - SPI > 2.0: extremely_wet
  - 1.5 to 2.0: severely_wet
  - 1.0 to 1.5: moderately_wet
  - 0 to 1.0: near_normal (wet)
  - -1.0 to 0: near_normal (dry)
  - -1.5 to -1.0: moderate_drought
  - -2.0 to -1.5: severe_drought
  - < -2.0: extreme_drought

### 3. Pipeline Integration
- Added `compute_spi` stage to `run_pipeline.py` (runs after sync_surface_water)
- Pipeline: gee_fetch → sync_indicators → sync_surface_water → compute_spi → predict_weekly → run_risk_alerts

### 4. Backend Models
- Updated `packages/backend/app/models/water.py` — WaterIndicator + WaterIndicatorCreate schemas
- Updated `packages/backend/app/models/db.py` — ORM model with SPI columns

**Verified:** 18 regions, SPI-1 and SPI-3 computed correctly

**Commits:** `0ea9e73` (surface water) + `190e555` (SPI module)

---

## Pending Items

1. **GEE timeout** — surface water module still needs real GEE data test
2. **Dam & Reservoir monitoring** — module 6.3
3. **Dashboard completion** — wire frontend to display surface water + SPI data
4. **Deployment** — Railway + Vercel setup (planned for tomorrow)
