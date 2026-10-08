# 07 — Alerts and Early Warning

## 1. Alert layers

The platform produces three distinct alert families:

| Family | Table | Produced by | Typical severity |
|--------|-------|-------------|------------------|
| Regional risk alerts (stress) | `aquavision.water_alerts` (59 rows) | weekly WAI pipeline + `run_risk_alerts.py` | Severe / Warning |
| Operational threshold alerts | `aquavision.water_operational_alerts` (49 rows) | `POST /water/operational/evaluate` against per-asset thresholds | CRITICAL / WARNING / … |
| Anomaly scores (advisory) | not persisted | IsolationForest per asset (`EXPERIMENTAL`) | HIGH / MODERATE / LOW |

Only the first two raise workflow items; anomalies are analyst aids (see `04-ml-models.md`).

## 2. Regional alert rules (deterministic)

Rules live in `services/ml-pipeline/scripts/run_risk_alerts.py` and read thresholds from
`aquavision.water_thresholds` at run time (`load_thresholds`, `:66-73`):

| Rule | Condition | alert_type | severity |
|------|-----------|------------|----------|
| WAI critical | `wai < th["wai_critical_min"]` (25) **or** anomaly ratio ≥ 0.6 | `WAI_CRITICAL` | Critical |
| WAI severe | `wai < th["wai_severe_min"]` (40) **or** anomaly ratio ≥ 0.55 | `WAI_SEVERE` | Severe |
| Rainfall deficit | `rainfall_anomaly < th["rainfall_deficit_pct"]` (−30 %) | `RAINFALL_DEFICIT` | Warning |
| Excess evapotranspiration | `et_anomaly ≥ et threshold` (+25 %) | `HIGH_ET` | Warning |

Rainfall/ET anomalies are computed as percent deviation from the component's own
historical mean (`run_risk_alerts.py:349-352`).

Live distribution (2026-10-05): `WAI_SEVERE` 32, `HIGH_ET` 21, `RAINFALL_DEFICIT` 6;
by status `New` 26, `ACKNOWLEDGED` 1, `RESOLVED` 32.

## 3. Workflow (queue → assign → instructions → verify)

Alert workflow router `presentation/http/routers/alert_workflow.py`:

| Step | Endpoint | Line |
|------|----------|------|
| Queue view (filter by status/region/severity) | `GET /water/alerts/queue` | `:222` |
| Timeline (full audit trail of one alert) | `GET /water/alerts/{id}/timeline` | `:320` |
| KPI counters | `GET /water/alerts/kpis` | `:506` |
| Escalation overview | `GET /water/alerts/escalations` | `:377` |
| Episode roll-up (repeating alerts grouped) | `GET /water/alerts/episodes` | `:443` |
| Assign to operator | `POST /water/alerts/{id}/assign` | `:555` |
| Issue field instruction | `POST /water/alerts/{id}/instructions` | `:574` |
| Officer accepts / progresses / reports | `POST /water/instructions/{id}/accept|progress|report` | `:611, :623, :635` |
| Supervisor verifies or rejects / waives | `POST /water/instructions/{id}/verify|reject|waive` | `:653-684` |
| Create synthetic test alert | `POST /water/alerts/test` | `:701` |

Stress-alert shortcuts (`routers/stress_alerts.py`):
`GET /water/stress-alerts` (`:48`), `POST /water/stress-alerts/{id}/ack` (`:96`),
`POST /water/stress-alerts/{id}/resolve` (`:114`).

Operational alert actions (`routers/operational.py`): investigate `:587`,
escalate `:605`, ack `:623`, resolve `:654`; evaluation trigger `POST
/water/operational/evaluate` `:773`.

Every state change appends to `aquavision.water_alert_audit_log` (117 rows) — the
timeline endpoint renders it, giving a defensible chain of custody.

## 4. SLA enforcement

`job_alert_sla_scan` runs every 5 minutes (`scheduler/main.py:519`, registered `:575`)
and escalates alerts that have exceeded their response window (assigned → escalated →
verified states tracked on the alert row: `assigned_to_user_id`, `escalated_to`,
`verified_by_user_id`).

## 5. Frontend surfaces

| Page | Purpose |
|------|---------|
| `/water/stress-alerts` | regional stress alert list + ack/resolve |
| `/water/alerts`, `/water/operator/alerts` | operational queue for operators |
| `/water/operator/tasks` | my instructions/tasks (field officers) |
| `/admin/alerts` | admin rules & audit view |

Access is permission-gated: acknowledging requires
`AQUAVISION_ACKNOWLEDGE_ALERT` (see `08-rbac.md`).

## 6. Verify live

```powershell
.\scripts\Test-API.ps1        # includes GET /water/stress-alerts and GET /water/alerts/queue
.\scripts\Query-DB.ps1 -Query "SELECT alert_type, severity, count(*) FROM aquavision.water_alerts GROUP BY 1,2 ORDER BY 3 DESC;"
.\scripts\Query-DB.ps1 -Query "SELECT status, count(*) FROM aquavision.water_alerts GROUP BY 1;"
```

Demo flow in Swagger: `POST /water/alerts/test` (creates a synthetic alert) →
`GET /water/alerts/queue` (appears as New) → `POST /water/alerts/{id}/assign` →
`GET /water/alerts/{id}/timeline` (shows every transition).
