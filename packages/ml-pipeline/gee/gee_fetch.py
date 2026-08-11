"""
gee/gee_fetch.py
AquaVision - Fetch region-level feature time-series from Google Earth Engine.

For each administrative region in shared.regions (SRID 4326 polygons),
pull MONTHLY aggregates from:
  - CHIRPS      precipitation  (mm / month)          "UCSB-CHG/CHIRPS/DAILY"
  - ERA5-Land   evapotranspiration (mm / month)      "ECMWF/ERA5_LAND/MONTHLY"
  - JRC GSW     surface water extent (%)             "JRC/GSW1_4/MonthlyHistory"
  - Sentinel-2  NDVI (median, cloud-filtered)        "COPERNICUS/S2_HARMONIZED"

Writes long-format CSV -> Data/raw/region_features.csv
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import ee

PROJECT = os.getenv("GEE_PROJECT", "ibcp-scada-504513")
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
# psycopg2 needs the plain postgresql:// DSN, not the SQLAlchemy dialect form.
_PSYCOPG2_DSN = DB_URL.replace("postgresql+psycopg2://", "postgresql://")
START_DATE = os.getenv("GEE_START_DATE", "2021-01-01")
END_DATE = os.getenv("GEE_END_DATE", "2026-07-31")

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
        "FROM shared.regions ORDER BY id"
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
    """ERA5-Land monthly ET: total_evaporation_sum (m) -> mm (absolute)."""
    et = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").select(
        "total_evaporation_sum"
    )
    imgs = []
    for s, e in month_ranges:
        coll = et.filterDate(s, e).map(
            lambda img: img.abs().multiply(1000).rename("et_mm")
        )
        img = ee.Image(
            ee.Algorithms.If(
                coll.size().gt(0),
                coll.first(),
                ee.Image.constant(0.0).rename("et_mm"),
            )
        )
        imgs.append(img.set("month", s))
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


def main() -> None:
    ee.Initialize(project=PROJECT)
    regions = load_regions()
    regions_fc = ee.FeatureCollection(
        {
            "type": "FeatureCollection",
            "features": regions,
        }
    )
    months = month_ranges(START_DATE, END_DATE)
    print(f"[gee_fetch] {len(months)} months ({START_DATE} -> {END_DATE})")

    datasets = {
        "rainfall_mm": _precip_ic(months),
        "et_mm": _et_ic(months),
        "water_extent": _jrc_ic(months),
        "ndvi": _ndvi_ic(months),
    }

    month_ids = [s for s, _e in months]
    results = []
    # Efficient: stack every month as a band, ONE reduceRegions per dataset.
    for name, ic in datasets.items():
        print(f"[gee_fetch] reducing {name} ...")
        # Rename each month's band to its date, then stack -> deterministic names.
        month_images = [
            ic.filter(ee.Filter.eq("month", m)).first().rename(m)
            for m in month_ids
        ]
        stacked = ee.Image.cat(month_images)
        red = stacked.reduceRegions(
            collection=regions_fc, reducer=ee.Reducer.mean(), scale=1000
        )
        feats = red.getInfo()["features"]
        for f in feats:
            rid = int(f["id"])
            props = f.get("properties", {})
            for m in month_ids:
                val = props.get(m)
                _set_nested(results, rid, name, m, val)
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


def _set_nested(rows: list, rid: int, feat: str, month: str, value) -> None:
    """Accumulate rows of {region_id, month, rainfall_mm, ...}."""
    for row in rows:
        if row["region_id"] == rid and row["month"] == month:
            row[feat] = value
            return
    rows.append({"region_id": rid, "month": month, feat: value})


if __name__ == "__main__":
    main()
