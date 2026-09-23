# Prediction Module Completion Plan
# ================================
# Created: 2026-09-21
# Updated: 2026-09-21
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
- [ ] Step 1: Retrain ML models targeting DISCHARGE (assets 2,9,10)
- [ ] Step 2: Fix prediction_v2.py discharge logic
- [ ] Step 3: Add 3-day horizon to training
- [ ] Step 4: Fix confidence intervals
- [ ] Step 5: Real-time WAI computation
- [ ] Step 6: Frontend dashboard components

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

### Step 1: Retrain ML Targeting Discharge (Day 1)
Currently ML targets water_level_ft. Retrain targeting discharge_cusecs.

Files to modify:
- ml/features/feature_engineering.py → change target column
- scripts/retrain_all_models.py → add discharge target option
- ml/models/flood_predictor.py → handle discharge output

Assets: 2 (Mangla), 9 (Kabul), 10 (Chenab) — have enough data.

### Step 2: Fix prediction_v2.py Discharge (Day 1)
- ML assets (2,9,10): Use discharge ML model directly
- Physics assets (3-8,11): Use upstream routing (already works)
- Tarbela (1): Use mass balance (inflow prediction)

### Step 3: Add 3-Day Horizon (Day 1)
- scripts/retrain_all_models.py → add horizon=3

### Step 4: Fix Confidence Intervals (Day 2)
- Quantile regression for assets with 100+ samples (Kabul, Mangla, Chenab)
- Simple bands for barrages (limited data)

### Step 5: Real-Time WAI (Day 2)
- ml/models/wai_computer.py → compute from latest observations
- Replace static July 2026 data

### Step 6: Frontend Dashboard (Days 3-5)
- National overview page
- Asset detail page with forecast charts
- Alert panel

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
