# Prediction Module Completion Plan
# ================================
# Created: 2026-09-21
# Updated: 2026-09-24
# Status: APPROVED — Scenario 3 (PARALLEL)
# Rating: 8.5/10

## The Problem
ML models predict water_level_ft, but dashboard needs discharge (m³/s).
No paired level+discharge data for rating curves.

## Architecture: Physics-First + ML Discharge (Path A)

Don't convert level→discharge. Instead:
- Reservoirs (1,2): Mass balance → inflow = outflow + Δstorage/Δt
- Barrages (3-8,11): Upstream routing → discharge from upstream observations
- Headwaters (9,10): ML predicts discharge directly (has discharge data)

## Asset Data Sufficiency

| Asset | Data | Rows | Years | Rating | Method | Status |
|-------|------|------|-------|--------|--------|--------|
| 1 Tarbela | Level+Inflow | 1,749 | 4.5 | ✅✅✅ EXCELLENT | ML level + mass balance | READY |
| 2 Mangla | Level+Discharge | 1,832 | 48 | ✅✅✅✅ OUTSTANDING | ML discharge | READY |
| 9 Kabul | Discharge | 9,398 | 67 | ✅✅✅✅✅ GOLD | ML discharge | READY |
| 10 Chenab | Discharge | 1,701 | 4.5 | ✅✅✅ GOOD | ML discharge | READY |
| 3-8,11 Barrages | Discharge only | 13 each | 0.2 | ❌ INSUFFICIENT | Physics routing | PARTIAL |

## Scenario 3: PARALLEL (RECOMMENDED) ⭐

### Week 1-2: CODE (primary) + DATA (background)

**Code tasks (Abeera — primary focus):**
- [x] Step 1: Retrain ML models targeting DISCHARGE/FLOW (assets 1,2 → outflow; 9,10 → discharge; verified 2026-09-24: retrain 81 success/0 failed, holdout ledger 360 rows)
- [x] Step 2: Fix prediction_v2.py discharge logic (verified 2026-09-24: ml_xgboost_outflow/discharge labels live, forecasts table 0 all-NULL rows, 168 tests)
- [x] Step 3: Add 3-day horizon to training (verified 2026-09-24: retrain_all_models horizons [3,7,14,30]; 77 models in models/flood_xgb/)
- [x] Step 4: Fix confidence intervals (verified 2026-09-24: quantile q10/q90 for 100+ sample assets, live ci_method labels, measured holdout coverage in metadata, 183 tests)
- [x] Step 5: Real-time WAI computation (verified 2026-09-24: ml/models/wai_computer.py; live asset 9 WAI=19 Severe; 144 tests, tsc OK)
- [x] Step 6: Frontend dashboard components (verified 2026-09-24: national overview + alert panel + forecast chart + CI badges on v2 tab, all 11 assets, tsc clean, dev server page 200)

**Data tasks (background — can be parallel):**
- [ ] Ingest GRDC files (already on disk, 42 stations)
- [ ] Email WAPDA for barrage historical data
- [ ] Setup Open-Meteo rainfall auto-fetch
- [ ] Setup GEE Sentinel-2 auto-fetch

### Week 3: INTEGRATION
- [ ] Barrage data arrives → plug into routing
- [ ] Test full pipeline end-to-end
- [ ] Deploy v2.1

## Implementation Steps (Detailed)

### Step 1: Retrain ML Targeting Discharge (Day 1) — DONE 2026-09-24
Targets per ml/targets.py (data-driven): assets 1,2 → **outflow** (discharge_cusecs only
2 REAL rows; storage_volume 100% empty → true mass balance impossible — documented deviation
from "Tarbela mass balance" below), assets 9,10 → **discharge**, barrages 3-8,11 → **inflow**
explicit fallback (inference uses physics routing).
- ml/targets.py → resolve_target_field / flow_baseline_cusecs (never returns "auto")
- scripts/retrain_all_models.py → both predictors use resolve_target_field
- flood_predictor.py → output-field routing per saved target_field; HighFlowPredictor target_field param
- engine.py → store concrete predicted_* field (fixes all-NULL rows for assets 9,10); horizons [3,7,14,30]
- Retrain: 81 success / 7 skipped / 0 failed; holdout MAPE: asset 1=33%, 9=22%, 10=29%, 2=112% (Mangla outflow near-zero denominators — honest, no dummy values)

### Step 2: Fix prediction_v2.py Discharge (Day 1) — DONE 2026-09-24
- ML assets 1,2: outflow model → discharge lead-time values; method `ml_xgboost_outflow`
- ML assets 9,10: discharge model; method `ml_xgboost_discharge`; level-only models excluded
  (legacy level-as-cusecs unit bug removed)
- Physics assets 3-8,11: upstream routing; method `physics_routing`
- flow baseline + stress trend target-aware via ml.targets.flow_baseline_cusecs
- compute_accuracy/seed/evaluate: predicted_outflow matching added; seeds aligned to resolve_target_field
- Verified live: asset 1 3d=121,017 cusecs (0.725), 9=13,855 (0.777), 10=15,057 (0.744), 5 physics NOT_VALIDATED

### Step 3: Add 3-Day Horizon (Day 1) — DONE 2026-09-24
- scripts/retrain_all_models.py → horizons [3,7,14,30]
- flood_predictor train(persist=True) guard so seed does not pollute models
- 81 success / 7 skipped / 0 failed; host-persisted via docker cp

