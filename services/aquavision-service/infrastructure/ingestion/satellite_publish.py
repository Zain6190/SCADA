# Read the weekly satellite CSV and shape the rows the screens and reports use.
# Reservoir area is stored beside the asset. It does not change the IRSA level.
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FEATURES = REPO / "packages" / "ml-pipeline" / "Data" / "raw" / "region_features.csv"
SURFACE_CSV = REPO / "packages" / "ml-pipeline" / "Data" / "raw" / "surface_water.csv"
RESERVOIR_CSV = REPO / "packages" / "ml-pipeline" / "Data" / "raw" / "reservoir_surface.csv"
INDICATOR_TABLE = "aquavision.water_indicators_weekly"
OBSERVATION_TABLE = "aquavision.water_observations"

RESERVOIRS = (
    {"asset_id": 1, "name": "Tarbela", "lon": 72.6837, "lat": 34.0887},
    {"asset_id": 2, "name": "Mangla", "lon": 73.6437, "lat": 33.1387},
)


def reservoir_area_row(asset_id: int, observed_on: date, area_km2: float) -> dict:
    return {
        "asset_id": asset_id,
        "observed_on": observed_on.isoformat(),
        "area_km2": float(area_km2),
        "source_authority": "GEE",
        "method": "NDWI",
        "writes_irsa_level": False,
    }


def read_feature_rows(path: Path = FEATURES) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _num(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def latest_by_region(rows: list[dict] | None = None) -> list[dict]:
    chosen: dict[str, dict] = {}
    for row in rows if rows is not None else read_feature_rows():
        region_id = str(row.get("region_id") or "")
        month = str(row.get("month") or "")
        if not region_id or not month:
            continue
        current = chosen.get(region_id)
        if current is None or month > str(current.get("month") or ""):
            chosen[region_id] = row
    published = []
    for row in chosen.values():
        published.append({
            "region_id": int(row["region_id"]),
            "month": str(row["month"])[:10],
            "rainfall_mm": _num(row.get("rainfall_mm")),
            "et_mm": _num(row.get("et_mm")),
            "water_extent": _num(row.get("water_extent")),
            "ndvi": _num(row.get("ndvi")),
            "source": "Sentinel-2" if row.get("ndvi") not in (None, "") else "GEE",
        })
    return sorted(published, key=lambda item: item["region_id"])


def ndvi_history(rows: list[dict] | None = None) -> list[dict]:
    history = []
    for row in rows if rows is not None else read_feature_rows():
        value = _num(row.get("ndvi"))
        if value is None or not row.get("region_id") or not row.get("month"):
            continue
        history.append({
            "region_id": int(row["region_id"]),
            "month": str(row["month"])[:10],
            "ndvi": value,
            "source": "Sentinel-2",
        })
    return history


def ndvi_rows(rows: list[dict] | None = None) -> list[dict]:
    return [
        {
            "region_id": row["region_id"],
            "month": row["month"],
            "ndvi": row["ndvi"],
            "source": "Sentinel-2",
        }
        for row in latest_by_region(rows)
        if row["ndvi"] is not None
    ]


def latest_surface_area(path: Path = SURFACE_CSV) -> dict[int, dict]:
    if not path.exists():
        return {}
    chosen: dict[int, dict] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("region_id"):
                continue
            region_id = int(row["region_id"])
            week = str(row.get("week_start_date") or "")
            current = chosen.get(region_id)
            if current is not None and week < current["week"]:
                continue
            chosen[region_id] = {
                "week": week,
                "area_km2": _num(row.get("water_area_km2")),
                "change_pct": _num(row.get("change_pct")),
            }
    return chosen


def satellite_section(rows: list[dict] | None = None, names: dict[int, str] | None = None) -> dict:
    latest = latest_by_region(rows)
    names = names or {}
    areas = latest_surface_area()
    ranked = sorted(latest, key=lambda row: (row["rainfall_mm"] is None, row["rainfall_mm"] if row["rainfall_mm"] is not None else 0))
    worst = []
    for row in ranked[:5]:
        area = areas.get(row["region_id"], {})
        worst.append({
            "region_id": row["region_id"],
            "name": names.get(row["region_id"], f"District {row['region_id']}"),
            "rainfall_mm": row["rainfall_mm"],
            "et_mm": row["et_mm"],
            "surface_water": row["water_extent"],
            "surface_water_km2": area.get("area_km2"),
            "surface_water_change_pct": area.get("change_pct"),
            "ndvi": row["ndvi"],
        })
    image_week = max((row["month"] for row in latest), default=None)
    return {
        "image_week": image_week,
        "districts": len(latest),
        "worst_districts": worst,
        "source_version": "GEE-CHIRPS/MOD16-JRC",
    }


def latest_reservoir_area(asset_id: int) -> dict | None:
    if not RESERVOIR_CSV.exists():
        return None
    chosen = None
    with RESERVOIR_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("asset_id")) != str(asset_id):
                continue
            if chosen is None or str(row.get("observed_on") or "") >= str(chosen.get("observed_on") or ""):
                chosen = row
    if chosen is None:
        return None
    return {
        "asset_id": int(chosen["asset_id"]),
        "observed_on": chosen.get("observed_on"),
        "area_km2": _num(chosen.get("area_km2")),
        "source_authority": chosen.get("source_authority") or "GEE",
        "method": chosen.get("method") or "NDWI",
        "writes_irsa_level": False,
    }


def store_reservoir_areas(rows: list[dict]) -> int:
    """Insert satellite area rows. The statement never updates water_level_ft."""
    if not rows:
        return 0
    from sqlalchemy import text
    from infrastructure.db.engine import SessionLocal

    if SessionLocal is None:
        return 0
    written = 0
    with SessionLocal() as db:
        for row in rows:
            if row.get("writes_irsa_level"):
                continue
            db.execute(
                text(
                    """
                    INSERT INTO aquavision.water_satellite_area
                        (asset_id, observed_on, area_km2, source_authority, method)
                    VALUES
                        (:asset_id, :observed_on, :area_km2, :source_authority, :method)
                    ON CONFLICT (asset_id, observed_on, method) DO UPDATE
                        SET area_km2 = EXCLUDED.area_km2,
                            source_authority = EXCLUDED.source_authority
                    """
                ),
                {
                    "asset_id": row["asset_id"],
                    "observed_on": row["observed_on"],
                    "area_km2": row["area_km2"],
                    "source_authority": row.get("source_authority") or "GEE",
                    "method": row.get("method") or "NDWI",
                },
            )
            written += 1
        db.commit()
    return written
