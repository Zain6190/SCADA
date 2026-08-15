# IBCP-SCADA - Indus Basin Cyber-Physical SCADA System

## Overview
A unified mega system for flood management, water distribution, and agricultural intelligence in Pakistan's Indus Basin.

## Tech Stack
- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI + Python
- Database: PostgreSQL + PostGIS (Docker)
- ML: XGBoost + Google Earth Engine
- Scheduling: schedule library

## Running the Stack

| Service | URL | How to start |
|---|---|---|
| Dashboard | http://localhost:3000/IBCP-SCADA | `cd packages/dashboard && npm run dev` |
| API | http://127.0.0.1:8100 | `cd services/aquavision-service && python -m uvicorn main:app --host 127.0.0.1 --port 8100 --reload` |
| Swagger | http://127.0.0.1:8100/docs | auto with backend |
| Database | localhost:5433 | `docker start ibcp-postgis` |

### Quick Start
```bash
start-all.bat
```

## Data Sources

| Source | Data | Status |
|--------|------|--------|
| IRSA | Dam levels, inflow/outflow | ✅ Working |
| FFD/PMD | Flood bulletins, discharge | ✅ Working |
| GEE | Rainfall, ET, NDVI | ❌ Not configured |

## Demo Accounts

| Role | Email | Password |
|---|---|---|
| Administrator | admin@ibcp.gov.pk | admin123 |
| Water Analyst | water@ibcp.gov.pk | water123 |
| Crop Analyst | crop@ibcp.gov.pk | crop123 |
| Geo Analyst | geo@ibcp.gov.pk | geo123 |
| Viewer | viewer@ibcp.gov.pk | viewer123 |

## API Endpoints

- `GET /water/operational/assets` - List water assets
- `GET /water/operational/assets/{id}` - Asset detail
- `GET /water/operational/alerts` - List alerts
- `GET /water/operational/ffd` - FFD flood bulletins
- `POST /water/operational/ffd/ingest` - Trigger FFD ingestion
- `GET /water/operational/impact/{id}` - Downstream impact

## Project Structure

```
IBCP-SCADA/
├── packages/dashboard/        # Next.js frontend
├── services/
│   ├── aquavision-service/    # FastAPI backend
│   │   ├── infrastructure/    # DB, ingestion, thresholds
│   │   ├── presentation/      # API routers
│   │   └── migrations/        # SQL files
│   └── scheduler/             # Background tasks
├── docs/ARCHITECTURE.md       # System architecture
└── start-all.bat              # Start all services
```
