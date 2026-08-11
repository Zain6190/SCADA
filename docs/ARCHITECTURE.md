# IBCP-SCADA — System Architecture (Current, Verified)

> Indus Basin Cyber-Physical SCADA System · Multi-team AquaVision/Crop/Geo platform
> Last updated: reflects the running system (PostGIS + FastAPI + Next.js + RBAC + geo-scope)

---

## 1. High-Level Architecture

```
┌─────────────────────────── DATA SOURCES ───────────────────────────┐
│  Google Earth Engine   │  Field IoT Sensors  │  CSV / Seed (init.sql) │
│  (earthengine-api)     │  (MQTT, optional)   │  manual-test rows       │
└───────────┬───────────────────────┬──────────────────────┬───────────┘
            ▼                       ▼                      ▼
   ┌───────────────────────────────────────────────────────────────┐
   │   ml-pipeline  (packages/ml-pipeline)                         │
   │   GEE pulls (NDVI/NDWI) · rasterio · xgboost model training   │
   │   ── on-demand scripts + Jupyter, outputs loaded into PostGIS  │
   └───────────────────────────────┬───────────────────────────────┘
                                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │   PostGIS 16 · PostgreSQL  (Docker: ibcp-postgis :5433)      │
   │   5 logical schemas → isolation boundary                     │
   │   shared.* · aquavision.* · crop.* · geo.* · system.*        │
   └───────────────────────────────┬───────────────────────────────┘
                                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │   FastAPI Backend  (packages/backend :8000)                  │
   │   Auth (JWT/DB) · RBAC (roles→permissions) · Geo scope       │
   │   /api/v1/{auth,water,soil,flood,geovision} + /health        │
   └───────────────────────────────┬───────────────────────────────┘
                                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │   Next.js 14 Dashboard  (packages/dashboard :3000)           │
   │   Command Center "/" · AquaVision "/water" · (crop/geo pages) │
   │   React Query · Leaflet map · Recharts · RBAC module guard    │
   └───────────────────────────────────────────────────────────────┘
```

**Request flow (example: operator views water overview):**
1. Browser → `login` → stores JWT (contains `sub` = user id).
2. FE calls `GET /api/v1/water/overview` with `Bearer` token.
3. Backend decodes JWT, resolves **roles → permissions** and **geographic scope** (typed, fail-closed) from Postgres.
4. Requires `water:read` (else 403). Requires an **active scope** (else 403, fail-closed). Narrows the SQL query to the user's allowed regions; national access is explicit only.
5. Returns JSON; FE renders only authorized data.

---

## 2. Tech Stack (verified versions)

| Layer | Tech | Notes |
|-------|------|-------|
| **DB** | PostgreSQL 16 + PostGIS 3.4 (Docker `ibcp-postgis`, port **5433**) | 5 logical schemas, 23 tables |
| **Backend** | FastAPI 0.109 · SQLAlchemy 2.0 · Pydantic v2 · psycopg2 | JWT via `python-jose`, passlib/bcrypt 4.0.1 |
| **Frontend** | Next.js 14 · React 18 · TS 5 · Tailwind · react-query 5 · Leaflet · Recharts | zustand, MQTT client present |
| **ML** | earthengine-api · geopandas · rasterio · xgboost · scikit-learn | `packages/ml-pipeline` |
| **Auth/RBAC** | JWT (HS256) · DB-backed roles/permissions · geo scope | `app/core/rbac.py` |

---

## 3. Data Layer — 5 Logical Schemas (23 tables)

| Schema | Purpose | Tables | Team owner |
|--------|---------|--------|-----------|
| `shared.*` | Auth + geography foundation | users, roles, permissions, user_roles, role_permissions, **user_region_scopes**, regions, assets, datasets | Main/security |
| `aquavision.*` | Water monitoring | water_indicators_weekly, water_predictions_weekly, **water_alerts**, water_reports, water_thresholds | **AquaVision** |
| `crop.*` | Agriculture | crop_features, crop_models, crop_predictions, crop_alerts, crop_reports | Crop Yield |
| `geo.*` | Remote sensing | geo_overlays, system_status | GeoVision |
| `system.*` | Platform ops | audit_logs, pipeline_runs | Main/security |

**Key security tables:**
- `shared.user_roles` (user↔role) · `shared.role_permissions` (role↔permission)
- `shared.user_region_scopes` (typed, **fail-closed**) — `scope_type` ∈ {NATIONAL, PROVINCE, DISTRICT, ASSET}; **no active scope = denied; NATIONAL must be explicit**

---

## 4. Backend (FastAPI) — Detailed

### 4.1 Auth & RBAC pipeline (`app/core/rbac.py`)
```
JWT (sub=user_id) → User·is_active → resolve permissions → resolve scope (fail-closed) →
enforce required permission → deny (403) if no active scope → pass {user_id, permissions, region_scope}
```
- `require_permissions("water:read")` FastAPI dependency reused on every Water route.
- `get_permissions()` joins user_roles→role_permissions→permissions.
- **Geo scope is FAIL-CLOSED**: `get_region_scope()` returns an explicit scope object. A user with **no active scope is denied (403)**; `NATIONAL` access must be an explicit row; `PROVINCE`/`DISTRICT` row resolve to concrete region ids; `ASSET` resolves to its owning region. Expired/inactive scopes grant nothing.

