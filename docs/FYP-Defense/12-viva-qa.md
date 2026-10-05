# 12 — Viva Q&A (with honest limitations)

Twenty anticipated questions with the answers we stand behind. Items marked **⚠** are
known limitations — state them before the examiner does.

## A. Architecture and deployment

**Q1. How is the system deployed?**
Four Docker containers (`docker-compose.yml`): PostGIS (`ibcp-postgis`, fallback only),
FastAPI API (`ibcp-api`, :8100), scheduler (`ibcp-scheduler`, same image, `python -m
scheduler.main`), and nginx serving a Next.js static export (`ibcp-frontend`, :3000).
Primary database is Neon (`.env: DATABASE_URL`); the compose file fails fast if it is
missing (`docker-compose.yml:40`).

**Q2. Why FastAPI?**
Native async, dependency injection for JWT/RBAC (`Depends(get_current_user)`), and free
OpenAPI → Swagger UI for the defence (`/docs`). Router assembly is explicit in
`main.py:241-263`.

**Q3. Why the `schedule` library instead of Airflow/APScheduler/Celery?**
One process, no broker, jobs visible in ~600 lines of readable code, and concurrency is
solved with Postgres advisory locks (`scheduler/main.py:59-69`) shared with API-triggered
runs. For a defence demo, inspectability beats feature count. **⚠** single point of
failure — mitigated by the 5-minute heartbeat table and the startup catch-up job
(`main.py:265-301`).

**Q4. Where do trained models live?**
Host-mounted directories `services/aquavision-service/models/` and `data/models/`
(`docker-compose.yml:54-60`) so container rebuilds never destroy them; registry rows in
`aquavision.model_versions` + `data/models/model_metadata.json`.

## B. Data

**Q5. Which datasets are real?**
IRSA daily gauge bulletins (403 obs, through 2026-10-04), FFD/PMD (20), sensor API (6),
USGS 15-minute RTU series (59k–482k readings/site), HAI 23.05 ICS dataset for OT,
GRDC/GEE satellite features. **⚠** GLOFAS/Kaggle historical series and
`SYNTHETIC_HISTORICAL` (740 rows) fill gaps — every row keeps its `source_authority`, so
the mix is auditable (`Query-DB.ps1` prints the distribution).

**Q6. Why Neon instead of the local Postgres container?**
Always-available managed Postgres for the demo without local setup; compose still ships a
PostGIS fallback for offline work (`docker-compose.yml:2-5`).

**Q7. How do you prevent data leakage in training?**
Time-ordered splits (train before test, never shuffled) recorded per model
(`train_samples`, `test_samples` in `model_metadata.json`).

## C. Machine learning

**Q8. What is the main model?**
XGBoost flood predictor per asset per horizon: 11 assets × {3,7,14,30} days = 44
regressors (`xgb-flood-v1.2`, `n_estimators=500, max_depth=4`,
`flood_predictor.py:155-157`), plus a 7-day GradientBoosting classifier and 30-day
high-flow regressors.

**Q9. What accuracy do you claim?**
Average R² 0.4824 across the 44 regressors; Tarbela 3-day R² 0.8663; accuracy degrades
with horizon (30-day worst: −0.003). We quote per-horizon numbers, not a single figure.

**Q10. ⚠ Why does the WAI regressor trail the persistence baseline?**
Weekly WAI is close to a random walk — persistence R² 0.5214 beats the pure regressor
(0.4675). The deployed number is the **blend** (α = 0.39) at R² 0.5248, i.e. skill +0.041
over persistence. And `metrics.json` admits `"fitted_on": "test"` — α was fitted on the
test window; a production evaluation would calibrate α on a separate split.

**Q11. ⚠ The severity classifier is 46.7% accurate — is it useless?**
It never generates alerts. Alerts come from deterministic threshold rules
(`run_risk_alerts.py:11-14`: WAI < 25/40, rainfall anomaly < −30%, ET ≥ +25%). The
classifier annotates; rules decide. Its confusion matrix is published in
`metrics.json` for transparency.

