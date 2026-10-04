# AquaVision Model Registry — Lifecycle & Validation Design (UC-9)
# ================================================
# Created: 2026-10-04
# Status: BUILT & VERIFIED (2026-10-04) — see §10 Build status
#
# Grounded in what already exists:
#   - aquavision.model_versions / validation_reports / prediction_errors
#     (alembic migration 012, applied)
#   - ModelStatus + ModelRegistry.VALID_TRANSITIONS
#     (ml/validation/model_registry.py)
#   - GET/POST /water/registry/models[/{id}/approve|promote|reject]
#     (presentation/http/routers/registry.py)
#   - Walk-forward scorers: ml/validation/validation_framework.py (regression),
#     scripts/validate_all_models.py::walk_forward_classifier (classifier)
#   - Scheduler chain: job_retrain_all_models (Sun 03:30 UTC) →
#     job_validate_all_models (Sun 03:45) → job_register_models (Sun 03:58)
#   - Serving gates in ml/models/prediction_v2.py + ml/prediction_api.py
#   - Dashboard: /admin/registry board, /admin/validation reports page
#   - Permission AQUAVISION_APPROVE_REPORT (granted to admin, water_supervisor)
#
# Design principle: evaluation earns trust in STAGES, a HUMAN always promotes
# to production, and REJECTED is the only status that changes what serves.
# The registry is evidence — the model file on disk keeps its own schedule.

---

## 1. Personas (real roles in the DB)

| Role | Count | Job in the registry loop |
|---|---|---|
| `admin` | 2 | Holds `AQUAVISION_APPROVE_REPORT`: approves, promotes, rejects; audits who signed what |
| `water_supervisor` | 5 | Also holds the approve permission: reviews shadow metrics, promotes fit models |
| `aquavision_analyst` | 1 | Owns validation: reads walk-forward reports, explains failures, requests rejections |
| `field_officer` / `viewer` | 25 | Read-only (registry board shows, cannot act) |

Permission rule: **every status change records `approved_by` + `approved_at`**
(only stamped on APPROVED, per `ModelRegistry.transition`) and is reachable
only through the guarded endpoints — no silent status edits.

---

## 2. Lifecycle state model

```
EXPERIMENTAL ──walk-forward SHADOW──► SHADOW ──human approve──► APPROVED ──human promote──► PRODUCTION
     │                                  │                           │                          │
     └────────── walk-forward REJECTED ─┴────────── reject ─────────┴────────── reject ────────┘
                                                        │
                                                        ▼
                                                    REJECTED   (terminal)
```

Transitions are a closed table (`ModelRegistry.VALID_TRANSITIONS`) — there is
no bypass, not even admin → PRODUCTION in one step:

| From | Allowed to |
|---|---|
| EXPERIMENTAL | SHADOW, REJECTED |
| SHADOW | APPROVED, REJECTED |
| APPROVED | PRODUCTION, REJECTED |
| PRODUCTION | REJECTED |
| REJECTED | *(terminal — retrain produces a NEW version)* |

- EXPERIMENTAL → SHADOW is taken **by the machine** (weekly register job, §5).
  SHADOW → APPROVED → PRODUCTION is **human-only** (§7 endpoints, RBAC-guarded).
- Every transition invalidates jumps: `transition()` re-checks the table and
  returns `False`; the API layer converts a miss into HTTP 409.
- REJECTED is rollback: one command demotes a production model; the serving
  gates (§6) react on the next prediction tick.

---

## 3. Data model (migration 012)

```sql
model_versions(                    -- one row per trained artifact
  id, model_type,                  -- flood_predictor | high_flow_predictor | flood_classifier
  asset_id FK NULL,                 -- NULL = global model
  version,                          -- e.g. xgb-flood-v1.2-h7 ( '-h{N}' suffix = horizon )
  status DEFAULT 'EXPERIMENTAL',
  metrics JSON,                     -- trainer metrics + walk_forward block
  validation_report_id FK NULL,     -- newest linked validation_reports row
  trained_at, approved_at, approved_by, notes, created_at)

validation_reports(                -- one row per walk-forward run
  id, asset_id FK, model_type, model_version, horizon,
  metrics JSON NOT NULL,            -- r2/mae/auc/brier/... + score
  data_info JSON, recommendation,   -- EXPERIMENTAL | SHADOW | REJECTED
  reasons JSON, fold_details JSON, validated_at)

prediction_errors(                 -- organic post-hoc accuracy (feeds UC-6 alerts)
  id, asset_id FK, model_version, prediction_date, target_date, horizon,
  predicted_value, actual_value, error, error_pct, data_origin)
```