### 4.1b Schema migrations (Alembic)
- Schema is versioned with **Alembic** (`alembic/`, `alembic.ini`), wired to `app.core.config` `DATABASE_URL`, generating only project-owned tables.
- `alembic upgrade head` provisions a fresh DB (extensions + 5 schemas + all tables); live DB is stamped at head.
- Migrations: `01` baseline schema, `02` scope fail-closed (typed `user_region_scopes`), `03` seed explicit NATIONAL scopes.
- Note: `init.sql` remains as the bootstrap/reference DDL.

### 4.2 API surface (`/api/v1/*`)
| Route | Auth gate | Notes |
|-------|-----------|-------|
| `/health` | none | liveness probe |
| `/auth/token|/me|/register|/logout` | public/ JWT | DB-backed login |
| `/water/...` (13) | `water:read` / `water:write` / `water:config` | **geo-scoped** |
| `/geovision/*` | — (scaffold) | stub |
| `/flood/*` | — (scaffold) | stub |
| `/soil/*` | — (scaffold) | stub |

### 4.3 AquaVision data model
- **Indicator = WAI composite** from: surface_water (GEE JRC), rainfall (CHIRPS), ET (MODIS)
- Severity classification: WAI <25 Critical · <40 Severe · <55 Stressed · <70 Moderate · else Normal
- Alerts (auto), predictions, reports, thresholds all persisted + served.

### 4.4 Water endpoints scoped:
```python
@router.get("/overview")
async def get_overview(auth = Depends(READ)):
    return water_service.get_overview(scope=auth["region_ids"])
```
Same pattern for regions, map-data, indicators, latest, predictions, alerts. `/alerts/{id}` returns 403 if region outside scope.

---

## 5. Frontend (Next.js) — Module/Portal layout

| Route | Module (`moduleForPath`) | RBAC |
|-------|--------------------------|------|
| `/` | command | always |
| `/water/*` | aqua | viewer/operator/analyst/supervisor/admin |
| `/crop/*` | crop | crop roles |
| `/geo/*` | geo | geo roles |
| `/system/*` | system | admin |

- `app-shell.tsx` runs `canAccess(module, role)` → renders child or `AccessDenied`.
- `src/lib/rbac.ts` maps role→modules (frontend UX guard; backend is authoritative).
- **AuthContext** exposes `user`, `hasPermission()`, `isViewer()`, `region_ids`; redirects by role.

---

## 6. Security Model (Least Privilege)

Every request enforces three independent checks:
1. **Role** — which role the user holds (`shared.users` → `user_roles` → `roles`).
2. **Permission** — which actions (read/write/config/operate) via `role_permissions`.
3. **Geographic scope** — **fail-closed**; no active scope → denied; **National access is explicit** only.

**Demo users (current):**
| Email | Role | Permission | Geo scope |
|-------|------|-----------|-----------|
| `admin@ibcp.gov.pk` / admin123 | admin | all 8 | **Explicit NATIONAL** |
| `viewer@ibcp.gov.pk` / viewer123 | viewer | water:read | **Explicit NATIONAL** |
| `operator@ibcp.gov.pk` / operator123 | field_officer | read + ack | 3 Sindh DISTRICTS |

---

## 7. ML Pipeline (`packages/ml-pipeline`)

- **Not a live server** — runs on demand (scripts + Jupyter) + model training.
- Toolset: `earthengine-api` (satellite), `geopandas`/`rasterio` (rasters), `xgboost`/`sklearn` (models).
- Outputs written into PostGIS (`crop.*`, `geo.*`, `aquavision.water_predictions_weekly`).
- Current gap: **no automated scheduler/service**; pipeline_runs + system_status tables exist for tracking when it's wired.

---

## 8. Current Status / What's LIVE

| Layer | State | Verified |
|-------|-------|----------|
| DB (PostGIS 5433) | ✅ Up | 23 tables, data |
| Backend (8000) | ✅ Healthy | `/api/v1/health` |
| Frontend (3000) | ✅ Up | `/`, `/water` |
| AquaVision data | ✅ Live | overview/map/alerts/predictions |
| RBAC roles→perms | ✅ Enforced | read 200 / write 403 / no-token 401 |
| Geo scope | ✅ Enforced | operator 3 regions vs admin 14 |
| Crop/Geo portals | ⏳ stub (empty schemas) | not populated |
| Audit logging | ⏳ table exists, unused | — |
| ML pipeline live | ⏳ scripts only | — |

---

## 9. Build & Run

```bash
# DB
docker run -d --name ibcp-postgis --restart unless-stopped \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=1234 \
  -e POSTGRES_DB=ibcp_scada -p 5433:5432 -v ibcp-pgdata:/var/lib/postgresql/data \
  postgis/postgis:16-3.4
docker exec -i ibcp-postgis psql -U postgres -d ibcp_scada < packages/backend/db/init.sql

# Backend
cd packages/backend && pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend
cd packages/dashboard && npm install && npm run dev   # :3000
```

---

## 10. Recommended Next Steps

1. **Role-based dashboards** — Analyst / Operator / Supervisor views (reuse proven RBAC + scope).
2. **Crop + Geo modules** — populate `crop.*`, `geo.*` + portals + endpoints.
3. **Audit log service** — write to `system.audit_logs` on every change (user_id, action, entity).
4. **ML pipeline wiring** — scheduled GEE pull + model training → inserts into PostGIS; use `pipeline_runs`/`system_status` for observability.
5. **Scope on region detail** — enforce scope on `/water/regions/[id]` and other portals.