**Q12. How does anomaly detection work?**
Per-asset IsolationForest over the last 370 days; anomaly ⟺ score < 0; bands
HIGH < −0.30 / MODERATE < −0.15. Scores computed on the fly (cached by
file-mtime and series fingerprint), never persisted. **⚠** flagged `EXPERIMENTAL`,
advisory only (`anomaly_detector.py:24, :36`).

**Q13. Some models are marked REJECTED — why keep them?**
Governance: weekly validation (`scheduler/main.py:363`) evaluates every model; failures
are rejected (e.g. Panjnad 30-day R² −0.003) but retained for audit, while only
approved versions can be promoted via `POST /water/registry/models/{id}/promote`
(permission-guarded, `registry.py:19`).

**Q14. What about the OT attack detector?**
ROC-AUC 0.7568 on HAI 23.05; precision 0.30 / recall 0.08 at the chosen threshold.
**⚠** low recall — positioned as a high-confidence signal generator, not a IDS replacement.

## D. Alerts, RBAC, Soft OT

**Q15. Walk me through an alert lifecycle.**
Threshold rules → `water_alerts` (New) → `GET /water/alerts/queue` → assign → field
instruction (accept → progress → report) → supervisor verify/reject → resolved; every
transition appended to `water_alert_audit_log` (117 rows) and rendered by
`GET /water/alerts/{id}/timeline`. SLA scan escalates every 5 minutes
(`scheduler/main.py:519`).

**Q16. Who can do what?**
7 roles, 18 permissions (`shared.permissions`), role→permission joins evaluated per
request (`rbac.py:33, :136`); model promotion requires
`AQUAVISION_APPROVE_REPORT` (`registry.py:19`); `system_admin/superuser/root` can never
be assigned (`auth.py:74`). **⚠** several read-only endpoints (overview, model list) are
open without a token for demo UX; all workflow/mutation endpoints return 401 without a
JWT — verified live.

**Q17. Does the Soft OT module control real equipment?**
No. Pure software twin (`services/ot-runtime/`), fail-safe interlocks are pure functions
(`interlocks.py:26-37`), every command response returns the banner *"SIMULATION — does
not control real infrastructure"* (`ot.py:219`), anchor writes `writes_observations:false`
(`ot.py:189`), and scenario rows are attributed to `source_authority = SOFT_OT`.

**Q18. What do scenarios demonstrate?**
Fault injection (`comms_down`, `sensor_stuck`, `actuator_jam`, `inflow_surge`),
TRACK vs SCENARIO discharge modes, and immediate flood-map repaint with
`ot_source: SOFT_OT_SCENARIO` attribution (`flood_map.py:182-183`) — showing the
early-warning loop end to end.

## E. Engineering quality

**Q19. How do you know it works?**
`pytest`: **422 passed, 1 skipped**; frontend type-check clean (`tsc --noEmit`), static
`next build` passes; live suite `Test-API.ps1` = 18/18 HTTP 200; DB checks
`Query-DB.ps1`; the anomaly summary endpoint was optimised from ~58 s to ~1.6 s warm
(fingerprint caches, commit `f068646`).

**Q20. ⚠ What is demo data and what would you do next?**
Crop and geo modules ship with empty/demo tables (`crop.*`, `geo.*` are 0 rows). The UI
polls instead of consuming the existing SSE stream (`/water/stream`). Next steps:
calibrate α on held-out data, retrain classifier with class weighting for Critical
recall, wire SSE into the dashboard, tighten read-endpoint auth, and add a CI pipeline
running the four verification steps in `11-docker-scripts.md §5`.

## Fast facts card

| Item | Value |
|------|-------|
| Containers | 4 (api, scheduler, frontend, postgis) |
| API / UI | `localhost:8100/docs` / `localhost:3000` (admin/admin123) |
| Tests | 422 passed, 1 skipped; 18/18 live API checks |
| Models | 44 flood regressors + 30 classifiers/high-flow + 11 anomaly IF + WAI v1.1 |
| Headline metrics | flood avg R² 0.4824; WAI blend R² 0.5248 (skill +0.041); RTU skill 0.31; OT AUC 0.757 |
| Alerts | 59 (32 WAI_SEVERE, 21 HIGH_ET, 6 RAINFALL_DEFICIT); SLA scan 5-min |
| Users | 35 accounts across 7 roles, 18 permissions |
