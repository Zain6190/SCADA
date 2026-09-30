"""Backfill historic river discharge for sparse assets from GloFAS.

GloFAS (Copernicus CEMS, ERA5-forced LISFLOOD reanalysis, 1979-present,
daily) is the only openly licensed discharge history for the barrage assets
whose gauges only started reporting in mid-2026. Rows are written with
data_origin='REANALYSIS' and source_authority='GLOFAS' — a labelled model
product that never masquerades as an observation — source_priority 5 keeps
it below every gauge source (IRSA=1, FFD=2, Kaggle=3) in v_best, and the
feature policy weights it below REAL during training.

Credentials: a free account at https://cds.climate.copernicus.eu (or the
CEMS EWDS portal), then Profile -> API token, accepted dataset terms, and
either export EWDS_API_URL/EWDS_API_TOKEN or write ~/.cdsapirc:

    url: https://ewds.climate.copernicus.eu/api
    key: <your-personal-access-token>

After the first ingest, retrain the sparse assets — they were fit on REAL
rows only, and their feature history grows by years.

Usage:
    python -m scripts.backfill_glofas [--start 2022-01-01] [--asset 3] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import time
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("aquavision.backfill_glofas")

DATASET = "cems-glofas-historical"
DEFAULT_EWDS_URL = "https://ewds.climate.copernicus.eu/api"
CUSECS_PER_M3S = 35.31466726
AREA_NORTH_WEST_SOUTH_EAST = [38.0, 60.0, 23.0, 77.0]
SOURCE_AUTHORITY = "GLOFAS"
SOURCE_PRIORITY = 5
MISSING_FLOOR = -100.0
WINDOW_CELLS = 3
LAT_NAMES = {"latitude", "lat"}
LON_NAMES = {"longitude", "lon"}


def build_request(year: int, start: dt.date, end: dt.date) -> Dict:
    """EWDS selection for one year of daily discharge, month-trimmed.

    Day-level edges of the window are trimmed later (rows outside
    [start, end] are dropped before insert), because year/month/day is a
    cross-product selection that cannot express per-month day bounds.
    """
    months = [
        f"{m:02d}" for m in range(1, 13)
        if not (year == start.year and m < start.month)
        and not (year == end.year and m > end.month)
    ]
    return {
        "system_version": ["version_4_0"],
        "hydrological_model": ["lisflood"],
        "product_type": ["consolidated"],
        "timespan": ["time_mean"],
        "variable": ["average_river_discharge_in_the_last_24_hours"],
        "year": [str(year)],
        "month": months,
        "day": [f"{d:02d}" for d in range(1, 32)],
        "area": list(AREA_NORTH_WEST_SOUTH_EAST),
        "data_format": "netcdf",
        "download_format": "zip",
    }


def _make_client():
    url = os.environ.get("EWDS_API_URL")
    key = os.environ.get("EWDS_API_TOKEN")
    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError("cdsapi is not installed — pip install cdsapi") from exc
    if url and key:
        return cdsapi.Client(url=url, key=key)
    if Path.home().joinpath(".cdsapirc").exists():
        return cdsapi.Client()
    raise RuntimeError(
        "No EWDS credentials. Create a free account at "
        "https://cds.climate.copernicus.eu, accept the GloFAS dataset terms, "
        "then set EWDS_API_URL + EWDS_API_TOKEN or write ~/.cdsapirc "
        f"(url: {DEFAULT_EWDS_URL}, key: <token>)."
    )


def download_year(client, year: int, request: Dict, cache_dir: Path) -> Path:
    """Download one year and return the path to a NetCDF file (zip-aware)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"glofas_{year}.nc"
    if target.exists() and target.stat().st_size > 0:
        return target
    archive = cache_dir / f"glofas_{year}.zip"
    logger.info("Requesting GloFAS %s from EWDS (queued downloads are normal)...", year)
    client.retrieve(DATASET, request).download(str(archive))
    if not archive.exists():
        raise RuntimeError(f"EWDS download produced no file for {year}")
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith((".nc", ".nc4"))]
            if not members:
                raise RuntimeError(f"No NetCDF member in {archive}: {zf.namelist()[:5]}")
            zf.extract(members[0], cache_dir)
            extracted = cache_dir / Path(members[0]).name
            extracted.replace(target)
        archive.unlink(missing_ok=True)
    else:
        archive.replace(target)
    return target


def _find_discharge_var(nc) -> str:
    for name, var in nc.variables.items():
        if var.ndim < 3:
            continue
        attrs = " ".join(
            str(getattr(var, a, "")).lower() for a in ("long_name", "standard_name")
        )
        if name.lower() in {"dis24", "dis"} or "discharge" in attrs:
            return name
    raise ValueError(f"No discharge variable in {list(nc.variables)}")


def _axis_index(var, candidates: Sequence[str]) -> int:
    for i, dim in enumerate(var.dimensions):
        if dim.lower() in candidates:
            return i
    raise ValueError(f"None of {sorted(candidates)} in dims {var.dimensions}")


