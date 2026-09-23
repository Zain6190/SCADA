# IBCP-SCADA - Indus Basin Cyber-Physical SCADA System

## Overview
A unified mega system for flood management, water distribution, and agricultural intelligence in Pakistan's Indus Basin.

## Tech Stack
- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI + Python (single service: `services/aquavision-service`)
- Database: PostgreSQL + PostGIS (Docker, external volume `ibcp-pgdata`)
- ML: XGBoost + Google Earth Engine (`services/ml-pipeline`)
- Scheduling: schedule library (in-service: `services/aquavision-service/scheduler`)

## Running the Stack

| Service | URL | How to start |
|---|---|---|
| Full stack | — | `docker compose up -d --build` |
| Dashboard | http://localhost:3000 | compose service `frontend` |
| API | http://127.0.0.1:8100 | compose service `aquavision` |
| Swagger | http://127.0.0.1:8100/docs | auto with backend |
| Database | localhost:5433 | compose service `db` (volume `ibcp-pgdata`) |
| Scheduler | — | compose service `scheduler` (same image, `python -m scheduler.main`) |

### Quick Start
```bash
docker compose up -d --build
```

For a local (non-Docker) backend + frontend loop:
```bash
start-all.bat
```

## Data Sources

| Source | Data | Status |
|--------|------|--------|
| IRSA | Dam levels, inflow/outflow | ✅ Working |
| FFD/PMD | Flood bulletins, discharge | ✅ Working |
| GEE | Rainfall, ET, NDVI | ❌ Not configured |

## Accounts

Database-backed (PostgreSQL `shared.users` + RBAC). Bootstrap admin:

| Role | Email | Password |
|---|---|---|
| Administrator | admin@ibcp.gov.pk (login as `admin` also works) | admin123 |

All other accounts are provisioned through the admin UI
(System → Users) with roles: `admin`, `water_supervisor`, `aquavision_analyst`,
`field_officer`, `crop_analyst`, `geo_analyst`, `viewer`.

## API Endpoints

Auth / admin (all under `/auth`):
- `POST /auth/login` - JWT login (JSON `{username, password}`)
- `GET /auth/me` - current user + permissions + geo scope
- `GET /auth/users`, `PATCH /auth/users/{id}`, `POST /auth/admin/users` - admin user lifecycle
- `GET /auth/roles` - roles with permissions (admin)
- `GET/POST/PATCH /auth/operators*` - supervisor delegation (MANAGE_OPERATORS)

Water domain (`/water/*`):
- `GET /water/operational/assets` - List water assets
- `GET /water/operational/assets/{id}` - Asset detail
- `GET /water/operational/alerts` - List alerts
- `GET /water/operational/ffd` - FFD flood bulletins
- `POST /water/operational/ffd/ingest` - Trigger FFD ingestion
- `GET /water/operational/impact/{id}` - Downstream impact

Ops:
- `GET /health/live`, `GET /health/ready`
- `GET /api/v1/admin/pipeline-health` - pipeline + scheduler status

## Project Structure

```
IBCP-SCADA/
├── docker-compose.yml          # db + aquavision + scheduler + frontend
├── Dockerfile                  # single backend image (API + scheduler)
├── packages/
│   └── dashboard/              # Next.js frontend (only package)
├── services/
│   ├── aquavision-service/     # FastAPI backend (THE single backend)
│   │   ├── infrastructure/     # DB, auth, RBAC, ingestion, notifications
│   │   ├── presentation/       # HTTP routers
│   │   ├── ml/                 # prediction API
│   │   ├── scheduler/          # background jobs (same image as API)
│   │   ├── alembic/            # migrations (000 SQL + 006-014)
│   │   └── db/                 # setup_neon.py + seed scripts
│   └── ml-pipeline/            # weekly WAI/NDWI/SPI pipeline scripts
├── docs/                       # ARCHITECTURE.md and design notes
├── data/                       # local data artifacts (gitignored PDFs etc.)
├── scripts/                    # backup-db.bat
└── start-all.bat               # local dev launcher (non-Docker backend)
```

> Historical note: the abandoned second backend (`packages/backend`) and the
> standalone `services/scheduler` were consolidated into
> `services/aquavision-service` — see `docs/ARCHITECTURE.md`.
