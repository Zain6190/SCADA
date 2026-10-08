# 01 — System Architecture

IBCP-SCADA (AquaVision AI) is a water-monitoring and early-warning platform for Pakistan's
Indus Basin. The repository is a monorepo containing one backend service, one frontend
application, one background scheduler, and one spatial database, orchestrated by Docker
Compose.

## 1. Deployment topology

Four containers are defined in `docker-compose.yml`:

| Compose service | Container       | Image / command                        | Ports       | Purpose |
|-----------------|-----------------|----------------------------------------|-------------|---------|
| `db`            | `ibcp-postgis`  | `postgis/postgis:16-3.4` (`docker-compose.yml:7`) | `5433→5432` (`:10-11`) | PostgreSQL 16 + PostGIS spatial database |
| `aquavision`    | `ibcp-api`      | `ibcp-scada-aquavision:latest` (`:29`)  | `8100→8100` (`:35-36`) | FastAPI REST API (serves Swagger, too) |
| `scheduler`     | `ibcp-scheduler`| same image, `command: ["python","-m","scheduler.main"]` (`:73-80`) | — | Background ingestion / training / alert jobs |
| `frontend`      | `ibcp-frontend` | built from `packages/dashboard/Dockerfile` (`:104-106`) | `3000→3000` (`:113-114`) | Next.js static export on nginx |

The API declares a Docker healthcheck against `/health/live` (`docker-compose.yml:65-70`);
the scheduler does not serve HTTP, so its healthcheck targets the shared image port
(`docker-compose.yml:94-101`).

## 2. Backend layering

The backend lives in `services/aquavision-service/` and follows a layered structure:

```
services/aquavision-service/
├── main.py            # FastAPI app assembly, middleware, router mounting
├── presentation/http/routers/   # HTTP layer: request/response models, endpoints
├── application/       # use-case orchestration
├── domain/            # pure domain logic (e.g. water_classifier.py)
├── infrastructure/    # DB session, auth/JWT, external integrations
├── scheduler/         # background scheduler (see 03-scheduler.md)
├── ml/ + ml/models/   # inference code and trained artifacts
├── alembic/ migrations/          # schema migrations
└── tests/             # pytest suite (422 tests)
```

The FastAPI application is created in `services/aquavision-service/main.py:169-174`
(title/version from settings, `lifespan` hook for startup/shutdown). Rate limiting is
installed immediately afterwards (`main.py:177-178`).

## 3. Router mounting

All AquaVision endpoints share the prefix `/water` (`main.py:238`,
`WATER_PREFIX = "/water"`). Routers are mounted in `main.py:241-263`:

| Group | Routers (mounting order) |
|-------|--------------------------|
| Core | `auth` (no prefix), `health` (no prefix), `validation`, `registry`, `overview`, `map_data`, `indicators`, `predictions`, `reports` |
| Operations | `operational`, `regions`, `sensors`, `ot` (Soft OT), `channels` |
| ML | `ml_router`, `ml_v2_router` (v2), `prediction_pipeline`, `ml_api` |
| Alerts / maps | `stress_alerts`, `impact`, `flood_map`, `alert_workflow`, `stream` |

Consequently:

* Health: `GET /health/live` (`routers/health.py:17`), `GET /health/ready` (`:23`).
* Water domain: everything under `GET /water/...` (e.g. `/water/overview`,
  `/water/operational/assets`, `/water/ml/predictions/{id}`).
* Real-time notifications are exposed as Server-Sent Events at
  `GET /water/stream` (`routers/stream.py:137`).

## 4. Request/data flow

```
IRSA PDF / FFD bulletin / weather / GEE / Soft OT
        │  (scheduler jobs — see 03-scheduler.md)
        ▼
PostgreSQL 16 (schema aquavision, shared, system)   ◄── Neon in .env (see 02-datasets-db.md)
        ▲                                            │
        │ SQLAlchemy sessions                        │ JWT (PyJWT) / bcrypt
        │                                            ▼
ibcp-scheduler ── runs ──► jobs write pipeline_runs,  │
                           scheduler_heartbeats       │
                                                      ▼
ibcp-api  (FastAPI :8100) ── GET/POST /water/* ──► ibcp-frontend (nginx :3000)
                                                      │  static Next.js export
                                                      ▼
                                               Browser (recharts, leaflet)
```

The dashboard authenticates with `POST /auth/login` and stores the JWT in
`sessionStorage`; every subsequent request sends `Authorization: Bearer <token>`
(`packages/dashboard/src/features/water/api.ts:45-56`).

## 5. Frontend

`packages/dashboard` is a Next.js (App Router) application built as a **static export**:

* `output: 'export'`, `images.unoptimized: true`, `trailingSlash: true`
  (`packages/dashboard/next.config.js:7, :9, :11`).
* The build writes `out/`, which nginx serves; a trailing-slash `301` from nginx is
  therefore expected behaviour, not an error.
* Water pages live under `src/app/water/` (overview at `src/app/water/page.tsx`,
  plus `command-center`, `operator`, `analyst`, `indicators`, `regions`, `predictions`,
  `anomalies`, `ffd`, `map`, `flood-map`, `alerts`, `stress-alerts`, `sensors`, `ot`).
* Navigation and access filtering are defined in
  `packages/dashboard/src/lib/navigation.ts:58-74` and `src/lib/permissions.ts`.

## 6. Related documents

* `docs/ARCHITECTURE.md` — original architecture write-up (cross-reference, source of truth
  for background).
* `docs/prediction-module-guide.md` — prediction module details.
* `03-scheduler.md` — background jobs; `06-api-swagger.md` — live API tests;
  `11-docker-scripts.md` — build/run commands.
