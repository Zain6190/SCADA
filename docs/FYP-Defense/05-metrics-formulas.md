# 05 — Metrics, Formulas and Interpretation

## 1. Core formulas

| Metric | Formula | Meaning |
|--------|---------|---------|
| R² (coefficient of determination) | `R² = 1 − Σ(y−ŷ)² / Σ(y−ȳ)²` | variance explained; < 0 means worse than predicting the mean |
| MAE | `mean(|y − ŷ|)` | average absolute error (same unit as target) |
| RMSE | `sqrt(mean((y − ŷ)²))` | error emphasising large misses |
| MAPE | `mean(|y − ŷ| / |y|) × 100` | percentage error |
| Skill vs persistence | `skill = 1 − MAE_model / MAE_persistence` | > 0 = model beats "tomorrow = today"; < 0 = trails the baseline |
| WAI (regional index) | per-region min-max normalise each feature, then weighted mean (`ml-pipeline/gee/build_labels.py:52-53`) | 0–100 composite drought/water stress |
| Anomaly score | IsolationForest decision score; anomaly ⟺ score < 0 | negative = more isolated = more unusual |
| Alert SLA | age since `created_at` vs response window (scan every 5 min, `scheduler/main.py:519`) | drives escalation |

## 2. WAI construction (regional model)

Components and weights (`services/ml-pipeline/gee/build_labels.py:27-36`, sum = 1.0):

| Component | Weight |
|-----------|--------|
| rainfall_mm | 0.25 |
| ndvi | 0.20 |
| water_extent | 0.15 |
| et_mm (evapotranspiration) | 0.15 |
| sm_rootzone (root-zone soil moisture) | 0.15 |
| sm_surface (surface soil moisture) | 0.10 |

Severity bands (`build_labels.py:40-49`; mirrored in the API by
`domain/water_classifier.py:23-25, :32-37` against DB thresholds `aquavision.water_thresholds`):

| WAI | Severity |
|-----|----------|
| < 25 | Critical |
| < 40 | Severe |
| < 55 | Stressed |
| < 70 | Moderate |
| ≥ 70 | Normal |

Alert rules derive from the same bands (`ml-pipeline/scripts/run_risk_alerts.py:11-12`):
WAI < 25 → `WAI_CRITICAL`; WAI < 40 → `WAI_SEVERE`.

SPI drought classes (`ml-pipeline/scripts/compute_spi.py:39-44`): ≤ −2.0 extreme drought,
−2.0…−1.5 severe drought, …, +1.5…+2.0 severely wet.

## 3. Live evaluation numbers (metrics.json, generated 2026-10)

Regional WAI model `xgb-v1.1` (`services/ml-pipeline/models/artifacts/metrics.json`,
n_train = 406 months, n_test = 102 months, test window 2026-03-01 → 2026-09-01):

| Variant | R² | MAE | RMSE | Skill vs persistence |
|---------|-----|-----|------|----------------------|
| Persistence baseline (repeat current WAI) | 0.5214 | 6.898 | 10.5278 | 0 (reference) |
| XGBoost regressor | 0.4675 | 7.5752 | 11.1053 | **−0.098 (trails)** |
| Blend (α = 0.39 with persistence) | **0.5248** | 6.6138 | 10.4903 | **+0.041 (beats)** |

* Honest interpretation: a single weekly WAI value is close to a random walk, so the pure
  regressor does not beat persistence. The reported system number is the **blend**
  (R² 0.5248), which only marginally beats persistence — this is stated openly in
  `12-viva-qa.md`.
* Blend caveat: `metrics.json` records `"fitted_on": "test"` — α was fitted on the test
  window; a deployment-grade evaluation would re-fit α on a held-out calibration split.
* Severity classifier accuracy: **0.4674** over 5 classes (`classifier.accuracy`);
  confusion shows the model rarely says Critical (0 true Criticals predicted). The
  classifier is decision-support only; threshold rules (section 2) generate the alerts.
* Prediction interval: conformal quantile method (q10/q90), inflation 1.4199, empirical
  80 % coverage 0.7869 (raw 0.6557) on the test window.

Flood predictors (`model_metadata.json`, 44 regressors):

| Statistic | Value |
|-----------|-------|
| Average R² (all assets × horizons) | 0.4824 |
| Best | Tarbela 3-day R² 0.8663 (MAE 15,508 cusecs) |
| Short horizon 3-day | typically 0.4–0.87 |
| Long horizon 30-day | degrades; worst −0.0032 (Panjnad) → status REJECTED |
| Flood classifier (7-day) | accuracy up to 1.0 where the positive class never occurs (trivial), meaningful AUC 0.95 (Tarbela) |

RTU telemetry (real USGS 15-min, 6-hour horizon, `rtu_metrics.json`):

| Site | R² | MAE (ft) | Skill vs persistence |
|------|-----|----------|----------------------|
| 03612600 | 0.9964 | 0.2316 | 0.3063 |
| 05331000 | 0.9880 | 0.0405 | 0.0748 |
| 06610000 | 0.9956 | 0.0619 | 0.0235 |

PLC/OT detection (HAI 23.05, `plc_metrics.json`): attack detector precision 0.2964,
recall 0.0807, F1 0.1268, **ROC-AUC 0.7568**; unsupervised divergence detector precision
0.8041 (recall 0.0399 — high-confidence flags only).

Regional anomaly detector (`anomaly_metrics.json`): 508 weekly rows, 26 flagged
(rate 0.0512) at contamination 0.05.

## 4. What each number is used for

| Question | Metric to quote |
|----------|-----------------|
| "How accurate are the flood forecasts?" | R²/MAE per horizon + skill vs persistence; note degradation with horizon |
| "Is the WAI model useful?" | blend R² 0.5248 and skill +0.041; be explicit that the pure regressor trails |
| "Do the alerts mean anything?" | deterministic threshold rules (section 2), not classifier output |
| "Is the anomaly page safe?" | EXPERIMENTAL flag, advisory-only (`anomaly_detector.py:36`) |
| "Show me the numbers" | `.\scripts\Show-Metrics.ps1` (single command, offline) |

## 5. Reproduce

```powershell
.\scripts\Show-Metrics.ps1        # prints every table above from the metrics files
.\scripts\Test-API.ps1            # includes GET /water/ml/model-performance
```
