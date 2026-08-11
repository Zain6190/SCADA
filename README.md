# IBCP-SCADA - Indus Basin Cyber-Physical SCADA System

## Overview
A unified mega system for flood management, water distribution, and agricultural intelligence in Pakistan's Indus Basin.

## Projects
1. **GeoVision AI** - AI-powered remote sensing for drought/flood prediction
2. **Flood SCADA** - Automated barrage gate control
3. **Soil Monitoring** - Salinity and land degradation tracking

## Tech Stack
- Frontend: Next.js + TypeScript + Tailwind
- Backend: FastAPI + Python
- ML: XGBoost + Google Earth Engine
- Real-time: MQTT + WebSockets
- Database: PostgreSQL + PostGIS (Docker)

## Running the Stack

The stack runs locally with three pieces: a Docker PostGIS database, a FastAPI backend, and a Next.js dashboard.

| Service | URL | How to start |
|---|---|---|
| Dashboard (Next.js) | http://localhost:3000 | `cd packages/dashboard && npm run dev` |
| Backend API (FastAPI) | http://localhost:8000 | `cd packages/backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| API docs (Swagger) | http://localhost:8000/docs | auto with backend |
| Database (PostGIS) | `localhost:5433` (container `ibcp-postgis`) | `docker start ibcp-postgis` |

### Database

```bash
docker start ibcp-postgis
# connect: postgres / 1234 / db ibcp_scada (host 127.0.0.1, port 5433)
```

### Backend

```bash
cd packages/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Dashboard

```bash
cd packages/dashboard
npm install
npm run dev
```

### ML Pipeline

```bash
cd packages/ml-pipeline
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Demo Accounts (login credentials)

All demo accounts log in through the dashboard at http://localhost:3000. Passwords are for **local development only** — never use in production.

| Role | Email | Password | Access level | Geographic scope |
|---|---|---|---|---|
| Administrator | `admin@ibcp.gov.pk` | `admin123` | All permissions (`SYSTEM_ADMIN`) | National |
| Analyst | `water@ibcp.gov.pk` | `water123` | Read + Manage data + Analyze | National |
| Field Officer | `field@ibcp.gov.pk` | `field123` | Read + Acknowledge alerts + Add notes | National |
| Viewer | `viewer@ibcp.gov.pk` | `viewer123` | Read-only | National |
| Operator (Sindh) | `operator@ibcp.gov.pk` | `operator123` | Read + Acknowledge alerts + Add notes | Districts 10, 11, 12 |
| Unscoped (demo) | `st4@ibcp.gov.pk` | `st4pass` | Read-only | **None** (fail-closed → 403) |

Notes:
- **Geographic scope is fail-closed**: a user with no active scope (like `st4`) is denied all regional data (HTTP 403).
- **Permission-based field filtering**: Viewers receive only core WAI/severity/surface-water fields; rainfall, ET, and anomaly fields are served only to Analyst+ access levels.
- **Audit logging**: every write and security event (logins, permission/scope denials) is recorded in `system.audit_logs`; passwords/tokens are never stored.
- **WATER_OPERATOR console** (`/water/operator`): operators (`field_officer` role) land on a scoped operations dashboard — assigned assets (reservoir level, storage, inflow/outflow/discharge via `aquavision.asset_telemetry`), scoped alert ack/resolve, and an asset operational logbook (`aquavision.asset_operational_notes`).

## Tests

```bash
cd packages/backend
python -m pytest -q   # security + schema-isolation suite
```

## Migrations

Schema changes use Alembic against the app models:

```bash
cd packages/backend
python -m alembic upgrade head          # apply migrations
python -m alembic revision --autogenerate -m "description"   # new migration
```

## Environment / Secrets

Copy `packages/backend/.env.example` to `.env` and set `SECRET_KEY`, `DATABASE_URL`, and `CORS_ORIGINS`. In production, `validate_security()` fails fast if insecure defaults are detected.