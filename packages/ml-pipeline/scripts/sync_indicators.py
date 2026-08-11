"""
scripts/sync_indicators.py
AquaVision - Populate aquavision.water_indicators_weekly from REAL GEE data.

This is the missing link that makes the live app serve actual satellite-derived
indicators instead of the seed_if_empty() demo rows:

  * Reads Data/raw/region_features.csv (CHIRPS rain, ERA5-Land ET, JRC water,
    Sentinel-2 NDVI) produced by gee.gee_fetch.
  * Computes WAI + severity with the SAME transparent composite as
    gee/build_labels.py (per-region min-max normalize -> weighted mean ->
    severity buckets), so dashboard numbers equal the model's training labels.
  * Computes rainfall_anomaly / et_anomaly vs each region's own historical mean
    (same proxy as scripts.run_risk_alerts).
  * Upserts into water_indicators_weekly keyed on (region_id, week_start_date)
    with honest provenance (data_provider=GEE, data_source_version, status).

The app's seed_if_empty() only seeds tables that are empty, so once real rows
exist the demo generator is bypassed automatically.

Usage:
    python -m scripts.sync_indicators   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

from gee.build_labels import compute_wai, classify

ML_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ML_ROOT / "Data" / "raw" / "region_features.csv"
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
SOURCE_VERSION = os.getenv("GEE_SOURCE_VERSION", "GEE-CHIRPS/ERA5-JRC-2026.8")
MODEL_VERSION = os.getenv("GEE_WAI_VERSION", "composite-v1.0")
# Set by the orchestrator when the source CSV could not be refreshed: rows are
# published as quality_status='STALE' + data_status='Stale' instead of VALID so
# stale satellite data can never be presented as fresh.
FORCE_STALE = os.getenv("SYNC_DATA_STATUS", "").strip().upper() == "STALE"

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
    return _engine


def district_ids() -> list[int]:
    with engine().connect() as conn:
        rows = conn.execute(
            text("SELECT id FROM shared.regions WHERE type = 'district' ORDER BY id")
        ).fetchall()
    return [int(r.id) for r in rows]


def _num(value) -> float | None:
    """Coerce a value to a rounded float, or None when NaN/Inf (Postgres
    NUMERIC rejects NaN and the API's JSON encoder chokes on it)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 2)


def anomaly_pct(series: pd.Series, value: float) -> float | None:
    """% deviation of a value from its series mean (0 if mean is 0)."""
    if value is None or np.isnan(value):
        return None
    mean = series.mean()
    if not mean or np.isnan(mean):
        return 0.0
    return float((value - mean) / mean * 100.0)


def _month_days(month: pd.Timestamp) -> int:
    return int(month.days_in_month)


# Physical-range validation gates. Out-of-range values are quarantined (never
# published to the dashboard) and counted as skipped.
BOUNDS = {
    "rainfall_mm": (0.0, 2000.0),
    "et_mm": (0.0, 500.0),
    "ndvi": (-1.0, 1.0),
    "water_extent": (0.0, 1.0),
}


def _in_bounds(value, lo, hi) -> bool:
    if value is None or np.isnan(value):
        return True  # missing is handled by completeness, not by bounds
    return lo <= float(value) <= hi


def build_rows(feats: pd.DataFrame, districts: list[int]) -> tuple[list[dict], int]:
    """Per district-month -> indicator row with WAI, severity, anomalies and
    completeness/quality. Returns (valid_rows, skipped_count).

    A month is COMPLETE only when both rainfall and ET are present (CHIRPS and
    ERA5-Land finalized). A trailing month with missing rainfall is PARTIAL and
    is published with quality_status='PARTIAL' + is_complete_period=False so it
    is never interpreted as 'no rain'. Rows failing physical bounds are
    quarantined (skipped) rather than published.
    """
    labeled = compute_wai(feats)
    labeled = labeled[labeled["region_id"].isin(districts)].copy()
    labeled["month"] = pd.to_datetime(labeled["month"])

    rows: list[dict] = []
    skipped = 0
    for _, r in labeled.sort_values(["region_id", "month"]).iterrows():
        rainfall = None if np.isnan(r["rainfall_mm"]) else float(r["rainfall_mm"])
        et = float(r["et_mm"]) if (not np.isnan(r["et_mm"]) and r["et_mm"] > 0) else None
        ndvi = None if np.isnan(r["ndvi"]) else float(r["ndvi"])
        water_extent = None if (r["water_extent"] == -1 or np.isnan(r["water_extent"])) else float(r["water_extent"])

        # ---- validation gates: quarantine out-of-range rows ----
        if not _in_bounds(rainfall, *BOUNDS["rainfall_mm"]):
            skipped += 1
            continue
        if et is not None and not _in_bounds(et, *BOUNDS["et_mm"]):
            skipped += 1
            continue
        if ndvi is not None and not _in_bounds(ndvi, *BOUNDS["ndvi"]):
            skipped += 1
            continue
        if water_extent is not None and not _in_bounds(water_extent, *BOUNDS["water_extent"]):
            skipped += 1
            continue

        # ---- completeness: complete only when rain + ET finalized ----
        complete = rainfall is not None and et is not None
        expected = _month_days(r["month"])

        hist = labeled[labeled["region_id"] == r["region_id"]]
        prev = labeled[
            (labeled["region_id"] == r["region_id"])
            & (labeled["month"] == r["month"] - pd.DateOffset(months=1))
        ]
        sw_change = None
        if not prev.empty and prev.iloc[0]["water_extent"] != -1 and r["water_extent"] != -1 \
                and not np.isnan(prev.iloc[0]["water_extent"]) and not np.isnan(r["water_extent"]):
            sw_change = _num((r["water_extent"] - prev.iloc[0]["water_extent"]) * 100.0)

        rows.append(
            dict(
                region_id=int(r["region_id"]),
                week_start_date=r["month"],
                week_number=int(r["month"].isocalendar()[1]),
                year=int(r["month"].year),
                period_start=r["month"],
                period_end=r["month"] + pd.offsets.MonthEnd(0),
                surface_water_area_km2=None,
                surface_water_change_pct=sw_change,
                rainfall_mm_30day=_num(rainfall),
                rainfall_anomaly=_num(anomaly_pct(hist["rainfall_mm"], rainfall)),
                et_mm_8day=_num(et),
                et_anomaly=_num(anomaly_pct(hist.loc[hist["et_mm"] > 0, "et_mm"], et)) if et is not None else None,
                wai_score=_num(r["wai_score"]),
                severity=classify(float(r["wai_score"])),
                is_complete_period=complete,
                coverage_percent=_num(100.0) if complete else None,
                observation_count=expected if complete else None,
                expected_observation_count=expected,
                quality_status=(
                    "STALE" if FORCE_STALE and complete else ("VALID" if complete else "PARTIAL")
                ),
                data_status="Stale" if FORCE_STALE else "Actual",
                source_observed_at=r["month"] + pd.offsets.MonthEnd(0),
            )
        )
    return rows, skipped


def upsert_rows(rows: list[dict]) -> None:
    eng = engine()
    with eng.begin() as conn:
        for r in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO aquavision.water_indicators_weekly
                        (region_id, week_start_date, week_number, year,
                         period_start, period_end, is_complete_period,
                         coverage_percent, observation_count,
                         expected_observation_count, quality_status,
                         surface_water_area_km2, surface_water_change_pct,
                         rainfall_mm_30day, rainfall_anomaly, et_mm_8day, et_anomaly,
                         wai_score, severity, data_source_version, data_status,
                         data_quality, data_provider, wai_model_version,
                         source_observed_at, last_validated_at)
                    VALUES
                        (:region_id, :week, :week_number, :year,
                         :period_start, :period_end, :complete,
                         :coverage, :observation_count, :expected_count, :quality,
                         :sw_area, :sw_change, :rain, :rain_anom, :et, :et_anom,
                         :wai, :severity, :source_version, :data_status, 'Good', 'GEE',
                         :model_version, :observed_at, now())
                    ON CONFLICT (region_id, week_start_date)
                    DO UPDATE SET
                        week_number = EXCLUDED.week_number,
                        year = EXCLUDED.year,
                        period_start = EXCLUDED.period_start,
                        period_end = EXCLUDED.period_end,
                        is_complete_period = EXCLUDED.is_complete_period,
                        coverage_percent = EXCLUDED.coverage_percent,
                        observation_count = EXCLUDED.observation_count,
                        expected_observation_count = EXCLUDED.expected_observation_count,
                        quality_status = EXCLUDED.quality_status,
                        surface_water_change_pct = EXCLUDED.surface_water_change_pct,
                        rainfall_mm_30day = EXCLUDED.rainfall_mm_30day,
                        rainfall_anomaly = EXCLUDED.rainfall_anomaly,
                        et_mm_8day = EXCLUDED.et_mm_8day,
                        et_anomaly = EXCLUDED.et_anomaly,
                        wai_score = EXCLUDED.wai_score,
                        severity = EXCLUDED.severity,
                        data_source_version = EXCLUDED.data_source_version,
                        data_status = EXCLUDED.data_status,
                        data_quality = EXCLUDED.data_quality,
                        data_provider = EXCLUDED.data_provider,
                        wai_model_version = EXCLUDED.wai_model_version,
                        source_observed_at = EXCLUDED.source_observed_at,
                        last_validated_at = now()
                    """
                ),
                {
                    "region_id": r["region_id"],
                    "week": r["week_start_date"].strftime("%Y-%m-%d"),
                    "week_number": r["week_number"],
                    "year": r["year"],
                    "period_start": r["period_start"].strftime("%Y-%m-%d"),
                    "period_end": r["period_end"].strftime("%Y-%m-%d"),
                    "complete": r["is_complete_period"],
                    "coverage": r["coverage_percent"],
                    "observation_count": r["observation_count"],
                    "expected_count": r["expected_observation_count"],
                    "quality": r["quality_status"],
                    "sw_area": r["surface_water_area_km2"],
                    "sw_change": r["surface_water_change_pct"],
                    "rain": r["rainfall_mm_30day"],
                    "rain_anom": r["rainfall_anomaly"],
                    "et": r["et_mm_8day"],
                    "et_anom": r["et_anomaly"],
                    "wai": r["wai_score"],
                    "severity": r["severity"],
                    "source_version": SOURCE_VERSION,
                    "data_status": r["data_status"],
                    "model_version": MODEL_VERSION,
                    "observed_at": r["source_observed_at"].strftime("%Y-%m-%d"),
                },
            )
    print(f"[sync_indicators] Upserted {len(rows)} indicator rows")
    if FORCE_STALE:
        n_stale = sum(1 for r in rows if r["quality_status"] == "STALE")
        print(f"[sync_indicators] Marked {n_stale} rows STALE (source CSV not refreshed)")


def run() -> dict:
    """Execute the sync and return an observable summary (for the orchestrator)."""
    feats = pd.read_csv(RAW_CSV)
    feats["month"] = pd.to_datetime(feats["month"])
    districts = district_ids()
    if not districts:
        raise RuntimeError("No districts found in shared.regions")

    rows, skipped = build_rows(feats, districts)
    if not rows:
        raise RuntimeError("No valid district-months to sync")

    print(f"[sync_indicators] Read {len(feats)} rows")
    upsert_rows(rows)

    span = (min(r["week_start_date"] for r in rows), max(r["week_start_date"] for r in rows))
    partial = sum(1 for r in rows if not r["is_complete_period"])
    sev = pd.Series([r["severity"] for r in rows]).value_counts()
    print(f"[sync_indicators] {len(rows)} rows across {span[0].date()} .. {span[1].date()}")
    print(f"[sync_indicators] PARTIAL (incomplete) periods: {partial}")
    print(f"[sync_indicators] Skipped {skipped} invalid rows")
    print(f"[sync_indicators] Severity distribution:\n{sev.to_string()}")
    return {
        "records_read": len(feats),
        "records_written": len(rows),
        "records_skipped": skipped,
        "warning_count": partial,
        "span": f"{span[0].date()}..{span[1].date()}",
    }


def main() -> None:
    run()


if __name__ == "__main__":
    main()