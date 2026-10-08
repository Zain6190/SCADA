# 02 — Datasets and Database

## 1. Database endpoint

The single connection string is `DATABASE_URL` in the repository `.env` file. In the
current deployment it points at a **Neon** PostgreSQL server
(`postgresql://...neon.tech/neondb?sslmode=require`). The API container reads it at
startup; the `ibcp-postgis` container (`postgis/postgis:16-3.4`) is the local/fallback
PostGIS instance mapped to host port `5433`.

Because `psql` inside `ibcp-postgis` can reach Neon as well, all inspection helpers run
through that container:

```powershell
.\scripts\Query-DB.ps1            # 8 standard read-only queries
.\scripts\Query-DB.ps1 -Tables    # table list with approximate row counts
.\scripts\Query-DB.ps1 -Query "SELECT now();"
```

## 2. Schema organisation

Schemas are assigned explicitly in the ORM layer,
`services/aquavision-service/infrastructure/db/models.py`:

| Schema | Ownership | Contents (representative tables) |
|--------|-----------|----------------------------------|
| `aquavision` | this service (read-write) | `water_observations`, `water_indicators_weekly`, `water_predictions_weekly`, `water_alerts`, `water_assets`, `water_thresholds`, `water_ot_*` (Soft OT), `pipeline_runs`, `scheduler_heartbeats` — declared at `models.py:142-148` |
| `shared` | read-only reference + RBAC | `regions`, `assets` (read-only) and `users`, `roles`, `permissions`, `user_roles`, `role_permissions` (RBAC) — `models.py:21-26` |
| `system` | platform | `audit_logs`, `pipeline_runs` (platform copy) |
| `crop`, `geo` | satellite/crop modules | `crop_*`, `geo_*` tables (currently empty/demo) |
| extension schemas | PostGIS | `tiger`, `topology`, `spatial_ref_sys` |

Schema migration is managed by Alembic (`services/aquavision-service/alembic/`,
`migrations/`).

## 3. Scale of live data (as of 2026-10-05)

Representative row counts from `.\scripts\Query-DB.ps1 -Tables`:

| Table | Rows | Meaning |
|-------|------|---------|
| `aquavision.water_ot_tag_values` | 239,802 | Soft OT tag time-series (twin) |
| `aquavision.grdc_observations` | 88,298 | GRDC gauge global records |
| `aquavision.water_observations` | 32,066 | main operational observation store |
| `aquavision.weather_forecasts` | 19,096 | weather forecast rows |
| `aquavision.gee_features` | 7,705 | Google Earth Engine features |
| `aquavision.water_indicators_weekly` | 1,249 | weekly regional WAI indicators |
| `aquavision.pipeline_runs` | 149 | scheduler run history |
| `aquavision.water_alerts` | 59 | alert records |
| `aquavision.scheduler_heartbeats` | 97 | scheduler liveness history |
| `shared.users` | 35 | portal accounts |

Observations are typed by provenance (`source_authority`), live distribution:

| Source | Observations | First | Last |
|--------|-------------|-------|------|
| GLOFAS | 18,037 | 2022-01-02 | 2026-07-01 |
| KAGGLE | 6,659 | 2022-01-04 | 2026-08-18 |
| SOFT_OT | 6,201 | 2026-07-29 | 2026-09-26 |
| SYNTHETIC_HISTORICAL | 740 | 2026-05-20 | 2026-08-17 |
| IRSA | 403 | 2026-07-22 | 2026-10-04 |
| FFD/PMD | 20 | 2026-08-18 | 2026-08-20 |
| SENSOR_API | 6 | 2026-08-21 | 2026-09-27 |

The core fact table `aquavision.water_observations` carries
`asset_id, source_id, observed_at, water_level_ft, storage_volume, storage_percent,
inflow_cusecs, outflow_cusecs, discharge_cusecs, quality_flag, source_authority,
source_content_hash` plus source lineage columns (publication time, parser version).

## 4. Training datasets on disk

| Dataset | Location | Used for |
|---------|----------|----------|
| IRSA daily gauge PDFs | `services/aquavision-service/data/raw/irsa_pdfs/` | water-level ingestion |
| Kaggle hydrology series | `services/aquavision-service/data/raw/real/kaggle/` | model training |
| USGS RTU 15-min series | `services/aquavision-service/data/raw/real/usgs/usgs_rtu_real.csv` | RTU forecast models (3 sites, 59k–482k readings) |
| HAI 23.05 ICS dataset | `data/raw/...` (`ml/artifacts/plc_metrics.json`: "HAI 23.05 (icsdataset/hai)") | PLC/OT attack detection (30 DI/DO + 56 AI/AO signals) |
| GRDC / OSM / GEE | `data/raw/grdc/`, `data/raw/real/osm/`, `gee_features` | network topology, satellite features |
| WAI feature dataset | `services/ml-pipeline/Data/features/dataset.csv` | regional WAI model training |

Historical observations also include controlled synthetic coverage
(`SYNTHETIC_HISTORICAL`) where official series did not reach; each observation keeps its
`source_authority`, so provenance is always auditable.

## 5. Ingestion paths

New data enters the database through scheduler jobs (detailed in `03-scheduler.md`):
IRSA PDF parsing (daily 01:30), FFD/PMD bulletin scraping (daily 01:00), weather refresh
(6-hourly), Google Earth Engine feature refresh (daily 04:30), inflow backfill (02:00),
plus manual/Soft-OT ingestion endpoints (`POST /water/operational/irsa/ingest`,
`POST /water/operational/ffd/ingest`, `POST /water/sensors/ingest`).

Every batch is recorded in `aquavision.pipeline_runs` (status, duration, error message,
code/config/source version), giving an end-to-end data lineage trail.

## 6. Verification commands

```powershell
.\scripts\Query-DB.ps1 -Tables                          # table inventory
.\scripts\Query-DB.ps1 -Query "SELECT source_authority, count(*) FROM aquavision.water_observations GROUP BY 1 ORDER BY 2 DESC;"
```
