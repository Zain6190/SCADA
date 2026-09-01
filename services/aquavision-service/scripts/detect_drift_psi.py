"""
PSI (Population Stability Index) Drift Detection.
Compares recent feature distributions against training baseline.
PSI < 0.1 = stable, 0.1-0.25 = moderate drift, > 0.25 = significant drift.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger("psi_drift")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_BASE_DIR = Path(os.environ.get("AQUAVISION_BASE_DIR", "/app"))
ASSET_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

# Key features to monitor (most important for model performance)
KEY_FEATURES = [
    "level", "inflow", "outflow", "discharge",
    "level_lag_1d", "inflow_lag_1d",
    "level_rollmean_7d", "inflow_rollmean_7d",
]


def get_db():
    from infrastructure.db.engine import engine
    return engine


def compute_psi(baseline: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """Compute Population Stability Index between two distributions.
    
    PSI < 0.1:   No significant change (STABLE)
    PSI 0.1-0.25: Moderate drift (MODERATE)
    PSI > 0.25:  Significant drift (SIGNIFICANT)
    """
    # Avoid division by zero
    baseline = baseline[~np.isnan(baseline)]
    current = current[~np.isnan(current)]
    
    if len(baseline) < 10 or len(current) < 10:
        return 0.0
    
    # Create bins from baseline
    min_val = min(baseline.min(), current.min())
    max_val = max(baseline.max(), current.max())
    
    if min_val == max_val:
        return 0.0
    
    bins = np.linspace(min_val, max_val, n_bins + 1)
    
    # Compute histograms
    baseline_hist, _ = np.histogram(baseline, bins=bins)
    current_hist, _ = np.histogram(current, bins=bins)
    
    # Normalize to proportions (avoid zero)
    baseline_prop = baseline_hist / len(baseline) + 1e-6
    current_prop = current_hist / len(current) + 1e-6
    
    # PSI formula
    psi = np.sum((current_prop - baseline_prop) * np.log(current_prop / baseline_prop))
    return float(psi)


def compute_ks_statistic(baseline: np.ndarray, current: np.ndarray) -> float:
    """Compute Kolmogorov-Smirnov statistic (max CDF difference)."""
    baseline = baseline[~np.isnan(baseline)]
    current = current[~np.isnan(current)]
    
    if len(baseline) < 5 or len(current) < 5:
        return 0.0
    
    all_vals = np.sort(np.concatenate([baseline, current]))
    cdf_baseline = np.searchsorted(np.sort(baseline), all_vals, side='right') / len(baseline)
    cdf_current = np.searchsorted(np.sort(current), all_vals, side='right') / len(current)
    
    return float(np.max(np.abs(cdf_baseline - cdf_current)))


def get_asset_features(asset_id: int, conn):
    """Get feature values for an asset from recent observations."""
    from sqlalchemy import text
    
    # Get recent observations (last 30 days) as current distribution
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cutoff_180d = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    
    rows = conn.execute(text("""
        SELECT observed_at, water_level_ft, inflow_cusecs, outflow_cusecs, discharge_cusecs
        FROM aquavision.water_observations
        WHERE asset_id = :asset_id
          AND observed_at >= :cutoff
          AND (water_level_ft IS NOT NULL OR inflow_cusecs IS NOT NULL 
               OR outflow_cusecs IS NOT NULL OR discharge_cusecs IS NOT NULL)
        ORDER BY observed_at
    """), {"asset_id": asset_id, "cutoff": cutoff_180d}).mappings().all()
    
    if len(rows) < 20:
        return None, None
    
    # Build feature arrays
    recent_features = {f: [] for f in KEY_FEATURES}
    baseline_features = {f: [] for f in KEY_FEATURES}
    
    values = [dict(r) for r in rows]
    
    for i, row in enumerate(values):
        level = float(row["water_level_ft"]) if row["water_level_ft"] else 0.0
        inflow = float(row["inflow_cusecs"]) if row["inflow_cusecs"] else 0.0
        outflow = float(row["outflow_cusecs"]) if row["outflow_cusecs"] else 0.0
        discharge = float(row["discharge_cusecs"]) if row["discharge_cusecs"] else 0.0
        
        # Current values
        feat = {
            "level": level,
            "inflow": inflow,
            "outflow": outflow,
            "discharge": discharge,
        }
        
        # Lag features
        if i >= 1:
            prev = values[i-1]
            feat["level_lag_1d"] = float(prev["water_level_ft"]) if prev["water_level_ft"] else 0.0
            feat["inflow_lag_1d"] = float(prev["inflow_cusecs"]) if prev["inflow_cusecs"] else 0.0
        else:
            feat["level_lag_1d"] = level
            feat["inflow_lag_1d"] = inflow
        
        # Rolling mean (7-day window)
        window_start = max(0, i - 6)
        window = values[window_start:i+1]
        feat["level_rollmean_7d"] = np.mean([
            float(w["water_level_ft"]) for w in window if w["water_level_ft"]
        ]) if any(w["water_level_ft"] for w in window) else level
        feat["inflow_rollmean_7d"] = np.mean([
            float(w["inflow_cusecs"]) for w in window if w["inflow_cusecs"]
        ]) if any(w["inflow_cusecs"] for w in window) else inflow
        
        # Split into baseline (first 150 days) and recent (last 30 days)
        row_date = row["observed_at"]
        if isinstance(row_date, str):
            row_date = datetime.fromisoformat(row_date.replace("Z", "+00:00"))
        
        is_recent = row_date > datetime.now(timezone.utc) - timedelta(days=30)
        
        for f in KEY_FEATURES:
            if f in feat:
                if is_recent:
                    recent_features[f].append(feat[f])
                else:
                    baseline_features[f].append(feat[f])
    
    return baseline_features, recent_features


def detect_drift_for_asset(asset_id: int, conn):
    """Compute PSI drift metrics for a single asset."""
    baseline, current = get_asset_features(asset_id, conn)
    
    if baseline is None or current is None:
        return []
    
    results = []
    
    for feature in KEY_FEATURES:
        base_vals = np.array(baseline.get(feature, []), dtype=np.float64)
        curr_vals = np.array(current.get(feature, []), dtype=np.float64)
        
        if len(base_vals) < 10 or len(curr_vals) < 10:
            continue
        
        psi = compute_psi(base_vals, curr_vals)
        ks = compute_ks_statistic(base_vals, curr_vals)
        
        # Determine drift status
        if psi > 0.25:
            drift_status = "SIGNIFICANT"
        elif psi > 0.1:
            drift_status = "MODERATE"
        else:
            drift_status = "STABLE"
        
        results.append({
            "asset_id": asset_id,
            "feature_name": feature,
            "psi": round(psi, 4),
            "ks_statistic": round(ks, 4),
            "mean_current": round(float(np.mean(curr_vals)), 2),
            "mean_baseline": round(float(np.mean(base_vals)), 2),
            "std_current": round(float(np.std(curr_vals)), 2),
            "std_baseline": round(float(np.std(base_vals)), 2),
            "drift_status": drift_status,
            "evaluation_window": "30d",
        })
    
    return results


def store_feature_drift(results, conn):
    """Store PSI results in feature_drift table."""
    from sqlalchemy import text
    stored = 0
    
    for r in results:
        try:
            conn.execute(text("""
                INSERT INTO aquavision.feature_drift
                    (asset_id, feature_name, psi, ks_statistic,
                     mean_current, mean_baseline, std_current, std_baseline,
                     drift_status, evaluation_window, computed_at)
                VALUES
                    (:asset_id, :feature_name, :psi, :ks_statistic,
                     :mean_current, :mean_baseline, :std_current, :std_baseline,
                     :drift_status, :evaluation_window, now())
            """), r)
            stored += 1
        except Exception as e:
            logger.error(f"Failed to store drift for {r['feature_name']}: {e}")
    
    conn.commit()
    return stored


def main():
    """Run PSI drift detection for all assets."""
    engine = get_db()
    
    all_results = []
    
    with engine.connect() as conn:
        for asset_id in ASSET_IDS:
            try:
                results = detect_drift_for_asset(asset_id, conn)
                all_results.extend(results)
                
                significant = [r for r in results if r["drift_status"] == "SIGNIFICANT"]
                moderate = [r for r in results if r["drift_status"] == "MODERATE"]
                
                if significant or moderate:
                    logger.info(f"Asset {asset_id}: {len(significant)} significant, {len(moderate)} moderate drift")
                else:
                    logger.info(f"Asset {asset_id}: all features stable")
            except Exception as e:
                logger.error(f"Drift detection failed for asset {asset_id}: {e}")
        
        # Store results
        stored = store_feature_drift(all_results, conn)
    
    # Summary
    by_status = {"STABLE": 0, "MODERATE": 0, "SIGNIFICANT": 0}
    for r in all_results:
        by_status[r["drift_status"]] = by_status.get(r["drift_status"], 0) + 1
    
    summary = {
        "total_features": len(all_results),
        "stored": stored,
        "by_status": by_status,
        "assets_checked": len(ASSET_IDS),
    }
    
    logger.info(f"PSI drift detection complete: {stored} features stored, {by_status}")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
