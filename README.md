# IBCP-SCADA - Indus Basin Cyber-Physical SCADA System

## Overview
A unified mega system for flood management, water distribution, and agricultural intelligence in Pakistan's Indus Basin.

## Tech Stack
- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI + Python (single service: `services/aquavision-service`)
- Database: Neon cloud Postgres + PostGIS (primary — `DATABASE_URL` in the
  repo-root `.env`); optional local fallback via compose service `db`
  (Docker, external volume `ibcp-pgdata`)
- ML: XGBoost + Google Earth Engine (`services/ml-pipeline`)
- Scheduling: schedule library (in-service: `services/aquavision-service/scheduler`)

## Running the Stack

| Service | URL | How to start |
|---|---|---|
| Full stack | — | `docker compose up -d --build` |
| Dashboard | http://localhost:3000 | compose service `frontend` |
| API | http://127.0.0.1:8100 | compose service `aquavision` |
| Swagger | http://127.0.0.1:8100/docs | auto with backend |
| Database | see root `.env` `DATABASE_URL` (Neon) | primary: Neon; local fallback: compose service `db` (port 5433) |
| Scheduler | — | compose service `scheduler` (same image, `python -m scheduler.main`) |

### Quick Start
```bash
cp .env.example .env    # paste your Neon connection string as DATABASE_URL
docker compose up -d --build
```
Real credentials live only in the gitignored `.env` — share that file with
teammates directly (the repo is public; `.env.example` keeps placeholders).

### Running it yourself, without Docker

Neon is the database, so nothing needs Docker unless `DATABASE_URL` points at
localhost. `start-all.bat` reads the root `.env`, starts the backend and the
dashboard, and skips the container when the URL is a Neon one:

```bash
start-all.bat
```

**One-time setup** (only needed on a fresh clone, or after `requirements.txt`
or `package.json` change):

```bash
python -m venv services\aquavision-service\.venv
services\aquavision-service\.venv\Scripts\python -m pip install -r services\aquavision-service\requirements.txt
cd packages\dashboard && npm install
```

Copy `.env.example` to `.env` at the repo root and paste the Neon connection
string. Also drop a copy at `services\aquavision-service\.env` — the backend
loads its settings relative to its own folder, so a root-only `.env` is not
picked up when you start uvicorn by hand.

**Starting the two services** — one terminal each, and leave them running:

```bash
cd services\aquavision-service
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8100
```

```bash
cd packages\dashboard
npm run dev
```

Then open http://localhost:3000 and sign in as `admin` / `admin123` — it is a
**username**, not an email.

**Stopping:** Ctrl-C in each terminal. Do stop the backend when you finish for
the day: its keepalive holds the Neon compute awake, and the free tier budgets
100 CU-hours a month (≈400 hours at 0.25 CU). Set `DB_KEEPALIVE=false` if you
need to leave it running and can accept a slow first request after idle.

**If something looks wrong**

| Symptom | Cause |
|---|---|
| `[Errno 10048] ... bind on address ... 8100` | An older backend is still running. Stop it, or use another port. |
| First request hangs ~60s, then everything is fine | Neon was auto-suspended and is waking. Normal after a long idle. |
| `DATABASE_URL not found` | No `.env` at the repo root, or the line is commented out. |
| Dashboard loads but every panel errors | The backend is not running, or is on a port other than 8100. |

## Data Sources

| Source | Data | Status |
|--------|------|--------|
| IRSA | Dam levels, inflow/outflow | ✅ Working |
| FFD/PMD | Flood bulletins, discharge | ✅ Working |
| Soft OT | Software PLC/RTU telemetry (simulated) | ✅ Working |
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
- `GET /water/ot/devices` - Soft PLC/RTU devices
- `POST /water/ot/tick` - Advance simulated plant
- `POST /water/ot/hmi/setpoint` - Virtual HMI (simulator only)

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
