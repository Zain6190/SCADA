# FYP Defence — Preparation Package

Everything needed to defend **IBCP-SCADA / AquaVision AI**: architecture, data, models,
metrics, live demos, and the questions that matter. All numbers and commands in these
files were executed on this machine (2026-10-05).

## 1. Quick start (defence machine)

```powershell
.\scripts\Start-All.ps1     # containers + health wait + prints URLs
.\scripts\Test-API.ps1      # 18/18 endpoint checks
.\scripts\Show-Metrics.ps1  # every model metric, offline
.\scripts\Query-DB.ps1      # database truth (Neon via psql tunnel)
```

* UI: `http://localhost:3000/` — login `admin` / `admin123`
* Swagger: `http://localhost:8100/docs`
* Health: `http://localhost:8100/health/live`

## 2. The 15-second pitch

> "IBCP-SCADA is a full early-warning platform for the Indus Basin: a scheduler ingests
> official IRSA and FFD bulletins daily into a cloud Postgres, forty-four per-asset
> XGBoost models forecast flood discharge up to thirty days ahead, an IsolationForest
> flags anomalous gauge behaviour, and a deterministic threshold engine raises audited,
> role-based alerts — all surfaced through a FastAPI service and a map-driven dashboard,
> with a Soft-OT twin that lets operators rehearse fault scenarios safely."

## 3. Document index

| # | File | Read it for |
|---|------|-------------|
| 01 | [01-architecture.md](01-architecture.md) | containers, FastAPI wiring, request flow |
| 02 | [02-datasets-db.md](02-datasets-db.md) | schemas, live row counts, dataset inventory |
| 03 | [03-scheduler.md](03-scheduler.md) | every job with exact times, locks, heartbeats |
| 04 | [04-ml-models.md](04-ml-models.md) | model inventory, training/validation/governance |
| 05 | [05-metrics-formulas.md](05-metrics-formulas.md) | formulas + all live metric numbers |
| 06 | [06-api-swagger.md](06-api-swagger.md) | 18 tested endpoints, curl examples, Swagger usage |
| 07 | [07-alerts.md](07-alerts.md) | alert rules, workflow, SLA, audit trail |
| 08 | [08-rbac.md](08-rbac.md) | roles, permission matrix, enforcement points |
| 09 | [09-soft-ot-scenarios-floodmap.md](09-soft-ot-scenarios-floodmap.md) | Soft-OT twin, fault scenarios, flood map |
| 10 | [10-frontend-graphs.md](10-frontend-graphs.md) | pages, chart inventory, demo path |
| 11 | [11-docker-scripts.md](11-docker-scripts.md) | compose, env contract, helper scripts |
| 12 | [12-viva-qa.md](12-viva-qa.md) | 20 Q&As incl. honest limitations |

Cross-references: `docs/ARCHITECTURE.md`, `docs/prediction-module-guide.md`.

## 4. Defence cheat sheet

**Numbers to memorise**

| | |
|---|---|
| Tests | 422 passed, 1 skipped · live API 18/18 · type-check clean |
| Models | 44 flood regressors (`xgb-flood-v1.2`), avg R² **0.4824**; best Tarbela 3-day **0.8663** |
| WAI model | blend R² **0.5248**, skill **+0.041** vs persistence (pure regressor 0.4675 — trails) |
| Anomaly | IsolationForest per asset, `iforest-v1.0`, **EXPERIMENTAL**, summary ~1.6 s (was 58 s) |
| Alerts | 59 total: 32 WAI_SEVERE, 21 HIGH_ET, 6 RAINFALL_DEFICIT · SLA scan 5-min |
| RBAC | 7 roles, 18 permissions, 35 users; workflow endpoints 401 without JWT |
| Data | 32,066 observations, 7 provenance sources, weekly indicators 1,249 rows |
| Scheduler | 15 jobs (IRSA 01:30, FFD 01:00, retrain Sun 03:00-03:58, WAI Sun 04:00) |

**Demo order (≈5 min)**

1. `Start-All.ps1` → health + URLs (deployment story).
2. Login UI → Overview (KPIs) → Indicators (WAI bands).
3. Predictions tab v1 → v2 (model revision).
4. Anomalies page (asset + regional tabs).
5. Swagger: run 2–3 curl examples from `06-api-swagger.md`.
6. Soft OT: inject `inflow_surge` → Flood Map repaint → `anchor` to restore.
7. Stress Alerts: ack + timeline (RBAC: 401 vs 200 with token).
8. `Show-Metrics.ps1` → close on honest numbers (`12-viva-qa.md` Q10/Q11/Q12).

**Honesty anchors** — say these first: WAI classifier 46.7 % (rules drive alerts, not the
classifier); blend α fitted on test; crop/geo are demo modules; several read endpoints are
open by design; anomaly model is experimental/advisory.

## 5. One-page verification

```powershell
# code
python -m pytest tests -q        # (in services/aquavision-service) 422 passed
# runtime
.\scripts\Start-All.ps1; .\scripts\Test-API.ps1
# numbers
.\scripts\Show-Metrics.ps1
# data
.\scripts\Query-DB.ps1 -Tables
```
