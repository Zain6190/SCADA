"""
ml/features/gee_service.py
AquaVision - Google Earth Engine feature fetcher (P5).

Datasets pulled per active asset point, stored in aquavision.gee_features:
  CHIRPS DAILY - precipitation mm/day        UCSB-CHG/CHIRPS/DAILY   scale 5566 m
  MOD16A2      - evapotranspiration mm/8day  MODIS/061/MOD16A2       scale 0.1
  MOD13Q1      - NDVI 16-day composite       MODIS/061/MOD13Q1       scale 0.0001

Requires GEE_PROJECT (GCP project with Earth Engine API enabled) and
credentials at ~/.config/earthengine/credentials inside the container.

Usage:
    from ml.features.gee_service import GeeFeatureService
    svc = GeeFeatureService(session)
    stats = svc.refresh_all_assets(days_back=10)
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger("aquavision.ml.gee")

CHIRPS_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_BAND = "precipitation"
CHIRPS_SCALE = 5566
CHIRPS_FACTOR = 1.0

MOD16_ID = "MODIS/061/MOD16A2"
MOD16_BAND = "ET"
MOD16_SCALE = 500
MOD16_FACTOR = 0.1

MOD13_ID = "MODIS/061/MOD13Q1"
MOD13_BAND = "NDVI"
MOD13_SCALE = 250
MOD13_FACTOR = 0.0001
MOD13_VALID_RAW = (-2000, 10000)


def _row_time_value(row: list) -> Tuple[object, object]:
    """getRegion rows are [id, lon, lat, time, value] (header first when
    serialized); older 4-column [lon, lat, time, value] rows also work."""
    if len(row) >= 5:
        return row[3], row[4]
    if len(row) >= 4:
        return row[2], row[3]
    return None, None


def region_rows_to_series(
    rows: Optional[List[list]],
    factor: float = 1.0,
    valid_raw: Optional[Tuple[float, float]] = None,
) -> Dict[date, float]:
    """Parse ee.ImageCollection.getRegion rows into {date: scaled_value}.

    Header rows, nulls, and raw values outside valid_raw (e.g. MOD13 fill
    -3000) are dropped.
    """
    series: Dict[date, float] = {}
    for row in rows or []:
        if not row:
            continue
        time_ms, value = _row_time_value(row)
        if time_ms is None or value is None:
            continue
        try:
            raw = float(value)
        except (TypeError, ValueError):
            continue
        if valid_raw is not None and not (valid_raw[0] <= raw <= valid_raw[1]):
            continue
        try:
            day = datetime.fromtimestamp(int(float(time_ms)) / 1000, tz=timezone.utc).date()
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        series[day] = round(raw * factor, 4)
    return series


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _fetch_region(collection, point, scale: int) -> List[list]:
    """getRegion rows for a collection; EE occasionally throws transient
    'Unable to transform geometry' errors, so retry. Empty collections
    (beyond catalog lag) return [] instead of failing."""
    if collection.size().getInfo() == 0:
        return []
    return collection.getRegion(point, scale).getInfo()


def merge_series(
    rainfall: Dict[date, float],
    et: Dict[date, float],
    ndvi: Dict[date, float],
) -> Dict[date, Dict[str, float]]:
    """Merge per-dataset series into {date: {rainfall_mm?, et_mm?, ndvi?}}."""
    merged: Dict[date, Dict[str, float]] = {}
    for field, series in (
        ("rainfall_mm", rainfall),
        ("et_mm", et),
        ("ndvi", ndvi),
    ):
        for day, value in series.items():
            merged.setdefault(day, {})[field] = value
    return dict(sorted(merged.items()))


class GeeFeatureService:
    """Fetch and store GEE raster features for water assets."""

    def __init__(self, session: Session, ee_module=None):
        self.session = session
        self.ee = ee_module

    def _ee(self):
        if self.ee is not None:
            return self.ee
        import ee

        project = os.environ.get("GEE_PROJECT")
        if not project:
            raise RuntimeError("GEE_PROJECT is not set - Earth Engine needs a GCP project")
        ee.Initialize(project=project)
        self.ee = ee
        return ee

    def fetch_series(self, lat: float, lon: float, start: date, end: date) -> Dict[date, Dict[str, float]]:
        """Point-sample CHIRPS/MOD16/MOD13 over [start, end) for one location."""
        ee = self._ee()
        point = ee.Geometry.Point([lon, lat])
        start_iso, end_iso = start.isoformat(), end.isoformat()

        def pull(image_id: str, band: str, scale: int, factor: float = 1.0,
                 valid_raw: Optional[Tuple[float, float]] = None) -> Dict[date, float]:
            collection = (
                ee.ImageCollection(image_id)
                .filter(ee.Filter.date(start_iso, end_iso))
                .select(band)
            )
            rows = _fetch_region(collection, point, scale)
            return region_rows_to_series(rows, factor, valid_raw)

        return merge_series(
            pull(CHIRPS_ID, CHIRPS_BAND, CHIRPS_SCALE, factor=CHIRPS_FACTOR),
            pull(MOD16_ID, MOD16_BAND, MOD16_SCALE, factor=MOD16_FACTOR),
            pull(MOD13_ID, MOD13_BAND, MOD13_SCALE, factor=MOD13_FACTOR,
                 valid_raw=MOD13_VALID_RAW),
        )

    def store(self, asset_id: int, day: date, fields: Dict[str, float]) -> None:
        """Upsert one asset-day; COALESCE keeps columns refreshed by other runs."""
        self.session.execute(
            text("""
                INSERT INTO aquavision.gee_features
                    (asset_id, observed_on, rainfall_mm, et_mm, ndvi, fetched_at)
                VALUES
                    (:asset_id, :observed_on, :rainfall, :et, :ndvi, now())
                ON CONFLICT (asset_id, observed_on)
                DO UPDATE SET
                    rainfall_mm = COALESCE(EXCLUDED.rainfall_mm, aquavision.gee_features.rainfall_mm),
                    et_mm = COALESCE(EXCLUDED.et_mm, aquavision.gee_features.et_mm),
                    ndvi = COALESCE(EXCLUDED.ndvi, aquavision.gee_features.ndvi),
                    fetched_at = now()
            """),
            {
                "asset_id": asset_id,
                "observed_on": day,
                "rainfall": fields.get("rainfall_mm"),
                "et": fields.get("et_mm"),
                "ndvi": fields.get("ndvi"),
            },
        )
        self.session.commit()

    def refresh_all_assets(self, days_back: int = 60) -> Dict[str, int]:
        """Fetch and store features for all active assets with coordinates.

        Default window covers the EE catalog's publish lag (CHIRPS/MOD13
        trail by ~30 days); upserts make re-fetching overlap days free.
        Returns {"assets": n, "days": n, "errors": n}.
        """
        self._ee()

        assets = self.session.execute(
            text("""
                SELECT id, latitude, longitude
                FROM aquavision.water_assets
                WHERE is_active = true
                AND latitude IS NOT NULL
                AND longitude IS NOT NULL
                ORDER BY id
            """)
        ).mappings().all()

        start = date.today() - timedelta(days=days_back)
        end = date.today() + timedelta(days=1)
        stats = {"assets": 0, "days": 0, "errors": 0}

        for asset in assets:
            aid = asset["id"]
            try:
                series = self.fetch_series(
                    float(asset["latitude"]),
                    float(asset["longitude"]),
                    start,
                    end,
                )
                for day, fields in series.items():
                    self.store(aid, day, fields)
                    stats["days"] += 1
                stats["assets"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"GEE feature fetch failed for asset {aid}: {e}")

        logger.info(
            f"GEE features: {stats['assets']} assets, {stats['days']} asset-days, "
            f"{stats['errors']} errors ({start} -> {end})"
        )
        return stats