def extract_series(
    path: Path,
    lat: float,
    lon: float,
    window: int = WINDOW_CELLS,
) -> List[Tuple[dt.date, float]]:
    """Daily discharge series (m3/s) from the wettest GloFAS cell near a point.

    GloFAS carries flow only on river-channel cells, so the geographically
    nearest cell can be a dry pixel while a real channel runs a few cells
    away. The channel cell is the wettest cell (highest mean flow over the
    file) within `window` cells of the nearest cell — about 15 km at the
    native 0.05 deg grid; window=0 keeps pure nearest-cell behaviour. All
    cells dry falls back to the nearest one.
    """
    import netCDF4
    import numpy as np

    series: List[Tuple[dt.date, float]] = []
    with netCDF4.Dataset(str(path)) as nc:
        vname = _find_discharge_var(nc)
        var = nc.variables[vname]
        time_axis = _axis_index(var, ("time", "valid_time"))
        lat_axis = _axis_index(var, LAT_NAMES)
        lon_axis = _axis_index(var, LON_NAMES)

        lat_var = nc.variables[var.dimensions[lat_axis]]
        lon_var = nc.variables[var.dimensions[lon_axis]]
        lats = np.atleast_1d(np.ma.filled(lat_var[:], np.nan))
        lons = np.atleast_1d(np.ma.filled(lon_var[:], np.nan))
        li = int(np.nanargmin(np.abs(lats - lat)))
        lo = int(np.nanargmin(np.abs(lons - lon)))

        lat0, lat1 = max(0, li - window), min(len(lats), li + window + 1)
        lon0, lon1 = max(0, lo - window), min(len(lons), lo + window + 1)

        block_sel = [slice(None)] * var.ndim
        block_sel[lat_axis] = slice(lat0, lat1)
        block_sel[lon_axis] = slice(lon0, lon1)
        block = np.ma.filled(var[tuple(block_sel)], np.nan).astype("float64")
        block[(block <= MISSING_FLOOR) | (block <= 0)] = np.nan
        counts = np.sum(~np.isnan(block), axis=time_axis)
        totals = np.nansum(block, axis=time_axis)
        means = np.divide(
            totals, counts, out=np.full(totals.shape, np.nan), where=counts > 0
        )
        red_lat = lat_axis - 1 if time_axis < lat_axis else lat_axis
        red_lon = lon_axis - 1 if time_axis < lon_axis else lon_axis
        if np.all(np.isnan(means)):
            ci, cj = li - lat0, lo - lon0
        else:
            flat = int(np.nanargmax(means))
            pos = np.unravel_index(flat, means.shape)
            ci = int(pos[red_lat]) if means.ndim > red_lat else 0
            cj = int(pos[red_lon]) if means.ndim > red_lon else 0
        chosen_lat, chosen_lon = lat0 + ci, lon0 + cj

        tvar = nc.variables[var.dimensions[time_axis]]
        times = netCDF4.num2date(
            tvar[:],
            getattr(tvar, "units", "hours since 1900-01-01 00:00:00"),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )

        selector = [slice(None)] * var.ndim
        selector[lat_axis] = chosen_lat
        selector[lon_axis] = chosen_lon
        values = np.ma.filled(var[tuple(selector)], np.nan)
        values = np.atleast_1d(values)

        for i, t in enumerate(times):
            if i >= len(values):
                break
            v = float(values[i])
            if np.isnan(v) or v <= MISSING_FLOOR or v <= 0:
                continue
            when = t.date() if isinstance(t, dt.datetime) else t
            series.append((when, v))
    return series


def rows_for_asset(
    asset_id: int,
    series: Sequence[Tuple[dt.date, float]],
    source_id: int,
) -> List[Dict]:
    """Map (date, m3/s) to water_observations rows with honest provenance."""
    rows = []
    for day, m3s in series:
        rows.append(
            {
                "asset_id": asset_id,
                "source_id": source_id,
                "observed_at": dt.datetime(day.year, day.month, day.day,
                                           tzinfo=dt.timezone.utc),
                "discharge_cusecs": round(m3s * CUSECS_PER_M3S, 2),
                "unit": "cusecs",
                "data_status": "GLOFAS_REANALYSIS",
                "data_origin": "REANALYSIS",
                "source_authority": SOURCE_AUTHORITY,
                "source_priority": SOURCE_PRIORITY,
                "notes": "GloFAS v4 consolidated reanalysis (LISFLOOD/ERA5); nearest river channel cell within ~15 km",
            }
        )
    return rows


