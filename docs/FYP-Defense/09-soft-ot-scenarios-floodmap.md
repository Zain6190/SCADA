# 09 — Soft OT Twin, Scenarios and Flood Map

## 1. Soft OT architecture

A software twin of the SCADA/OT layer runs entirely inside the platform — no hardware is
touched. Implementation lives in the separate package `services/ot-runtime/`
(`ot_runtime/{plant, plc, rtu, interlocks, anchor, catalog, runtime, series}.py`):

| Module | Responsibility |
|--------|----------------|
| `plant.py` | asset/gate model of the 11 water structures |
| `plc.py` | soft-PLC control scan: interlocks + command/feedback slew (`plc.py:1-9`, decision at `:60`) |
| `interlocks.py` | **pure-function fail-safe gate interlocks** — `decide_interlocks` (`interlocks.py:26-37`), no I/O |
| `rtu.py` | telemetry tagging (15-min cadence model of an RTU) |
| `anchor.py` / `runtime.py` | load official IRSA/FFD state (`apply_official_anchor`, `runtime.py:75`), run the scan, expose runtime view |
| `series.py` | scenario vs official series selection, divergence notes (`series.py:139-149`) |

HTTP surface: `presentation/http/routers/ot.py` (mounted with `/water` prefix,
`main.py:258`):

| Endpoint | Line | Behaviour |
|----------|------|-----------|
| `GET /water/ot/devices`, `/tags`, `/commands` | `ot.py:68, :134, :156` | inventory of the twin |
| `GET /water/ot/status` | `ot.py:252` | mode, interlocks, coverage (live test in `Test-API.ps1`) |
| `GET /water/ot/process-view` | `ot.py:236-243` | official day vs OT reading, mode, interlocks, divergence per asset — banner: *"Software twin. Commands do not leave this process."* |
| `POST /water/ot/tick` | `ot.py:177-179` | advance the scan (`run_ot_tick(evaluate_thresholds=True)`) |
| `POST /water/ot/anchor` | `ot.py:182-193` | reload plant from latest official IRSA/FFD rows; response asserts `writes_observations: false` |
| `POST /water/ot/hmi/setpoint` | `ot.py:196-220` | virtual HMI setpoint — *"Soft PLC AO only. Never writes water_observations"*; asserts official observation ids unchanged; banner *"SIMULATION — does not control real infrastructure"* |
| `POST /water/ot/hmi/fault` | `ot.py:223-233` | inject a fault scenario (below) |

Safety invariant: commands are confined to the twin's own tables —
`water_ot_tag_values` (239,802 rows), `water_ot_divergences` (2,464),
`water_ot_process_days` (382), `water_ot_commands` (44), `water_ot_devices` (11) — and
every response repeats the SIMULATION banner (`ot.py:219, :232`).

## 2. Scenario modes and fault injection

**Mode selection** (`ot_runtime/series.py:154-156`):

```python
def flood_discharge(mode, official_discharge, scenario_discharge):
    if mode == "SCENARIO" and scenario_discharge is not None:
        return scenario_discharge, "SOFT_OT_SCENARIO"
    ...
```

* `TRACK` (default) — classification uses the official IRSA/FFD discharge; the map keeps
  the official flood category.
* `SCENARIO` — the operator's modified discharge repaints affected districts immediately
  (`flood_map.py:135-136`, `:182-183` tags the alert `ot_source: SOFT_OT_SCENARIO`).

**Fault scenarios** injectable through `POST /water/ot/hmi/fault`
(`ot.py:225`): `comms_down`, `sensor_stuck`, `actuator_jam`, `inflow_surge`, `clear`.
Each fault is exercised against interlock logic; observed divergence from the official
series accumulates in `water_ot_divergences` and appears in the weekly report section
(`reports.py:35` — mode, official date, interlocks, scenario divergence).

**Divergence accounting**: when a scenario releases materially less than the official
day's outflow, the twin produces a human-readable note, e.g. *"Soft OT scenario release
is {gap} cusecs below the IRSA day {date}"* (`ot_runtime/series.py:143-149`).

UI: `/water/ot` — process view + fault buttons (front-end hook `runScenarioFault`,
`packages/dashboard/src/features/water/...`), plus a live banner showing
`scenario_assets` count vs official tracking.

## 3. Flood map

* Endpoint: `GET /water/flood-map/territory` (`routers/flood_map.py:190-191`), built by
  `load_flood_territory` (`:42`) over `water_asset_thresholds`, `water_downstream_impacts`
  and current discharge.
* Each district carries a severity (`MODERATE/HIGH/EXTREME/CRITICAL` → alert flag,
  `flood_map.py:179`) plus `ot_mode` and `ot_source` fields, so the sidebar can show
  whether a colour comes from official data or a Soft-OT scenario (`:156-160`).
* UI: `/water/flood-map` with `flood-arrival-map-dynamic.tsx` (leaflet choropleth),
  `flood-map-sidebar.tsx` (district list, thresholds, OT attribution), and FFD arrival
  markers from `GET /water/operational/ffd/markers` (`operational.py:1082`).
* Real-time: `GET /water/stream` pushes updates; injected scenarios repaint without a
  page reload (`flood_map.py:195`).

## 4. Live demo script (90 seconds)

```powershell
$T = (curl.exe -s -X POST http://localhost:8100/auth/login -H "Content-Type: application/json" `
       -d '{\"username\":\"admin\",\"password\":\"admin123\"}' | ConvertFrom-Json).access_token
$A = "Authorization: Bearer $T"

curl.exe -s -H $A http://localhost:8100/water/ot/status              # 1) baseline
curl.exe -s -X POST -H $A -H "Content-Type: application/json" http://localhost:8100/water/ot/hmi/fault `
       -d '{\"asset_id\":1,\"kind\":\"inflow_surge\"}'                # 2) inject
curl.exe -s -H $A http://localhost:8100/water/ot/process-view        # 3) interlock/divergence visible
curl.exe -s -H $A http://localhost:8100/water/flood-map/territory    # 4) repaint in SCENARIO
curl.exe -s -X POST -H $A http://localhost:8100/water/ot/anchor      # 5) restore official state
```

Open `http://localhost:3000/water/ot` and `http://localhost:3000/water/flood-map` to see
the same transitions visually.

## 5. Verification notes

* The twin never writes official observations: anchor returns `writes_observations:false`
  (`ot.py:189`), setpoint checks observation ids before/after (`ot.py:199-218`).
* Provenance stays honest: Soft-OT rows are stored under `source_authority = SOFT_OT`
  (6,201 observations, 2026-07-29 → 2026-09-26), separate from IRSA/FFD official rows.