Indexes: `model_versions(model_type)`, `model_versions(status)`,
`validation_reports(asset_id)`, `prediction_errors(asset_id, prediction_date)`.

Report keying: **(model_type, asset_id, horizon), newest report wins** —
`scripts/register_models.py::build_latest_reports` — so a superseded report
can never drive a transition once a newer verdict exists.

---

## 4. Evaluation → recommendation (the evidence)

Both scorers output a 0–100 `score` and a `recommendation`; same thresholds:

| Score | Recommendation |
|---|---|
| ≥ 70 | SHADOW (candidate for human review) |
| ≥ 40 (regression: ≥ 35) | EXPERIMENTAL (stay, keep watching) |
| < 40 | REJECTED |

**Regression (`validation_framework.py::_generate_recommendation`)** —
walk-forward R² is primary because a single chronological split lies under
distribution shift:

- Walk-forward R² (needs ≥ 5 folds): > 0.8 → 45 pts, > 0.5 → 35, > 0 → 15,
  ≤ 0 → **instant REJECTED**; < 5 folds → **instant REJECTED**.
- Beats persistence MAE → +15; MAE improvement vs persistence → +5/+10/+20.
- High-flow R² (needs ≥ 3 high-flow samples) → +5/+15.
- Test R² > 0.5 → +10 (secondary only).

**Classifier (`validate_all_models.py::walk_forward_classifier`)** —
probability quality against a persistence-style baseline:

- AUC → +5/+15/+30/40 (thresholds 0.55/0.60/0.70/0.80).
- Brier skill vs baseline → +10/+20/+30 (0/0.10/0.20).
- Recall ≥ 0.30/0.60 → +8/+15; precision ≥ 0.30/0.50 → +8/+15.
- Guardrails that pre-empt scoring: `insufficient_data`,
  `no_positive_labels`, `no_negative_labels` → report carries the error and
  the model cannot reach SHADOW (covered by tests).

Every report stores `reasons[]` (human-readable) + `fold_details[]`
(per-fold metrics) — the analyst page shows why, not just what.

---

## 5. The weekly automation loop (the machine's half)

All three jobs run under the existing pipeline-lock + `pipeline_runs` pattern
in `scheduler/main.py`, every Sunday, as subprocesses of the app:

| UTC | Job | Script | Effect |
|---|---|---|---|
| 03:30 | `job_retrain_all_models` | retrain FloodPredictor + FloodClassifier | fresh artifacts on disk, `model_metadata.json` refreshed |
| 03:45 | `job_validate_all_models` | `scripts/validate_all_models.py` | walk-forward → writes `validation_reports` rows (flood_predictor + flood_classifier) |
| 03:58 | `job_register_models` | `scripts/register_models.py` | upsert `model_versions`, link latest report, **auto-transition** |

`register_models.py` decision rules (per model/asset/horizon):

1. Version exists → refresh `metrics` + `validation_report_id` (status kept).
2. Version new → `registry.register()` → **EXPERIMENTAL**.
3. Latest report says SHADOW and row is still EXPERIMENTAL → transition to SHADOW.
4. Latest report says REJECTED and row is still EXPERIMENTAL → transition to REJECTED.
5. Already past EXPERIMENTAL → **kept** (a later bad report never silently
   demotes an in-review model; demotion is a human/`reject` act).

Daily, `job_compute_accuracy` appends organic rows to `prediction_errors`
(REAL origin) — that stream feeds the accuracy badges and UC-6 degradation
alerts, and is separate from the weekly walk-forward verdict.

---

## 6. Serving gates (where the registry actually bites)

The registry is consulted on live prediction paths — three known consumers:

1. **Lead-time validation badge** — `prediction_v2::_get_validation_by_lead`
   reads every `flood_predictor` row for the asset, maps the `-h{N}` version
   suffix to horizon (newest row wins), and surfaces
   `model_metadata.model_validation = {lead_time: status}`. Horizons with no
   row report **`UNREGISTERED`** — the UI never implies validation that did
   not happen.
