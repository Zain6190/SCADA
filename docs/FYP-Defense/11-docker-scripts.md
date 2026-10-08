# 11 — Docker, Build and Helper Scripts

## 1. Services in `docker-compose.yml`

| Service | Lines | Image / build | Key configuration |
|---------|-------|---------------|-------------------|
| `db` | `:6-25` | `postgis/postgis:16-3.4` | **Optional fallback** — `DATABASE_URL` normally points at Neon (`:2-5`). Port `5433→5432`, db `ibcp_scada` (`:13`), healthcheck `pg_isready` (`:20-25`) |
| `aquavision` | `:28-70` | `ibcp-scada-aquavision:latest`, built from the root `Dockerfile` (`:30-32`) | port `8100`; `DATABASE_URL` **required** (`:40`, fails fast if missing); JWT settings `:41-43`; rate limits `:44-45`; healthcheck `curl -f http://localhost:8100/health/live`, `start_period: 120s` (`:65-70`) |
| `scheduler` | `:73-101` | same image, `command: ["python","-m","scheduler.main"]` (`:80`) | no ports; healthcheck targets the shared image port (`:94-101`) |
| `frontend` | `:103-120` | built from `packages/dashboard/Dockerfile` (`:104-106`) | port `3000`; build arg `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8100` for the browser (`:107-110`) |

Infrastructure: named volume `ibcp-pgdata` — **external** (`:122-124`) — and bridge
network `scada-net` (`:126-128`).

**Model persistence**: trained artifacts are mounted from the host so container
recreation never wipes training results (`:54-60` — `./services/aquavision-service/models`
→ `/app/models` and `./services/aquavision-service/data/models` → `/app/data/models`).
GEE credentials are mounted read-only (`:61-62`).

## 2. Images and builds

| Image | Dockerfile | Contains |
|-------|-----------|----------|
| `ibcp-scada-aquavision` (API + scheduler) | `/Dockerfile` | Python service, `ml/` code, `scheduler`, frontend-independent |
| frontend | `packages/dashboard/Dockerfile` | Node build → static `out/` served by nginx |

Commands:

```powershell
docker compose build               # rebuild both images
docker compose up -d               # start everything (scripts/Start-All.ps1 does this)
docker compose up -d scheduler     # scheduler only
docker compose logs -f scheduler   # follow job logs
docker ps --filter name=ibcp       # status table
```

> Safety rule: never run `docker compose down -v` — it deletes named volumes (data).

## 3. Environment contract (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | **yes** (`:40` `:?` guard) | Neon connection string (`sslmode=require`) |
| `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | optional | token signing (defaults `change-me-in-production` / HS256 / 480 min) |
| `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_AUTH_PER_MINUTE` | optional | 120 general, 10 auth (`:44-45`) |
| `NEXT_PUBLIC_API_BASE_URL` | build-time | baked into the static bundle (`:107-110`) |
| `POSTGRES_PASSWORD`, `GEE_*`, `SMTP_*`, `ALERT_RECIPIENTS` | optional | local db / Earth Engine / mail |

## 4. Helper scripts (`scripts/`)

| Script | Purpose | Usage |
|--------|---------|-------|
| `Start-All.ps1` | `docker compose up -d`, wait for `/health/live`, print URLs | `.\scripts\Start-All.ps1` (`-Logs` to tail scheduler) |
| `Start-Scheduler.ps1` | container mode (default) or foreground local mode | `.\scripts\Start-Scheduler.ps1 -Mode Docker\|Local` (`-Logs`) |
| `Show-Metrics.ps1` | print all model metrics (WAI, flood, RTU, PLC, anomaly) from artifacts | `.\scripts\Show-Metrics.ps1` (`-WaiOnly`) |
| `Test-API.ps1` | login + 18 endpoint checks with status/latency table | `.\scripts\Test-API.ps1` (`-WithMutations`) |
| `Query-DB.ps1` | read-only SQL via psql in `ibcp-postgis` (Neon-aware; rewrites `localhost` → `host.docker.internal`) | `.\scripts\Query-DB.ps1` / `-Tables` / `-Query "..."` |

Legacy/auxiliary: `start-all.bat` (Windows double-click start), `scripts/backup-db.bat`
(pg_dump helper), `services/aquavision-service/entrypoint.sh` (container entry: migrate,
seed, start API).

## 5. Build/verify pipeline used during development

```powershell
# 1) backend tests (services/aquavision-service)
python -m pytest tests -q                 # 422 passed, 1 skipped

# 2) frontend type-check + static build
packages\dashboard\node_modules\.bin\tsc.cmd --noEmit -p packages\dashboard\tsconfig.json
npm run build                             # next build -> out/

# 3) images
docker compose build
docker compose up -d

# 4) live checks
.\scripts\Start-All.ps1                   # waits for health
.\scripts\Test-API.ps1                    # 18/18 HTTP 200
.\scripts\Query-DB.ps1 -Tables            # data present
```

## 6. Current live state (defence machine)

| Container | Status |
|-----------|--------|
| `ibcp-api` | Up, `(healthy)` — API + Swagger on `:8100` |
| `ibcp-scheduler` | Up, `(healthy)` — heartbeat every 5 min |
| `ibcp-frontend` | Up — static UI on `:3000` |
| `ibcp-postgis` | Up, `(healthy)` — fallback PostGIS on `:5433` (primary DB is Neon) |