### Step 4: Fix Confidence Intervals (Day 2) — DONE 2026-09-24
- Quantile regression (q10/q90, `reg:quantileerror`) for assets with 100+ samples and
  persist=True → assets 1,2,9,10 × horizons [3,7,14,30] = 16 `{key}_interval.joblib` files;
  barrages (~30-60 rows) and holdout seeds skip them
- predict() CI chain: quantile → residual_p90 band → legacy R² band (last resort);
  every prediction carries `ci_method` (`quantile_q10_q90` | `residual_p90` | `r2_band` |
  `physics_band` | `pct_heuristic`) through prediction_v2 → DischargeResponse API schema
- Measured holdout coverage recorded honestly: raw q10-q90 coverage observed 0.33-0.81
  vs 0.80 target (kept as `ci_coverage_80_raw`); `ci_coverage_90` for residual bands
  (~0.90 by construction)
- **Conformal calibration (rec #1, 2026-09-24):** split-conformal inflation on the holdout
  (80th pct of nonconformity scores, additive, original units) so shipped bands reach the
  0.80 coverage target; raw coverage kept as `ci_coverage_80_raw`, offset as `ci_inflation`;
  legacy interval files load with inflation=0
- forecast-chart endpoint: CI band fixed for 7d/14d points (was 3d-only); ft-vs-cusecs
  threshold unit bug removed (no rating curve ⇒ None, never mixes units)
- Fixes dual-use training_mae bug (load path now fills dedicated residual_p90 dict)
- compose: models/ bind-mounted to /app/models so container recreates never wipe models
- Verified: 183 tests (new tests/unit/test_confidence_intervals.py, 15 cases);
  live assets 1,9,10 → quantile_q10_q90 + coverage, asset 5 → physics_band

### Step 5: Real-Time WAI (Day 2) — DONE 2026-09-24
- ml/models/wai_computer.py → flow 0.50 / storage 0.30 / trend 0.20 from water_observations (90d)
- Stale weekly indicator only as fallback; never invents a default score
- prediction_v2._get_wai_data rewired; no-WAI → category "No Data"
- rain/et anomalies honest None (weather_forecasts empty)

### Step 6: Frontend Dashboard (Days 3-5) — DONE 2026-09-24
- water/predictions v2 tab: National Overview card (national WAI, status, assets
  monitored, province chips, critical-alert panel) from GET /water/v2/national-overview
- Forecast chart (recharts): 30-day actual + 3/7/14 lead-time forecast + q10-q90
  interval band from GET /water/v2/asset/{id}/forecast-chart
- CI provenance badges per lead-time card (Quantile 80% CI / Residual ±p90 / Physics band /
  ±15% heuristic) + holdout coverage % from model_metadata.ci_coverage_80
- All 11 assets in selector (added 3 Chashma, 4 Kalabagh, 11 Panjnad)
- waterApi.getV2ForecastChart() + V2ForecastChart/V2DischargePrediction.ci_method types
- Verified: tsc --noEmit clean; dev server /water/predictions 200; endpoints smoke-tested

## Data Gap Solutions

### GAP 1: Barrage History → Email WAPDA
- Need: 5+ years discharge for assets 3-8,11
- Solution: Formal request to WAPDA Head Office Lahore
- Priority: MEDIUM (routing works without it)

### GAP 2: GRDC → Ingest Existing Files
- Have: 42 stations on disk
- Solution: Python script to parse + ingest
- Priority: HIGH (needed for routing validation)

### GAP 3: Rainfall → Open-Meteo Auto-Fetch
- Have: API configured, nearly empty
- Solution: Auto-fetch 16-day forecast weekly
- Priority: HIGH (critical for alerts)

### GAP 4: Satellite → GEE Sentinel-2
- Have: Service account configured
- Solution: Auto-fetch MNDWI weekly
- Priority: MEDIUM (nice-to-have)

### GAP 5: Sensors → Skip for Now
- Option C: Use existing WAPDA daily reports
- Priority: LOW (can skip for FYP)

## Architecture Diagram

```
                    ┌─────────────────────────────┐
                    │    AquaVision v2 API         │
                    │  GET /water/v2/predict/{id}  │
                    └──────────┬──────────────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │  AquaVisionPredictionModel   │
                    │     prediction_v2.py         │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼────────┐ ┌────▼─────┐ ┌────────▼────────┐
    │  ML Predictor    │ │ Physics  │ │  WAI Computer   │
    │ (assets 2,9,10)  │ │ Routing  │ │ (live from DB)  │
    │ discharge direct │ │ (3-8,11) │ │                 │
    └─────────┬────────┘ └────┬─────┘ └────────┬────────┘
              │                │                │
    ┌─────────▼────────┐ ┌────▼─────┐ ┌────────▼────────┐
    │ XGBoost .joblib  │ │ Upstream │ │ indicators      │
    │ (retrained for   │ │ Obs +    │ │ _weekly +       │
    │  discharge)      │ │ Travel   │ │ weather         │
    │                  │ │ Times    │ │ forecasts       │
    └──────────────────┘ └──────────┘ └─────────────────┘
```

## Timeline

| Week | Focus | Deliverable |
|------|-------|-------------|
| Week 1 | ML retrain + v2 fix | 4 assets predicting discharge |
| Week 2 | CI + WAI + Frontend | Dashboard showing predictions |
| Week 3 | Integration + testing | Full production system |