2. **Classifier REJECTED gate** — `prediction_v2::_get_flood_probability`
   queries the newest `flood_classifier` row for the asset; if `status =
   'REJECTED'` it returns `None`, so no probability reaches forecasts, the
   threshold engine, or the flood map. SHADOW classifiers *do* score — their
   output is labelled shadow work, which is what shadow means.
3. **Lifecycle map in prediction API** — `prediction_api::_lifecycle_status_map`
   loads all rows once into `(model_type, asset_id, horizon) → status` and
   decorates prediction responses; failures degrade to a logged warning, never
   a 500.

What serving does **not** do (deliberate, see §10): pick artifact files by
registry status. The prediction pipeline loads the newest `.joblib`/`.pkl`
from `data/models/`; `ModelRegistry.get_active_model()` (PRODUCTION filter,
asset-specific falling back to global) exists and is unit-tested but has no
production caller. Today the registry gates and labels serving; it does not
select bytes.

---

## 7. API surface

```
GET  /water/registry/models?model_type=&status=&asset_id=&limit=   (read)
POST /water/registry/models/{id}/approve    SHADOW  → APPROVED     (guarded)
POST /water/registry/models/{id}/promote    APPROVED → PRODUCTION  (guarded)
POST /water/registry/models/{id}/reject     any     → REJECTED     (guarded)
```

- Guard: `APPROVE_GUARD = require_permissions("AQUAVISION_APPROVE_REPORT")`
  — admin + water_supervisor (setup_neon role grants).
- Every response carries `allowed_transitions[]` computed from the same
  `VALID_TRANSITIONS` table, plus the linked `validation_recommendation` —
  the UI renders buttons from data, never from hardcoded status logic.
- Wrong move → 409 with `Cannot transition X → Y`; unknown id → 404;
  unknown stored status → 409 (no blind enum cast).
- Body is optional `{notes}` — notes overwrite `model_versions.notes`.

## 8. Dashboard surfaces

1. **`/admin/registry` (Model Registry board)** — KPI strip (Registered /
   Approved / In Production / Rejected), status filter chips with live counts,
   table: model, version, status badge, validation recommendation, metrics
   summary (R²/MAE/AUC/F1/Score), approver + date, trained date, and
   per-row action buttons rendered from `allowed_transitions`. Without the
   permission the table renders "Read-only" + explanatory subtitle instead
   of buttons (no hidden 403s).
2. **`/admin/validation`** — walk-forward reports with fold detail, scoring
   explanation, and the lifecycle explainer (`EXPERIMENTAL → SHADOW →
   APPROVED → PRODUCTION`); deep-links the evidence a reviewer approves against.
3. **Prediction/forecast UIs** — inherit §6.1 badges and the classifier
   probability column (empty when gated REJECTED).

---

## 9. THE USE CASES

### UC-9 — Weekly lifecycle walk (machine, no human)
- **Trigger:** Sunday 03:30–04:00 UTC chain (§5).
- **Flow:** retrain writes artifacts → walk-forward validation writes reports
  (SHADOW/EXPERIMENTAL/REJECTED + reasons) → register job upserts versions,
  links reports, auto-moves EXPERIMENTAL rows per report recommendation.
- **Data captured:** metrics + walk_forward block on the version, report id,
  notes ("Walk-forward report {id}"), pipeline_runs rows for each job.
- **Result this week:** SHADOW 26 — every one report-linked, and the hop is
  machine-*only* by construction (the API exposes no "to shadow" action, so a
  human cannot perform it at all). REJECTED 9 = 8 walk-forward rejects + 1
  deliberate live E2E-test reject (unlinked, notes say so). Nothing reached
  PRODUCTION by itself.

### UC-10 — Human approval & promotion (the only door to production)
- **Trigger:** analyst/supervisor reviews a SHADOW model on `/admin/registry`
  (metrics + validation report + reasons).
- **Flow:** click **Approve** (SHADOW → APPROVED, `approved_by/at` stamped) →
  after confidence/paperwork click **Promote** (APPROVED → PRODUCTION).
  Both hit guarded endpoints; both re-validated against `VALID_TRANSITIONS`.
- **Data captured:** who, when, notes; board shows it to everyone.

### UC-11 — Rejection / rollback (the only door out of production)
- **Trigger:** validation fails, review finds leakage, or a production model
  misbehaves (UC-6 accuracy alert).
