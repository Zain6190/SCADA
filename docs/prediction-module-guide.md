# Prediction Module — Complete Guide
# ==================================
# Created: 2026-09-26
# Status: LIVE (advisory forecasts; accuracy loop running daily)
#
# Every rule, value and formula below is taken from the code as it stands
# (file paths given per section). If code changes, this file must follow.

---

## 1. What the module is

Produces **operational forecasts for all 11 water assets** at **3 / 7 / 14 day**
lead times (models also trained at 30d for backtesting):

1. **Expected discharge** (cusecs + m³/s) with an uncertainty interval
2. **Water stress** (WAI 0–100 + category)
3. **Flood risk** (0–100 score + category)
4. **Rainfall** (mm over the lead window + probability)

It is **advisory** (`prediction_v2.py` header: "EXPERIMENTAL. Predictions are
advisory only") and closes a loop: **predict → store → later score against what
really happened → report accuracy honestly**.

**Delivered through:**
- REST: `GET /water/v2/...` (`ml/prediction_api_v2.py`)
- Dashboard: `/water/predictions` (v2 tab), `/water/operator/alerts`
- Alert engine: `infrastructure/thresholds/engine.py` (persisted forecast alerts)
- Notifications: email/Slack on new critical/warning alerts
- Workflow: CRITICAL/HIGH (and FLOOD/RAINFALL WARNING) v2 predictions are persisted
  as `ML_*` alerts with `alert_source='ML_V2'` (`prediction_v2.py::_persist_alerts`)
  and flow through the role-based alert workflow (`docs/alert-workflow-design.md`)

---

## 2. Architecture

```
 ┌──────────────────────────── Scheduler (scheduler/main.py) ───────────────────────────┐
 │ 01:00 FFD ingest │ 01:30 IRSA ingest │ 02:00 inflow backfill                        │
 │ 02:30 job_run_predictions → engine.run_prediction_pipeline (predict→store→alert)     │
 │ 03:00 job_compute_accuracy → scripts.compute_accuracy (forecast vs REAL obs)         │
 │ 06:00h job_refresh_weather │ Sun 03:00 train │ Sun 03:30 retrain │ Sun 03:45 validate│
 └──────────────────────────────────────────────────────────────────────────────────────┘
                     │                                   │
                     ▼                                   ▼
      water_asset_forecasts (history)          water_operational_alerts
                     │                           └─► _dispatch_notifications (email/Slack)
                     ▼
      scripts.compute_accuracy ──► prediction_errors ──► accuracy shown in API/UI
                     ▲
 ┌───────────────────┴───────────────┐
 │  GET /water/v2/predict/{id}       │  ml/prediction_api_v2.py
 │  AquaVisionPredictionModel        │  ml/models/prediction_v2.py
 │  .predict()                       │
 └───────┬──────────────┬────────────┘
         │              │
         ▼              ▼
  FloodPredictor     Physics routing      WAI (wai_computer)   Weather (weather_service)
  (XGBoost .joblib)  (upstream obs)       (realtime + weekly)  (Open-Meteo, 6h)
         │
         ▼
  models/flood_xgb/{asset}_{horizon}.joblib
  (+ _interval.joblib quantile models, *_hf HighFlow variants)
```

| Component | File |
|---|---|
| Orchestration / API responses | `ml/models/prediction_v2.py` |
| HTTP endpoints | `ml/prediction_api_v2.py` |
| ML trainer/predictor | `ml/models/flood_predictor.py` |
| Flood probability classifier | `ml/models/flood_classifier.py` |
| Feature builder | `ml/features/feature_engineering.py` |
| Target rules (single source of truth) | `ml/targets.py` |
| WAI | `ml/models/wai_computer.py` |
| Weather | `ml/features/weather_service.py`, `scripts/backfill_weather.py` |
| Forecast store + alerts + pipeline | `infrastructure/thresholds/engine.py` |
| Accuracy scorer | `scripts/compute_accuracy.py` |
| Batch retrain / validate | `scripts/retrain_all_models.py`, `scripts/validate_all_models.py` |
| Dashboard consumers | `packages/dashboard/src/app/water/predictions/*` |

---

## 3. Which data is used, where and how

### 3.1 Sources

| Data | Table | Used for | Refresh |
|---|---|---|---|
| Daily level/inflow/outflow/discharge (IRSA, KAGGLE, sensors, FFD, seeded history) | `aquavision.water_observations` | Training features/labels, current value, trend, accuracy actuals (**REAL only**) | IRSA 01:30, FFD 01:00 daily |
| Weather (daily actual + 7/14/16d forecast) | `aquavision.weather_forecasts` | Features `forecast_*`; rainfall in risk/alerts | Archive backfill + refresh every 6h |
| Discharge thresholds (warn/danger/critical, ft) | threshold table | Features `pct_of_warning/danger`, flood-risk threshold factor, forecast-danger alerts | static config |
| FFD status | FFD observations | One-hot features `ffd_*` | 01:00 daily |
| Upstream gauge (for barrages) | `water_observations` via river network | Physics routing value + trend projection | on read |
| WAI inputs (level, storage, flow, 90d) | `water_observations` + weekly indicators | Water-stress score | realtime compute + Sun 04:00 pipeline |
| Trained models | `models/flood_xgb/*.joblib` | Inference | Sunday retrain (bind-mounted, survives recreates) |
| GRDC (1936–1982 station archives) | `aquavision.grdc_stations/observations` | **Offline only** — routing validation / future features. Never mixed into asset series | one-time ingest |

### 3.2 Per-asset prediction rules (`ml/targets.py` + `prediction_v2.py`)

| Assets | Target the model learns | Served discharge path | `prediction_method` |
|---|---|---|---|
| 1 Tarbela, 2 Mangla | **outflow** (explicit map; storage_volume is empty → mass balance impossible) | ML outflow model | `ml_xgboost_outflow` |
| 9 Kabul, 10 Chenab | **discharge** (explicit) | ML discharge model | `ml_xgboost_discharge` |
| 3–8, 11 barrages | inflow fallback (only for storage/history) | **Physics routing**: upstream observation ± damped trend | `physics_routing` |

Rules:
- `resolve_target_field()` **never returns `"auto"`** — train, predict and accuracy
  all use the same concrete field.
- `flow_baseline_cusecs()` picks the current-value baseline that matches the
  model's target (outflow models compare against outflow, never inflow) so the
  "trend" is not nonsense.
- Level-target models are the only ones allowed to compare against ft
  thresholds — comparing cusecs to ft is treated as a unit bug (engine skips it).

---

## 4. Features (what the model actually sees)

Built by `FloodFeatureBuilder._extract_features` (identical at train and
inference):

| Group | Features |
|---|---|
| Current state | `level`, `inflow`, `outflow`, `discharge` |
| Lags | `level/inflow/outflow_lag_{1,3,7,14,30}d` |
| Rolling | `level/inflow_roll_{7,14,30}d_mean`, `..._std` |
| Rate of change | `level_roc_{1,3,7}d`, `inflow_roc_1d` |
| Seasonality | `day_sin`, `day_cos`, `month`, `is_monsoon` (Jun–Sep) |
| Threshold proximity | `pct_of_warning`, `pct_of_danger` (level / warn-level) |
| Ratio | `inflow_outflow_ratio` |
| FFD status | `ffd_below_low`, `ffd_low`, `ffd_medium`, `ffd_high` |
| Weather | `forecast_precip_7d`, `forecast_temp_max`, `forecast_humidity_mean` (0.0 if no row for that asset+date) |

Training masks inflow lag/roll/roc features when the target is outflow-shaped
(`feature_engineering.py` ~L147) to avoid target leakage.

---

## 5. Training rules (`flood_predictor.train`)

| Rule | Value |
|---|---|
| Split | **chronological 80/20**, `shuffle=False` (last 20% = holdout) |
| Target transform | `log1p` (flag stored per model) |
| Model | XGBoost `n_estimators=500, max_depth=4, learning_rate=0.03` |
| Sample weights | optional (flood-classifier-style weighting) |
| Persistence blend | closed-form `alpha = argmin MSE(alpha·xgb + (1−alpha)·current)` on holdout; `alpha=1` when the model already beats persistence (Tarbela etc.) |
| Quantile interval model | q10/q90 (`reg:quantileerror`, 300 trees) if `persist` and ≥100 samples |
| Residual band | `residual_p90` = 90th pct of \|holdout residuals\| |
| Conformal calibration | additive inflation = 80th pct of holdout nonconformity → shipped bands hit the **0.80 coverage target** |
| Baseline metrics | `r2_persistence`, `mae_persistence` recorded on the same holdout |
| Horizons | `[3, 7, 14, 30]` per asset (81 models success / 7 skipped / 0 failed on last run) |
| Artifacts | `{aid}_{h}.joblib` (model+scaler+metrics), `{aid}_{h}_interval.joblib` (quantile), `{aid}_{h}_hf.joblib` (HighFlow, 75th-pct threshold) |
| Legacy files | no `blend_alpha` → loads as alpha=1 (unchanged behaviour) |

Models are **never** trained on seeded/polluted rows in a way that leaks the
holdout (`persist=False` for holdout backtests).

---

## 6. Metrics: what they are, why they exist, where you see them

### R² (coefficient of determination)
`1 − SS_res/SS_tot` — the fraction of the variation the model explains versus
"always predict the average". **0 = no better than the mean, 1 = perfect,
negative = worse than the mean.** Why it's used: scale-free, so Tarbela
(100k+ cusecs) and Kabul (10k) are comparable.
- Headline `r2` in each model's metrics is the **served (blended) value**;
  the raw XGBoost is kept as `r2_xgb_raw`.
- `r2_persistence` is the same metric for "today's value continues" — the
  honest yardstick. A model is only meaningfully useful if it beats this.

### MAE (mean absolute error)
Average `|predicted − actual|` **in the model's own units** (cusecs/ft).
Why: operators think in cusecs — "off by ~8,500 cusecs on average" is
actionable, percentages aren't. Stored as `mae` / `mae_xgb_raw` / `mae_persistence`.

### MAPE (mean absolute percentage error)
Average `|error| / actual × 100`. Why: relative accuracy across assets. It is
what the live accuracy score is built from:

```
accuracy (0–1) = max(0, 1 − MAPE/100)          # prediction_v2._get_accuracy_by_lead
```

- Only computed from `prediction_errors` rows with `data_origin='REAL'`
- Requires **≥ 5 samples per horizon** (`ACCURACY_MIN_SAMPLES`), else the API
  returns `None` → UI shows "Not validated" instead of a fake score
- Exposed as `model_metadata.accuracy_3day/7day/14day` and
  `accuracy_status = VALIDATED | NOT_VALIDATED`

### Coverage (ci_coverage_80)
Fraction of holdout actuals that landed inside the served q10–q90 band after
conformal calibration. Target = 0.80; **currently measured 0.798–0.801 across
all 16 ML models**. Raw (pre-calibration) kept as `ci_coverage_80_raw`,
inflation as `ci_inflation` — nothing is hidden.

### Current model quality (post-weather retrain, 2026-09-26)

| Asset | 3d R² | 7d R² | 14d R² | 30d R² |
|---|---|---|---|---|
| 1 Tarbela (outflow) | 0.878 | 0.803 | 0.721 | 0.659 |
| 2 Mangla (outflow) | 0.539 | 0.212 | −0.055 | 0.264 |
| 9 Kabul (discharge) | 0.807 | 0.706 | 0.654 | 0.471 |
| 10 Chenab (discharge) | 0.809 | 0.716 | 0.683 | 0.673 |

Mangla is weak at 14d because outflow autocorrelation dies by lag 14
(lag-7 = 0.68, lag-14 = 0.44, lag-30 = 0.14) — the persistence blend guarantees
it is never worse than "hold today's value", but beyond ~7d there is little
signal to find. Barrages show `NOT_VALIDATED` until routed flow accrues errors.

---

## 7. Inference flow (one `GET /water/v2/predict/{id}`)

`AquaVisionPredictionModel.predict()` (`prediction_v2.py:334`), for lead times
**[3, 7, 14]**:

1. **Current observation** — no data → empty payload (`status: NO_DATA`).
2. **Inputs loaded:** realtime WAI, weather forecast, flood-classifier
   probability, warn/danger thresholds, ML predictions (all horizons from
   `.joblib`), upstream discharge (barrages), real accuracy per lead.
3. **Discharge branch** (first match wins), per lead time:
   1. **Physics** (`upstream > 0`): `value = upstream × (1 + damped trend)`,
      dampening `{3d: 0.60, 7d: 0.25, 14d: 0.12}` × daily % trend, change capped
      **±40%**. Interval `physics_band` = **±(0.10 + 0.02×lead)** → 16% at 3d,
      24% at 7d, 38% at 14d (widening with lead time).
   2. **ML**: point = blended model output; interval chain
      `quantile_q10_q90` → `residual_p90` → `r2_band` → fallback `pct_heuristic` **±15%**.
   3. **Neither**: hold current value, `pct_heuristic` **±10%**.
   Lower bound clamped ≥ 0. Converted cusecs→m³/s by `/35.3147`.
4. **Water stress**: realtime WAI (flow 0.50 / storage 0.30 / trend 0.20 over
   90d; stale weekly only as fallback; **None → "No Data", never a default
   score**). Trend = % change of target-matched baseline (physics assets:
   projected, capped ±50%).

   | WAI | Abundant | Moderate | Stressed | Critical | Severe |
   |---|---|---|---|---|---|
   | | 80–100 | 60–80 | 40–60 | 20–40 | 0–20 |

5. **Flood risk** (0–100):
   ```
   score = min(100, base + threshold + rainfall + trend)
   base      = flood_probability × 100            (0 if classifier absent)
   threshold = ratio = q_pred/q_warn:
               ratio ≥ 1.0 → min(30, (ratio−1.0)×50)
               0.8 ≤ ratio < 1.0 → (ratio−0.8)×50
   rainfall  = mm > 50 → min(15, (mm−50)/10)
   trend     = % > 10 → min(10, (%−10)/5)
   ```
   Categories: **Critical ≥ 70, High 50–70, Moderate 30–50, No Risk < 30**.
   Drivers list explains which factor contributed.
6. **Rainfall**: `mm = precip_sum_mm(lead window) × (lead/7)`; probability
   `= min(1, (mm / (30mm × lead/7)) × 0.7)` (30mm/wk ≈ September normal).

### Two separate alert systems

**A. Alerts inside the v2 payload** (`_generate_alerts`, returned to the UI):

| Rule | Level |
|---|---|
| Water stress ≤ 40 | CRITICAL (`WATER_STRESS`) |
| Water stress ≤ 60 | WARNING |
| Flood risk ≥ 70 | CRITICAL (`FLOOD_RISK`) |
| Flood risk ≥ 50 | HIGH |
| Flood risk ≥ 30 | WARNING |
| Rainfall > 80 mm in lead window | WARNING (`RAINFALL`) |

**B. Persisted forecast alerts in the alert engine** (`check_prediction_alerts`,
runs inside `run_prediction_pipeline` after each batch):

- Loads the **7-day model**, predicts the latest row, and **only for
  level-target models** compares against ft thresholds:
  - predicted ≥ **critical** → `FORECAST_DANGER_7D`, severity **CRITICAL**
  - predicted ≥ **danger** → `FORECAST_DANGER_7D`, severity **WARNING**
- Inflow/discharge-target models are skipped (unit bug guard); deduplicated
  while an open alert of the same type exists; `alert_source="ML"`.
- New critical/warning alerts → `_dispatch_notifications` (Email + Slack if
  configured, DB-backed dedup) and appear in `/water/operator/alerts`.

---

## 8. The accuracy loop (why predictions get scored)

1. **02:30 daily** `run_prediction_pipeline` (`engine.py:1166`) — for each
   active asset × horizon [3,7,14,30]: build features from the last 400 days →
   predict → `store_prediction()` writes to **`water_asset_forecasts`**
   (`generated_at`, `target_time = now+horizon`, value in the column matching
   the model's target_field) → `check_prediction_alerts`.
2. **03:00 daily** `scripts.compute_accuracy` (`lookback 60d`):
   - selects forecasts whose `target_time < now` and not yet scored
   - finds the nearest **`data_origin='REAL'`** observation within ±1 day
   - matches value-in-value-out priority: inflow → outflow → discharge → level
   - writes `prediction_errors`: `error = pred − actual`,
     `error_pct = |error|/actual×100` (plain `|error|` if actual = 0)
   - skips (never fakes) when no REAL actual exists → `skipped` counter
3. **API/UI read it back**: `_get_accuracy_by_lead` aggregates
   `error_pct → MAPE → accuracy 0–1` per horizon (n ≥ 5), and the dashboard
   shows `model_metadata.accuracy_*`, `ci_coverage_80` badges and
   `accuracy_status`.
4. First **organic** (non-seeded) rows land **2026-09-28/29** — from forecasts
   generated on 09-24+.

Seeded rows (`seed_prediction_errors.py`, holdout-style, `data_origin != REAL`)
exist only to exercise the UI before organic data arrives; the accuracy query
filters them out (`data_origin='REAL'`).

---

## 9. Scheduler (the module's heartbeat)

| UTC | Job |
|---|---|
| 01:00 / 01:30 | FFD / IRSA ingestion |
| 02:00 | inflow backfill |
| **02:30** | **predictions: predict → store → forecast alerts** |
| **03:00** | **compute_accuracy (score expired forecasts)** |
| every 6h | weather refresh (forecast + horizon-0 bridge) |
| Sun 03:00 / 03:30 / 03:45 / 04:00 | train / retrain_all / validate_all / WAI pipeline |
| 05:00 | heartbeat every 5 min |

---

## 10. API surface (`ml/prediction_api_v2.py`)

| Endpoint | Returns |
|---|---|
| `GET /water/v2/predict/{asset_id}` | 3/7/14 forecasts + alerts + `model_metadata` |
| `GET /water/v2/predict/{asset_id}/{lead}` | single lead time |
| `GET /water/v2/national-overview` | NDMA rollup (national WAI, statuses) |
| `GET /water/v2/asset/{asset_id}/forecast-chart` | 30d actual + 3/7/14 forecast + q10–q90 band |

Key response fields: `discharge.value_cusecs / value_m3s`,
`discharge.ci_method`, `ci_coverage_80` (per horizon), `water_stress.value/category`,
`flood_risk.value/category/drivers`, `rainfall.value_mm/probability`,
`confidence` (live accuracy 0–1 or null), `alerts[]`,
`model_metadata.prediction_method`, `accuracy_status`.

Units: stored/served in **cusecs**; m³/s always shown alongside
(1 m³/s = 35.3147 cusecs). Level thresholds are **ft** and only ever compared
to level values.

---

## 11. Who uses the predictions (module map)

| Consumer | How |
|---|---|
| **Dashboard — `/water/predictions` v2 tab** | National Overview card, forecast chart with CI band, per-lead CI provenance badges (Quantile 80% CI / Residual ±p90 / Physics band / ±15% heuristic) + coverage % |
| **Dashboard — `/water/operator/alerts`** | persisted `water_operational_alerts` incl. `FORECAST_DANGER_7D` from the engine, with notification dispatch |
| **Dashboard — flood map / impact tools** | read `water/operational/alerts` + flow endpoints (impact `latest-flow` uses observations) |
| **Admin — `/admin/validation`** | validation reports + `prediction_errors`-driven accuracy views |
| **Notifications (email/Slack)** | new critical/warning alerts only, deduplicated |
| **Weekly WAI pipeline** | same observation/indicator basis as the WAI shown per asset |
| **GRDC archives** | offline reference for routing validation — not served |

---

## 12. Honest limitations

- **No level↔discharge rating curves** — level-target prediction exists but the
  module's headline product is discharge; barrages cannot be ML-scored yet.
- **Barrages (3–8,11)**: ~13 rows each → physics routing only,
  `accuracy_status = NOT_VALIDATED` until routed flow accrues REAL errors
  (WAPDA data request would fix the training side).
- **Mangla 14d** ≈ no skill beyond persistence — the blend caps the damage, it
  does not create signal.
- **GRDC data is 1936–1982** — valuable for validation/features, useless for
  live inference.
- **Accuracy shown pre-2026-09-28** is seeded, not organic (filtered in the
  REAL-only query).
- Empty/no-data responses are marked `NO_DATA` — the module does not invent
  observations, and every metric (coverage, R², persistence) is measured on the
  holdout and stored with the model, not asserted.

---

## 13. Operations runbook

```bash
# Retrain everything (81 success / 7 skipped / 0 failed expected)
docker exec -w /app ibcp-api python -m scripts.retrain_all_models

# Score expired forecasts now (scheduler does it daily 03:00 UTC)
docker exec -w /app ibcp-api python -m scripts.compute_accuracy

# Validate all stored models / regenerate reports
docker exec -w /app ibcp-api python -m scripts.validate_all_models

# Weather: archive backfill + bridge rows (scheduler refreshes every 6h)
docker exec -w /app ibcp-api python -m scripts.backfill_weather

# GRDC archives (idempotent)
docker exec -w /app ibcp-api python -m scripts.ingest_grdc

# Live check
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8100/water/v2/predict/1
```

Tests: `python -m pytest -q` in `services/aquavision-service` (204 passing as
of 2026-09-26).

Related docs: `docs/prediction-module-plan.md` (status, gaps, recommendations).
