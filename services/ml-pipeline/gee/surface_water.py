"""
gee/surface_water.py
AquaVision - Surface Water Detection using Sentinel-2 NDWI/MNDWI.

Computes weekly surface water area per region using:
  - NDWI  = (Green - NIR) / (Green + NIR)  → water detection
  - MNDWI = (Green - SWIR) / (Green + SWIR) → better urban separation

Water threshold: NDWI > 0.3

Data flow:
  GEE Sentinel-2 → NDWI/MNDWI per pixel → water mask →
  water area (km²) per region → CSV export

Requires:
  - Google Earth Engine authentication
  - Region polygons in shared.regions (PostGIS)
"""
from __future__ import annotations

import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path

import ee
import psycopg2

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT = os.getenv("GEE_PROJECT", "ibcp-scada-504513")
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
_PSYCOPG2_DSN = DB_URL.replace("postgresql+psycopg2://", "postgresql://")

# Water detection threshold
NDWI_THRESHOLD = 0.3

# Cloud cover limit (percent)
MAX_CLOUD_PCT = 60

# Output directory
RAW_DIR = Path(__file__).resolve().parent.parent / "Data" / "raw"

# Pakistan bounding box for fill images
PAKISTAN_BBOX = [[60, 37], [80, 37], [80, 23], [60, 23], [60, 37]]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def load_regions() -> list[dict]:
    """Read region polygons from PostGIS as GeoJSON features."""
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
    print(f"[surface_water] Loaded {len(rows)} regions from PostGIS", flush=True)
    return rows


