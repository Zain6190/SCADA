# 06 — API and Swagger Reference

Base URL: `http://localhost:8100` — Swagger UI at **http://localhost:8100/docs**
(OpenAPI from FastAPI, title `aquavision-service`, version 1.0.0). All AquaVision
endpoints are prefixed `/water` (`main.py:238`).

## 1. Authentication

Every protected endpoint requires a JWT obtained from `POST /auth/login`
(`presentation/http/routers/auth.py:131`, request model `LoginRequest` at `:48`,
response `LoginResponse.access_token` at `:53-54`).

```powershell
$login = Invoke-RestMethod -Uri http://localhost:8100/auth/login -Method Post `
  -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}'
$H = @{ Authorization = "Bearer $($login.access_token)" }
```

Equivalent curl for PowerShell 5.1 (embedded double quotes must be backslash-escaped —
plain `'{"a":1}'` is mangled by PS argument passing; in bash/Git-Bash the plain form works):

```powershell
curl.exe -s -X POST http://localhost:8100/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
```

Demo account: `admin` / `admin123` (role `admin`; see `08-rbac.md`).

## 2. Representative endpoints (all tested live)

The suite `.\scripts\Test-API.ps1` executes exactly this set (18 requests, all HTTP 200
on 2026-10-05):

| # | Domain | Request | Proves |
|---|--------|---------|--------|
| 1 | Auth | `POST /auth/login` | credential check, JWT issuance |
| 2 | Auth | `GET /auth/me` | bearer token accepted; roles echoed |
| 3 | Health | `GET /health/live` | container liveness |
| 4 | Overview | `GET /water/overview` | KPI aggregation across sources |
| 5 | Assets | `GET /water/operational/assets` | 11 assets with thresholds/coords |
| 6 | Observations | `GET /water/operational/assets/1/observations?days=7` | time-series read path |
| 7 | ML v1 | `GET /water/ml/predictions/1` | v1 composite forecast |
| 8 | ML v2 | `GET /water/v2/predict/1` | v2 heads (discharge, stress, risk, rainfall, lead-time) |
| 9 | Anomaly | `GET /water/ml/anomalies/summary?days=30` | per-asset IsolationForest summary |
| 10 | Anomaly | `GET /water/ml/anomalies/1/history?days=30` | point-level anomaly scores |
| 11 | Model governance | `GET /water/ml/model-performance` | 99 registered model records |
| 12 | Indicators | `GET /water/indicators?limit=5` | weekly WAI rows |
| 13 | Regions | `GET /water/regions` | 21 regions |
| 14 | Alerts | `GET /water/stress-alerts?limit=5` | computed stress alerts |
| 15 | Alerts | `GET /water/alerts/queue` | workflow queue (assign/escalate state) |
| 16 | Maps | `GET /water/flood-map/territory` | district flood classification |
| 17 | Soft OT | `GET /water/ot/status` | twin mode, interlocks, scenario coverage |
| 18 | Sensors | `GET /water/sensors/status` | telemetry gateway status |

## 3. Curl examples (copy-paste)

```powershell
# 0) token (curl form verified on PowerShell 5.1; use Invoke-RestMethod if preferred)
$T = (curl.exe -s -X POST http://localhost:8100/auth/login -H "Content-Type: application/json" `
       -d '{\"username\":\"admin\",\"password\":\"admin123\"}' | ConvertFrom-Json).access_token
$A = "Authorization: Bearer $T"

# 1) overview KPIs
curl.exe -s -H $A http://localhost:8100/water/overview | ConvertFrom-Json | ConvertTo-Json -Depth 3

# 2) asset list
curl.exe -s -H $A http://localhost:8100/water/operational/assets

# 3) last 7 days of observations for asset 1 (Tarbela)
curl.exe -s -H $A "http://localhost:8100/water/operational/assets/1/observations?days=7"

# 4) prediction v1
curl.exe -s -H $A http://localhost:8100/water/ml/predictions/1

# 5) prediction v2 (revised heads)
curl.exe -s -H $A http://localhost:8100/water/v2/predict/1

# 6) anomaly summary (30 days)
curl.exe -s -H $A "http://localhost:8100/water/ml/anomalies/summary?days=30"

# 7) anomaly history for asset 1
curl.exe -s -H $A "http://localhost:8100/water/ml/anomalies/1/history?days=30"

# 8) weekly indicators
curl.exe -s -H $A "http://localhost:8100/water/indicators?limit=5"

# 9) stress alerts
curl.exe -s -H $A "http://localhost:8100/water/stress-alerts?limit=5"

# 10) alert workflow queue
curl.exe -s -H $A http://localhost:8100/water/alerts/queue

# 11) flood map territories
curl.exe -s -H $A http://localhost:8100/water/flood-map/territory

# 12) Soft OT status
curl.exe -s -H $A http://localhost:8100/water/ot/status

# 13) acknowledge a stress alert (mutation demo)
curl.exe -s -X POST -H $A "http://localhost:8100/water/stress-alerts/<id>/ack"

# 14) OpenAPI document itself (machine-readable)
curl.exe -s http://localhost:8100/openapi.json
```

Latency reference (local run, warm): health ~50 ms, overview ~1.3 s, predictions v1
~4.6 s (model load), v2 ~10 s (first call builds the overview cache), anomaly summary
~1.5 s.

## 4. Using Swagger UI

1. Open **http://localhost:8100/docs**.
2. Click **Authorize** (lock icon), enter `Bearer <token>` (or use the login request
   first and paste the `access_token`).
3. Expand any router (e.g. *ml_api*, *alert_workflow*, *ot*), **Try it out**, fill query
   parameters (`days=30`, `limit=5`), **Execute**.
4. The response shows status, schema-validated body, and latency.

Mutating calls to demonstrate workflow (all reversible):
`POST /water/stress-alerts/{id}/ack`, `POST /water/stress-alerts/{id}/resolve`,
`POST /water/alerts/{id}/assign`, `POST /water/alerts/{id}/instructions`,
`POST /water/ot/hmi/setpoint`, `POST /water/ot/hmi/fault` (scenario injection),
`POST /water/sensors/ingest`.

## 5. Error and stream conventions

* Errors: FastAPI standard `{"detail": ...}` with proper status codes (401 missing/invalid
  token, 403 forbidden by RBAC, 404 unknown id, 422 validation).
* Real-time: Server-Sent Events at `GET /water/stream` (`routers/stream.py:137`) —
  consume from the browser `EventSource`, not from Swagger.

## 6. One-command verification

```powershell
.\scripts\Test-API.ps1                  # read-only suite (18 requests)
.\scripts\Test-API.ps1 -WithMutations   # + ack / setpoint / ingest
```