def ensure_source(db) -> int:
    """Return the water_sources id for GLOFAS, creating it once."""
    row = db.execute(
        text("SELECT id FROM aquavision.water_sources WHERE authority = :a LIMIT 1"),
        {"a": SOURCE_AUTHORITY},
    ).first()
    if row:
        return int(row[0])
    inserted = db.execute(
        text(
            """
            INSERT INTO aquavision.water_sources
                (authority, source_url, source_type, update_frequency, description)
            VALUES (:a, :u, 'REANALYSIS', 'DAILY',
                    'Copernicus CEMS GloFAS river discharge reanalysis (ERA5/LISFLOOD)')
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        ),
        {"a": SOURCE_AUTHORITY, "u": "https://ewds.climate.copernicus.eu"},
    ).first()
    if inserted:
        db.commit()
        return int(inserted[0])
    row = db.execute(
        text("SELECT id FROM aquavision.water_sources WHERE authority = :a LIMIT 1"),
        {"a": SOURCE_AUTHORITY},
    ).first()
    db.commit()
    return int(row[0])


UPSERT_CHUNK = 500


def _sql_literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def upsert_rows(db, rows: List[Dict]) -> int:
    """Idempotent bulk insert of reanalysis rows; returns rows written.

    Row-at-a-time inserts cost one network round trip each — thousands of
    trips over a high-latency link stretch a transaction across minutes and
    invite mid-flight stalls, so rows go in as chunked multi-row VALUES.
    """
    if not rows:
        return 0
    cols = (
        "asset_id", "source_id", "observed_at", "discharge_cusecs", "unit",
        "data_status", "data_origin", "source_authority", "source_priority",
        "notes",
    )
    head = (
        "INSERT INTO aquavision.water_observations ("
        + ", ".join(cols)
        + ") VALUES "
    )
    tail = (
        " ON CONFLICT (asset_id, observed_at, source_id) DO UPDATE SET"
        " discharge_cusecs = EXCLUDED.discharge_cusecs,"
        " notes = EXCLUDED.notes"
    )
    for i in range(0, len(rows), UPSERT_CHUNK):
        chunk = rows[i:i + UPSERT_CHUNK]
        values = ",\n".join(
            "(" + ", ".join(_sql_literal(r[c]) for c in cols) + ")"
            for r in chunk
        )
        db.execute(text(head + values + tail))
    db.commit()
    return len(rows)


def _with_session(fn):
    """Run fn(db) on a fresh session; retry when serverless Postgres reaps it.

    Neon suspends idle compute (~65s) and drops stale SSL links, so a phase
    that follows a long EWDS download must not reuse a pooled connection.
    """
    last: Optional[Exception] = None
    for delay in (0, 5, 30, 70):
        if delay:
            time.sleep(delay)
        from infrastructure.db.engine import SessionLocal

        db = SessionLocal()
        try:
            return fn(db)
        except OperationalError as exc:
            last = exc
            logger.warning("DB phase failed (attempt will retry): %s", exc)
        finally:
            db.close()
    raise last  # pragma: no cover


def backfill_glofas(
    start: Optional[dt.date] = None,
    asset_id: Optional[int] = None,
    dry_run: bool = False,
    cache_dir: Optional[Path] = None,
    db=None,
) -> dict:
    """Fetch GloFAS history and write labelled REANALYSIS rows per asset.

    No session is held across a download: EWDS queues can take minutes and
    Neon reaps idle connections, so every DB phase opens a fresh session
    (with a short retry in case the serverless compute is asleep).
    """
    start = start or dt.date(2022, 1, 1)
    end = dt.date.today() - dt.timedelta(days=7)
    cache_dir = cache_dir or Path("/tmp/glofas")

    if end < start:
        return {"inserted": 0, "reason": "empty_window"}

    def _load_assets(s):
        return s.execute(
            text(
                """
                SELECT id, canonical_name, latitude, longitude
                FROM aquavision.water_assets
                WHERE is_active = true
                  AND latitude IS NOT NULL AND longitude IS NOT NULL
                  AND (:aid IS NULL OR id = :aid)
                ORDER BY id
                """
            ),
            {"aid": asset_id},
        ).mappings().all()

    if db is not None:
        assets = _load_assets(db)
    else:
        assets = _with_session(_load_assets)
    if not assets:
        return {"inserted": 0, "reason": "no_assets"}

    client = _make_client()
    if dry_run:
        source_id = -1
    elif db is not None:
        source_id = ensure_source(db)
    else:
        source_id = _with_session(ensure_source)

    result = {"inserted": 0, "assets": len(assets), "files": 0,
              "window": [str(start), str(end)], "dry_run": dry_run}
    per_asset: Dict[int, int] = {}

    for year in range(start.year, end.year + 1):
        request = build_request(year, start, end)
        nc_path = download_year(client, year, request, cache_dir)
        result["files"] += 1
        year_rows: List[Dict] = []
        for a in assets:
            series = extract_series(nc_path, float(a["latitude"]),
                                    float(a["longitude"]))
            series = [(d, v) for d, v in series if start <= d <= end]
            rows = rows_for_asset(a["id"], series, source_id)
            per_asset[a["id"]] = per_asset.get(a["id"], 0) + len(rows)
            year_rows.extend(rows)
        if dry_run:
            continue
        if db is not None:
            upsert_rows(db, year_rows)
        else:
            _with_session(lambda s, rs=year_rows: upsert_rows(s, rs))
        result["inserted"] += len(year_rows)

    result["per_asset"] = per_asset
    logger.info("GloFAS backfill complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--asset", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(backfill_glofas(
        start=dt.date.fromisoformat(args.start),
        asset_id=args.asset,
        dry_run=args.dry_run,
    ))