- **Flow:** **Reject** from ANY status → REJECTED (terminal). Effects are
  immediate on next tick: classifier probability stops flowing (§6.2), and
  an untouched terminal row can never be re-approved — recovery = retrain
  yields a new version that walks the ladder again.
- **Value:** rollback is one audited click, and it cannot be half-done.

### UC-12 — Audit & inspection (read-only)
- **Flow:** any role opens `/admin/registry`; viewer/field officer see
  statuses, metrics, approvers; API consumers filter
  `?status=PRODUCTION&model_type=flood_predictor`.
- **Value:** "what served last month, and who signed for it?" is a query,
  not archaeology.

---

## 10. Build status (2026-10-04)

Everything in §2–§8 is implemented and verified:

| Piece | Landed in |
|---|---|
| Schema (3 tables + indexes) | `alembic/versions/012_add_model_registry.py` (applied) |
| Lifecycle engine | `ml/validation/model_registry.py` (`ModelStatus`, `VALID_TRANSITIONS`, register/transition/get_active_model/list_versions) |
| Guarded API | `presentation/http/routers/registry.py` (approve/promote/reject, `APPROVE_GUARD`, `allowed_transitions` in responses) |
| Scorers | `ml/validation/validation_framework.py` (regression), `scripts/validate_all_models.py` (classifier walk-forward + report persistence) |
| Weekly automation | `scheduler/main.py::job_retrain_all_models / job_validate_all_models / job_register_models` (Sun 03:30/03:45/03:58 UTC, pipeline-locked) |
| Auto-transitions | `scripts/register_models.py` (upsert, report linking, EXPERIMENTAL→SHADOW/REJECTED) |
| Serving gates | `ml/models/prediction_v2.py::_get_validation_by_lead` (+ UNREGISTERED), `::_get_flood_probability` (REJECTED gate), `ml/prediction_api.py::_lifecycle_status_map` |
| UI | `app/admin/registry/page.tsx` (board + guarded actions), `app/admin/validation/page.tsx`, nav entry "Model Registry", `features/water/api.ts` (`getRegistryModels`/`transitionModel`) |

Verification (2026-10-04):
- 21/21 tests pass for the registry suites
  (`tests/unit/test_model_registry.py`, `tests/unit/test_classifier_shadow_promote.py`);
  full service suite at `c5bc4b9`: 397 passed, 1 skipped.
- Live API: `GET /water/registry/models` returns rows with correct
  `allowed_transitions` + linked `validation_recommendation`
  (e.g. id 87 `PRODUCTION → [REJECTED]`, id 88 `APPROVED → [PRODUCTION, REJECTED]`).
- Live DB tallies: **88 versions** — EXPERIMENTAL 51, SHADOW 26, REJECTED 9,
  APPROVED 1, PRODUCTION 1; by type: flood_predictor 44, high_flow_predictor 33,
  flood_classifier 11. **223 reports** (EXPERIMENTAL 96, SHADOW 69, REJECTED 58);
  55/88 versions have a linked report. **401 prediction_errors**
  (2026-04-08 → 2026-10-02). PRODUCTION = `flood_classifier` asset 8
  `xgb-flood-v1.2-h7`, approved by **Admin User on 2026-10-03**; the next in
  line (asset 9, same version string) sits APPROVED by the same reviewer.

Deliberate deferrals / known limits:
- **`get_active_model()` has no production caller** — serving selects the
  newest artifact file; registry labels and gates, it does not choose bytes.
  Promote wiring (PRODUCTION row → file selection) is the natural next step.
- **high_flow_predictor never auto-advances** — `REPORT_MODEL_TYPES` covers
  flood_predictor + flood_classifier only, so its 33 rows stay EXPERIMENTAL
  (32) / REJECTED (1, a live E2E-test reject with no report) until walk-forward
  reporting is extended to it.
- **Legacy `validation_reports.model_type='xgb_flood'`** rows predate the
  current type names; they are inert (no versions key to them).
- **Version-string reuse** (`xgb-flood-v1.2-h7` used by two assets) is legal
  because identity is (model_type, asset_id, version) — but versions are not
  globally unique names.
- No notification on promotion/rejection — reviewers watch the board; hooking
  `NotificationDispatcher` would mirror the alert workflow.
