# 04 — Machine-Learning Models

## 1. Model inventory

| Model | Algorithm | Code | Version / status | Served by |
|-------|-----------|------|------------------|-----------|
| Flood predictor (discharge, 3/7/14/30-day) | XGBoost regressor, `n_estimators=500, max_depth=4` | `ml/models/flood_predictor.py:84` (`FloodPredictor`), model built at `:155-157` | `xgb-flood-v1.2` (`:102`) | `GET /water/ml/predictions/{asset_id}` |
| High-flow predictor | XGBoost regressor | `ml/models/flood_predictor.py:643` (`HighFlowPredictor`) | `xgb-highflow-v1.0` (`:662`) | `GET /water/v2/predict/{asset_id}` |
| Flood classifier (7-day binary) | GradientBoostingClassifier + SMOTE | `ml/models/flood_classifier.py:41`, `:166` (`:149` SMOTE, fallback `:161-163`) | per-asset, trained weekly | `GET /water/v2/predict/{asset_id}` |
| Anomaly detector (per asset) | IsolationForest | `ml/models/anomaly_detector.py:51`, fit at `:206-212` | `iforest-v1.0`, **EXPERIMENTAL** (`:24-25`) | `GET /water/ml/anomalies/summary`, `.../{asset_id}/history` |
| Prediction v1 (composite) | feature blend | `ml/prediction_api.py` | `model_version "1.0"` | `GET /water/ml/predictions/{id}` |
| Prediction v2 (revised) | discharge / stress / flood-risk / rainfall / lead-time heads | `ml/prediction_api_v2.py:150` (`get_prediction`), model class `ml/models/prediction_v2.py:321`, `model_version "2.0"` (`:427`) | `2.0` | `GET /water/v2/predict/{id}` |
| Real-time WAI (per request) | percentile-rank formula | `ml/models/wai_computer.py:46` (`compute_realtime_wai`) | — | predictions, overview |
| Reliability scoring | heuristic/statistical | `ml/models/reliability.py` | — | `GET /water/v2/reliability/...` |
| Regional WAI (weekly) | XGBoost regressor + classifier | `services/ml-pipeline/models/train_wai.py` | `xgb-v1.1` | `GET /water/indicators`, `/water/stress-alerts` |
| RTU 6-hour forecast | gradient-boosted trees per USGS site | `ml/` artifacts `ml/artifacts/rtu_metrics.json` | 3 sites, real 15-min data | sensor analytics |
| PLC/OT attack detector | HistGradientBoosting + divergence + state machine | `ml/artifacts/plc_metrics.json` | HAI 23.05 | `GET /water/ot/status` |

## 2. Flood prediction family (core contribution)

* One regressor per asset **per horizon** — 11 assets × {3, 7, 14, 30} days = 44
  `flood_predictor_*` models, plus 11 `flood_classifier_7` and 11 `high_flow_*` models,
  recorded in `services/aquavision-service/data/models/model_metadata.json`
  (generated `2026-10-03`, `model_version xgb-flood-v1.2`).
* Features: lagged inflow/outflow, rolling maxima/minima, day-of-year, storage state
  (top importances per asset are stored with each model, e.g. Tarbela 7-day:
  `inflow_roll_max_7 = 0.516`, `inflow_roll_max_14 = 0.219`).
* Training splits are time-ordered (train/test by date), never shuffled — avoids
  look-ahead leakage. Per-model record: `train_samples`, `test_samples`, `r2`, `mae`,
  `rmse`, `mape`, `feature_importance`.
* **Model governance**: every model carries a lifecycle status — `SHADOW`,
  `EXPERIMENTAL`, or `REJECTED` — assigned during the weekly validation job
  (`scheduler/main.py:363`, `job_validate_all_models`) and registered by
  `job_register_models` (`main.py:394`). Rejected models (e.g. Panjnad 30-day,
  R² ≈ −0.003) remain on disk for audit but are not promoted.

## 3. Anomaly detection (IsolationForest)

* Per-asset IsolationForest trained on the latest 370 days of observations; artifacts at
  `models/anomaly_if/anomaly_{asset_id}.joblib` (11 models).
* Scoring is **on-the-fly** — scores are never persisted. Endpoints:
  * `GET /water/ml/anomalies/summary?days=30` — one scored series per asset,
    aggregated counts;
  * `GET /water/ml/anomalies/{asset_id}/history?days=...` — point-level scores.
* Engineering notes (defence-relevant): artifact cache keyed by file mtime/size
  (`anomaly_detector.py:27`, `_ARTIFACT_CACHE`), series cache keyed by a
  count/max-timestamp fingerprint (`:29`, `_SERIES_CACHE`), batch scoring in
  `score_many` (`:513`). This reduced the summary endpoint from ~58 s to ~1.6 s warm.
* Severity bands on the isolation score (anomaly ⟺ score < 0):
  HIGH < −0.30, MODERATE < −0.15, otherwise LOW.
* Explicitly marked **EXPERIMENTAL / advisory only** (`anomaly_detector.py:24, :36`) —
  scores support analysts, they do not raise alerts by themselves.

## 4. Regional WAI pipeline (ml-pipeline)

Weekly regional Water-Aggregate Index modelling lives in `services/ml-pipeline/`:

* `gee/build_labels.py:29-36` — component weights; `:40-49` — severity classification.
* `models/train_wai.py:53` — severity order `Normal → Moderate → Stressed → Severe → Critical`.
* `scripts/predict_weekly.py:243-247` — band assignment for forecasts.
* `scripts/run_risk_alerts.py:11-12` — alert rules (WAI < 25 → `WAI_CRITICAL`,
  WAI < 40 → `WAI_SEVERE`), writing `aquavision.water_alerts`.
* Artifacts: `models/artifacts/wai_reg_xgb-v1.1.joblib`, `wai_clf_*.joblib`,
  `wai_interval_*.joblib`, `metrics.json`, `anomaly_metrics.json`.
* Run weekly by `job_run_wai_pipeline` (Sunday 04:00) through `subprocess` with the same
  advisory lock (`scheduler/main.py:225-262`).

## 5. Training, validation and registration flow

```
Sun 03:00 train (job_train_models, main.py:199)
Sun 03:30 retrain all (job_retrain_all_models, main.py:332)
Sun 03:45 validate backtests (job_validate_all_models, main.py:363)
Sun 03:58 register (job_register_models, main.py:394)
   │
   ▼
model_metadata.json + aquavision.model_versions (DB) + artifacts on disk
   │
   ▼
GET /water/ml/model-performance  (99 model records, live)  →  /admin/registry UI
```

Manual triggers: `POST /water/ml/train` (per-asset), admin validation pages.

## 6. Verification

```powershell
.\scripts\Show-Metrics.ps1          # every metric, no server required
.\scripts\Test-API.ps1              # includes predictions v1/v2, anomaly summary/history
python -m pytest tests -q           # 422 passed, 1 skipped (services/aquavision-service)
```

Headline live numbers (2026-10-05): flood predictors average R² = 0.4824 across 44
models; Tarbela 3-day R² = 0.8663; RTU skill vs persistence 0.31/0.07/0.02 per site;
PLC attack detector ROC-AUC = 0.7568. Full metric definitions in `05-metrics-formulas.md`.
