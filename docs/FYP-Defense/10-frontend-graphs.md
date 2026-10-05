# 10 — Frontend: Pages and Graphs

## 1. Stack

* Next.js (App Router) + TypeScript + Tailwind; icons from `lucide-react`.
* Charts: **Recharts 2.10.3** (`packages/dashboard/package.json`); maps: **Leaflet 1.9.4 /
  react-leaflet 4.2.1**.
* Built as a static export — `output: 'export'`, `images.unoptimized`,
  `trailingSlash: true` (`packages/dashboard/next.config.js:7, :9, :11`) — and served by the
  `ibcp-frontend` nginx container. A `301` adding a trailing slash is expected.
* API base URL: `src/lib/config.ts:2-5` (defaults to `http://127.0.0.1:8100`).
* HTTP client: axios with `Authorization: Bearer` from `sessionStorage`
  (`src/features/water/api.ts:45-56`); login call
  `POST ${API_URL}/auth/login` (`src/context/AuthContext.tsx:103`).

## 2. Navigation map

Defined in `src/lib/navigation.ts` (`:51` portal; water module `:58-74`;
crop `:82-84`; geo `:92-94`; system `:102-107`; admin `:115-121`).

| Group | Pages (URL) |
|-------|-------------|
| Operational | `/water/command-center`, `/water/operator`, `/water/operator/assets`, `/water/operator/alerts`, `/water/operator/tasks`, `/water/stress-alerts`, `/water/sensors`, `/water/ot` |
| Analysis | `/water` (overview), `/water/analyst`, `/water/indicators`, `/water/regions`, `/water/predictions`, `/water/anomalies`, `/water/ffd` |
| Maps | `/water/map` (live), `/water/flood-map` |
| Admin | `/admin`, `/admin/pipelines`, `/admin/alerts`, `/admin/assets`, `/admin/validation`, `/admin/registry`, `/admin/impact` |
| System | `/reports`, `/system`, `/system/audit`, `/system/team`, `/system/users`, `/system/access-requests` |

Unauthenticated visits are redirected to `/login` (`AuthContext.tsx:27`).

## 3. Chart inventory (every Recharts usage)

| Page / component | File | Charts |
|------------------|------|--------|
| Water overview KPIs | `src/features/water/overview-charts.tsx` | AreaChart (level/inflow history), LineChart (forecast), BarChart (severity distribution), `ReferenceLine` for thresholds (`:9-21`) |
| Region detail | `src/app/water/regions/[id]/client.tsx` | multi-series trend of weekly indicators |
| Predictions (v2 tab) | `src/app/water/predictions/v2-tab.tsx` | discharge/stress forecast with CI band |
| Anomalies (asset tab) | `src/app/water/anomalies/asset-tab.tsx` | scored series — flagged points coloured by isolation score + threshold band |
| Anomalies (regional tab) | `src/app/water/anomalies/regional-tab.tsx` | rainfall/ET anomaly bars per week |
| Indicators | `src/app/water/indicators/page.tsx` | WAI trend + SPI/sm bars |
| Asset detail | `src/app/water/operator/assets/[id]/client.tsx` | operational time-series |
| Crop module | `src/app/crop/{page,regions/page,historical/page}.tsx` | yield bars, regional comparison, historical series |
| Geo module | `src/app/geo/{page,regions/page,ndvi/page}.tsx` | NDVI index lines, regional index |

Maps (Leaflet, not Recharts): `src/features/water/water-map-dynamic.tsx` (live map),
`flood-arrival-map-dynamic.tsx` + `flood-map-sidebar.tsx` (flood map — see
`09-soft-ot-scenarios-floodmap.md`).

## 4. Data-fetch patterns

| Pattern | Where | Notes |
|---------|-------|-------|
| KPI aggregation | `GET /water/overview` → overview page | single round-trip, server-side joins |
| Asset drill-down | `GET /water/operational/assets/{id}/observations?days=7` | charts bound to `days` selector |
| Model outputs | `GET /water/ml/predictions/{id}` (v1), `/water/v2/predict/{id}` (v2 tabs) | latency ~4.6 s / ~10 s first call — skeleton loaders shown |
| Anomaly summary/history | `/water/ml/anomalies/summary`, `.../{id}/history` | fingerprint cache keeps summary ~1.5 s |
| Streaming | backend exposes `GET /water/stream` (SSE) | the current UI polls/refetches instead of subscribing |
| Alerts workflow | `/water/alerts/queue` (+ assign/instructions) | requires JWT (401 otherwise) |

## 5. Defence demo path (2 minutes)

1. `http://localhost:3000/login` → `admin` / `admin123`.
2. **Overview** (`/water`) — KPI cards + area/bar charts (what, at a glance).
3. **Indicators** (`/water/indicators`) — WAI trend and severity bands (`05-metrics-formulas.md`).
4. **Predictions** (`/water/predictions`) — switch v1/v2 tabs to show the model revision.
5. **Anomalies** (`/water/anomalies`) — asset tab with isolation scores; regional tab with
   rainfall/ET anomalies feeding stress alerts.
6. **Flood Map** (`/water/flood-map`) — district classification; then **Soft OT**
   (`/water/ot`) — inject `inflow_surge`, watch the flood map repaint in scenario mode.
7. **Alerts** (`/water/stress-alerts`, `/water/alerts`) — ack flow with timeline.

## 6. Verification

```powershell
.\scripts\Start-All.ps1     # prints http://localhost:3000/
.\scripts\Test-API.ps1      # the same endpoints the charts consume
```

Static-export check: `npm run build` (inside `packages/dashboard`) emits `out/` — the
nginx image copies that directory; type-check with
`packages\dashboard\node_modules\.bin\tsc.cmd --noEmit -p packages\dashboard\tsconfig.json`.