# ---------------------------------------------------------------------------
# GEE helpers
# ---------------------------------------------------------------------------
def week_ranges(start: str, end: str) -> list[tuple[str, str]]:
    """List of (week_start, week_end) ISO date pairs, weekly intervals."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    # Align to Monday
    s = s - timedelta(days=s.weekday())
    out = []
    while s <= e:
        week_end = s + timedelta(days=7)
        out.append((s.isoformat(), week_end.isoformat()))
        s = week_end
    return out


def _get_s2_collection(start: str, end: str) -> ee.ImageCollection:
    """Get cloud-filtered Sentinel-2 collection for a date range."""
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
    )


def compute_surface_water_for_week(
    regions_fc: ee.FeatureCollection,
    week_start: str,
    week_end: str,
) -> dict[int, dict]:
    """Compute NDWI, MNDWI, and water area for all regions in a week.

    Returns: {region_id: {ndwi_mean, mndwi_mean, water_area_km2, cloud_pct}}
    """
    s2 = _get_s2_collection(week_start, week_end).filterBounds(regions_fc)

    # Single map pass carrying both indices as bands: two separate
    # median() composites double the sort cost and were the dominant
    # source of "Computation timed out" on heavy weeks.
    def _add_indices(img: ee.Image) -> ee.Image:
        return img.addBands(
            [
                img.normalizedDifference(["B3", "B8"]).rename("ndwi"),
                img.normalizedDifference(["B3", "B11"]).rename("mndwi"),
            ]
        )

    indexed = s2.map(_add_indices).select(["ndwi", "mndwi"])
    composite = ee.Image(
        ee.Algorithms.If(
            indexed.size().gt(0),
            indexed.median(),
            ee.Image.constant([0.0, 0.0]).rename(["ndwi", "mndwi"]),
        )
    )
    ndwi_img = composite.select("ndwi")
    mndwi_img = composite.select("mndwi")

    # --- Water mask: NDWI > threshold ---
    water_mask = ndwi_img.gt(NDWI_THRESHOLD).rename("water")

    # --- Water area: pixel count × pixel area ---
    water_area = water_mask.multiply(ee.Image.pixelArea()).rename("water_area_m2")

    # --- Cloud percentage (using QA60 band: bits 10-11 = clouds) ---
    def add_cloud_flag(img):
        qa = img.select("QA60")
        cloud_bit = 1 << 10
        cirrus_bit = 1 << 11
        cloud = qa.bitwiseAnd(cloud_bit).eq(0).And(
            qa.bitwiseAnd(cirrus_bit).eq(0)
        ).Not().rename("cloud")
        return img.addBands(cloud)

    cloud_collection = s2.map(add_cloud_flag)
    cloud_pct_img = ee.Image(
        ee.Algorithms.If(
            cloud_collection.size().gt(0),
            cloud_collection.select("cloud").mean().multiply(100),
            ee.Image.constant(0.0),
        )
    ).rename("cloud_pct")

    # --- Reduce regions ---
    # Water area must be a SUM over pixels (mean of mask*pixelArea is a
    # per-pixel quantity, not a total - the old mean reducer silently
    # produced ~0 km2 everywhere). tileScale stays small: 16 shards so
    # finely that scheduling overhead alone timed out (169s OK at
    # tileScale=4 vs 300s at 16). Scale 30 on all 21 regions also busts
    # the budget, so start at 60m and escalate to 100m on retry.
    image = ee.Image.cat([ndwi_img, mndwi_img, water_area, cloud_pct_img])
    image = image.clipToCollection(regions_fc)
    reducer = ee.Reducer.mean().combine(
        reducer2=ee.Reducer.sum(), sharedInputs=True
    )

    last_error: Exception | None = None
    stats = None
    for attempt_scale, attempt_tiles in ((60, 4), (100, 4)):
        try:
            stats = (
                image.reduceRegions(
                    collection=regions_fc,
                    reducer=reducer,
                    scale=attempt_scale,
                    tileScale=attempt_tiles,
                ).getInfo()
            )
            break
        except Exception as exc:
            last_error = exc
            print(
                f"[surface_water] scale {attempt_scale} failed for "
                f"{week_start}: {exc}",
                flush=True,
            )
    if stats is None:
        raise last_error if last_error else RuntimeError("reduceRegions failed")

    features = stats["features"]

    def _pick_mean(props: dict, band: str):
        for key in (f"{band}_mean", band):
            if props.get(key) is not None:
                return props.get(key)
        return None

    def _pick_sum(props: dict, band: str):
        return props.get(f"{band}_sum")

    results = {}
    for i, f in enumerate(features):
        rid = int(f["id"])
        props = f.get("properties", {})
        if i == 0:
            print(f"[surface_water] reduce props: {sorted(props)}", flush=True)
        results[rid] = {
            "ndwi_mean": _pick_mean(props, "ndwi"),
            "mndwi_mean": _pick_mean(props, "mndwi"),
            "water_area_km2": (_pick_sum(props, "water_area_m2") or 0) / 1e6,
            "cloud_pct": _pick_mean(props, "cloud_pct"),
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Run surface water detection and export to CSV."""
    key_path = Path(__file__).resolve().parent / "service-account.json"
    ee.Initialize(
        ee.ServiceAccountCredentials(None, key_data=key_path.read_text()),
        project=PROJECT,
    )
    print(f"[surface_water] Authenticated with service account for project {PROJECT}", flush=True)

    # Default: last 4 weeks
    if not end_date:
        end_date = date.today().isoformat()
    if not start_date:
        start = date.today() - timedelta(weeks=4)
        start_date = start.isoformat()

    regions = load_regions()
    regions_fc = ee.FeatureCollection(
        {"type": "FeatureCollection", "features": regions}
    )

    weeks = week_ranges(start_date, end_date)
    print(f"[surface_water] {len(weeks)} weeks ({start_date} -> {end_date})", flush=True)

    all_rows = []
    for i, (ws, we) in enumerate(weeks):
        print(f"[surface_water] week {i+1}/{len(weeks)}: {ws} -> {we}", flush=True)
        try:
            week_results = compute_surface_water_for_week(regions_fc, ws, we)
            for rid, data in week_results.items():
                all_rows.append(
                    {
                        "region_id": rid,
                        "week_start_date": ws,
                        **data,
                    }
                )
        except Exception as e:
            print(f"[surface_water] WARNING: week {ws} failed: {e}", flush=True)
            continue

    # Write CSV, merging with existing rows so a partial-window run cannot
    # wipe earlier weeks (fetched window replaces, older weeks survive).
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "surface_water.csv"
    fieldnames = [
        "region_id",
        "week_start_date",
        "ndwi_mean",
        "mndwi_mean",
        "water_area_km2",
        "cloud_pct",
    ]
    existing: list[dict] = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))
    fetched_keys = {
        (str(r["region_id"]), str(r["week_start_date"])) for r in all_rows
    }
    kept = [
        r
        for r in existing
        if (str(r.get("region_id")), str(r.get("week_start_date"))) not in fetched_keys
    ]
    merged = kept + all_rows
    merged.sort(key=lambda r: (str(r["region_id"]), str(r["week_start_date"])))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)

    print(
        f"[surface_water] Wrote {len(merged)} rows -> {path} "
        f"({len(all_rows)} fetched, {len(kept)} kept)",
        flush=True,
    )
    return merged


if __name__ == "__main__":
    import sys

    s = sys.argv[1] if len(sys.argv) > 1 else None
    e = sys.argv[2] if len(sys.argv) > 2 else None
    main(s, e)
