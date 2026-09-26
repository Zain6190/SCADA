"""
gee/gee_fetch.py
AquaVision - Fetch region-level feature time-series from Google Earth Engine.

For each administrative region in shared.regions (SRID 4326 polygons),
pull MONTHLY aggregates from:
  - CHIRPS      precipitation  (mm / month)          "UCSB-CHG/CHIRPS/DAILY"
  - MOD16       evapotranspiration (mm / month)      "MODIS/061/MOD16A2"
  - JRC GSW     surface water extent (%)             "JRC/GSW1_4/MonthlyHistory"
  - Sentinel-2  NDVI (median, cloud-filtered)        "COPERNICUS/S2_HARMONIZED"
  - SMAP L4     soil moisture (vol. fraction)        "NASA/SMAP/SPL4SMGP/008"

The default window is the last 12 weeks. --backfill restores the long training range.

Writes long-format CSV -> Data/raw/region_features.csv
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import ee

PROJECT = os.getenv("GEE_PROJECT", "ibcp-scada-504513")
DB_URL = os.getenv("DATABASE_URL", "")
SERVICE_ACCOUNT_KEY = Path(__file__).resolve().parent / "service-account.json"
# psycopg2 needs the plain postgresql:// DSN, not the SQLAlchemy dialect form.
_PSYCOPG2_DSN = DB_URL.replace("postgresql+psycopg2://", "postgresql://")
BACKFILL_START = os.getenv("GEE_BACKFILL_START", "2021-01-01")
BACKFILL_END = os.getenv("GEE_BACKFILL_END", "2026-07-31")
SOURCE_VERSION = "GEE-CHIRPS/MOD16-JRC"

RESERVOIRS = (
    {"asset_id": 1, "name": "Tarbela", "lon": 72.6837, "lat": 34.0887},
    {"asset_id": 2, "name": "Mangla", "lon": 73.6437, "lat": 33.1387},
)


def recent_window(today: date | None = None, weeks: int = 12) -> tuple[str, str]:
    today = today or date.today()
    start = (today - timedelta(weeks=weeks)).replace(day=1)
    return start.isoformat(), today.isoformat()


def resolve_window(backfill: bool = False, today: date | None = None) -> tuple[str, str]:
    if backfill:
        return BACKFILL_START, BACKFILL_END
    start = os.getenv("GEE_START_DATE")
    end = os.getenv("GEE_END_DATE")
    if start and end:
        return start, end
    return recent_window(today)

RAW_DIR = Path(__file__).resolve().parent.parent / "Data" / "raw"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def load_regions() -> list[dict]:
    """Read region polygons from PostGIS as GeoJSON features (no geopandas)."""
    import json

    import psycopg2

    conn = psycopg2.connect(_PSYCOPG2_DSN)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, type, ST_AsGeoJSON(geom) AS geojson "
        "FROM shared.regions WHERE type = 'district' ORDER BY id"
    )
    rows = []
    for rid, name, rtype, geojson in cur.fetchall():
        rows.append(
            {
                "type": "Feature",
                "id": str(rid),
                "properties": {"region_id": rid, "name": name, "region_type": rtype},
                "geometry": json.loads(geojson),
            }
        )
    cur.close()
    conn.close()
    print(f"[gee_fetch] Loaded {len(rows)} regions from PostGIS")
    return rows


def month_ranges(start: str, end: str) -> list[tuple[str, str]]:
    """List of (month_start, month_end) ISO date pairs between start and end."""
    s = date.fromisoformat(start).replace(day=1)
    e = date.fromisoformat(end)
    out = []
    y, m = s.year, s.month
    while date(y, m, 1) <= e:
        first = date(y, m, 1)
        if m == 12:
            last = date(y + 1, 1, 1)
        else:
            last = date(y, m + 1, 1)
        out.append((first.isoformat(), last.isoformat()))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _precip_ic(month_ranges: list[tuple[str, str]]) -> ee.ImageCollection:
    """CHIRPS monthly precipitation: one image per month = daily sum."""
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
    imgs = [
        chirps.filterDate(s, e).sum().set("month", s)
        for s, e in month_ranges
    ]
    return ee.ImageCollection(imgs)


def _et_ic(month_ranges: list[tuple[str, str]]) -> ee.ImageCollection:
    """MODIS MOD16 8-day ET summed to mm for the month. Scale factor is 0.1."""
    et = ee.ImageCollection("MODIS/061/MOD16A2").select("ET")
    imgs = []
    for s, e in month_ranges:
        coll = et.filterDate(s, e).map(lambda img: img.multiply(0.1).rename("et_mm"))
        img = ee.Image(
            ee.Algorithms.If(
                coll.size().gt(0),
                coll.sum(),
                ee.Image.constant(0.0).rename("et_mm"),
            )
        )
        imgs.append(img.rename("et_mm").set("month", s))
    return ee.ImageCollection(imgs)


def _jrc_ic(month_ranges: list[tuple[str, str]]) -> ee.ImageCollection:
    """JRC Global Surface Water - Monthly History: water class per month."""
    jrc = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory").select("water")
    imgs = []
    for s, e in month_ranges:
        img = ee.Image(
            ee.Algorithms.If(
                jrc.filterDate(s, e).size().gt(0),
                jrc.filterDate(s, e).first(),
                ee.Image.constant(-1.0).rename("water"),
            )
        )
        imgs.append(img.rename("water").set("month", s))
    return ee.ImageCollection(imgs)


def _ndvi_ic(month_ranges: list[tuple[str, str]]) -> ee.ImageCollection:
    """Sentinel-2 NDVI median per month (cloud filtered)."""
    s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filter(
        ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)
    )
    imgs = []
    for s, e in month_ranges:
        coll = s2.filterDate(s, e).map(
            lambda img: img.normalizedDifference(["B8", "B4"]).rename("ndvi")
        )
        ndvi = ee.Image(
            ee.Algorithms.If(
                coll.size().gt(0),
                coll.median(),
                ee.Image.constant(-1.0).rename("ndvi"),
            )
        )
        imgs.append(ndvi.set("month", s))
    return ee.ImageCollection(imgs)


def _smap_ic(month_ranges: list[tuple[str, str]], band: str = "sm_rootzone") -> ee.ImageCollection:
    """SMAP L4 soil moisture: monthly mean of volume fraction (0-0.9).
    Bands: sm_surface (0-5cm), sm_rootzone (0-100cm).
    """
    smap = ee.ImageCollection("NASA/SMAP/SPL4SMGP/008").select(band)
    imgs = []
    for s, e in month_ranges:
        coll = smap.filterDate(s, e)
        img = ee.Image(
            ee.Algorithms.If(
                coll.size().gt(0),
                coll.mean(),
                ee.Image.constant(0.0).rename(band),
            )
        )
        imgs.append(img.set("month", s))
    return ee.ImageCollection(imgs)


def _first_or_fill(
    ic: ee.ImageCollection, s: str, e: str, band: str, fill: float
) -> ee.Image:
    """Return first image in window, or a constant fill image if empty."""
    empty = ee.Image.constant(fill).rename([band]).clip(
        ee.Geometry.Polygon(
            [[60, 37], [80, 37], [80, 23], [60, 23], [60, 37]]
        )
    )
    return ee.Image(
        ee.Algorithms.If(
            ic.filterDate(s, e).size().gt(0), ic.filterDate(s, e).first(), empty
        )
    )


def initialize_ee() -> None:
    if SERVICE_ACCOUNT_KEY.exists():
        credentials = ee.ServiceAccountCredentials(
            None,
            key_data=SERVICE_ACCOUNT_KEY.read_text(),
        )
        ee.Initialize(credentials, project=PROJECT)
        print(f"[gee_fetch] Authenticated with service account for project {PROJECT}")
        return
    ee.Initialize(project=PROJECT)
    print(f"[gee_fetch] Authenticated with Earth Engine user credentials for project {PROJECT}")


def sample_reservoirs(end_date: str) -> list[dict]:
    """NDWI water area inside an 8 km buffer around Tarbela and Mangla."""
    start = (date.fromisoformat(end_date) - timedelta(weeks=12)).isoformat()
    s2 = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filter(
        ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)
    )
    rows = []
    for spec in RESERVOIRS:
        geom = ee.Geometry.Point([spec["lon"], spec["lat"]]).buffer(8000)
        coll = s2.filterDate(start, end_date).filterBounds(geom).map(
            lambda img: img.normalizedDifference(["B3", "B8"]).rename("ndwi").updateMask(
                img.normalizedDifference(["B3", "B8"]).gt(0.3)
            )
        )
        area = ee.Image(
            ee.Algorithms.If(
                coll.size().gt(0),
                coll.median().multiply(ee.Image.pixelArea()).rename("area"),
                ee.Image.constant(0).rename("area"),
            )
        )
        total = area.reduceRegion(ee.Reducer.sum(), geom, 30).get("area")
        km2 = float(total.getInfo() or 0) / 1e6
        rows.append({
            "asset_id": spec["asset_id"],
            "name": spec["name"],
            "observed_on": end_date,
            "area_km2": round(km2, 3),
            "source_authority": "GEE",
            "method": "NDWI",
            "writes_irsa_level": False,
        })
    return rows


def _write_reservoirs(rows: list[dict]) -> None:
    import csv

    path = RAW_DIR / "reservoir_surface.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "asset_id", "name", "observed_on", "area_km2",
            "source_authority", "method", "writes_irsa_level",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[gee_fetch] Wrote {len(rows)} reservoir area rows -> {path}")


def main() -> None:
    import sys

    backfill = "--backfill" in sys.argv
    start_date, end_date = resolve_window(backfill=backfill)
    initialize_ee()
    regions = load_regions()
    regions_fc = ee.FeatureCollection(
        {
            "type": "FeatureCollection",
            "features": regions,
        }
    )
    months = month_ranges(start_date, end_date)
    print(f"[gee_fetch] {len(months)} months ({start_date} -> {end_date}) source {SOURCE_VERSION}")

    datasets = {
        "rainfall_mm": _precip_ic(months),
        "et_mm": _et_ic(months),
        "water_extent": _jrc_ic(months),
        "ndvi": _ndvi_ic(months),
    }

    month_ids = [s for s, _e in months]
    results = []
    CHUNK = 12
    for name, ic in datasets.items():
        print(f"[gee_fetch] reducing {name} ...")
        for chunk_start in range(0, len(month_ids), CHUNK):
            chunk = month_ids[chunk_start : chunk_start + CHUNK]
            month_images = [
                ic.filter(ee.Filter.eq("month", m)).first().rename(m)
                for m in chunk
            ]
            stacked = ee.Image.cat(month_images)
            red = stacked.reduceRegions(
                collection=regions_fc, reducer=ee.Reducer.mean(), scale=1000
            )
            feats = red.getInfo()["features"]
            for f in feats:
                rid = int(f["id"])
                props = f.get("properties", {})
                for m in chunk:
                    val = props.get(m)
                    _set_nested(results, rid, name, m, val)
            print(f"[gee_fetch]   chunk {chunk_start//CHUNK+1}/{(len(month_ids)+CHUNK-1)//CHUNK} done ({len(chunk)} months)")
    print(f"[gee_fetch] {len(results)} region-months accumulated")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    import csv

    path = RAW_DIR / "region_features.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["region_id", "month"] + list(datasets.keys())
        )
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print(f"[gee_fetch] Wrote {len(results)} rows -> {path}")
    try:
        _write_reservoirs(sample_reservoirs(end_date))
    except Exception as exc:
        print(f"[gee_fetch] reservoir area sample skipped: {exc}")


def _set_nested(rows: list, rid: int, feat: str, month: str, value) -> None:
    """Accumulate rows of {region_id, month, rainfall_mm, ...}."""
    for row in rows:
        if row["region_id"] == rid and row["month"] == month:
            row[feat] = value
            return
    rows.append({"region_id": rid, "month": month, feat: value})


if __name__ == "__main__":
    main()
