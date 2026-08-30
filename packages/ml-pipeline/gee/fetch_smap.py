"""
gee/fetch_smap.py
AquaVision - Fetch soil moisture from Open-Meteo ERA5 hourly archive and merge
into region_features.csv.

Uses Open-Meteo Historical Weather API (free, no key required).
Hourly soil moisture aggregated to monthly mean.

Usage:
    python -m gee.fetch_smap   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import csv
import os
import time
from datetime import date
from pathlib import Path

import psycopg2
import requests

DB_URL = os.getenv("DATABASE_URL", "")
_PSYCOPG2_DSN = DB_URL.replace("postgresql+psycopg2://", "postgresql://")
START_DATE = os.getenv("GEE_START_DATE", "2021-01-01")
END_DATE = os.getenv("GEE_END_DATE", "2026-07-31")

RAW_DIR = Path(__file__).resolve().parent.parent / "Data" / "raw"
RAW_CSV = RAW_DIR / "region_features.csv"

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def load_regions() -> list[dict]:
    conn = psycopg2.connect(_PSYCOPG2_DSN)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat "
        "FROM shared.regions ORDER BY id"
    )
    regions = [{"id": r[0], "name": r[1], "lon": r[2], "lat": r[3]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    print(f"[fetch_smap] Loaded {len(regions)} regions")
    return regions


def fetch_soil_moisture(lat: float, lon: float, start: str, end: str) -> dict[str, dict]:
    """Fetch hourly soil moisture from Open-Meteo, aggregate to monthly mean."""
    resp = requests.get(
        OPEN_METEO_ARCHIVE,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "hourly": "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm",
            "timezone": "auto",
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    hourly = data.get("hourly", {})
    dates = hourly.get("time", [])
    sm_0_7 = hourly.get("soil_moisture_0_to_7cm", [])
    sm_7_28 = hourly.get("soil_moisture_7_to_28cm", [])

    monthly: dict[str, dict[str, list[float]]] = {}
    for i, dt_str in enumerate(dates):
        month_key = dt_str[:7]  # "2021-01"
        if month_key not in monthly:
            monthly[month_key] = {"sm_surface": [], "sm_rootzone": []}
        if sm_0_7[i] is not None:
            monthly[month_key]["sm_surface"].append(sm_0_7[i])
        if sm_7_28[i] is not None:
            monthly[month_key]["sm_rootzone"].append(sm_7_28[i])

    result = {}
    for mk, vals in monthly.items():
        result[mk] = {
            "sm_surface": round(sum(vals["sm_surface"]) / len(vals["sm_surface"]), 6) if vals["sm_surface"] else 0.0,
            "sm_rootzone": round(sum(vals["sm_rootzone"]) / len(vals["sm_rootzone"]), 6) if vals["sm_rootzone"] else 0.0,
        }
    return result


def year_chunks(start: str, end: str) -> list[tuple[str, str]]:
    """Split date range into year-long chunks for API stability."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    chunks = []
    while s <= e:
        chunk_end = min(date(s.year, 12, 31), e)
        chunks.append((s.isoformat(), chunk_end.isoformat()))
        s = date(s.year + 1, 1, 1)
    return chunks


def main() -> None:
    regions = load_regions()
    all_sm: dict[tuple[int, str], dict[str, float]] = {}
    chunks = year_chunks(START_DATE, END_DATE)

    for reg in regions:
        print(f"[fetch_smap] Fetching {reg['name']} ({reg['lat']:.2f}, {reg['lon']:.2f}) ...")
        combined: dict[str, dict] = {}
        for cs, ce in chunks:
            sm = fetch_soil_moisture(reg["lat"], reg["lon"], cs, ce)
            combined.update(sm)
            time.sleep(0.3)
        for month_key, vals in combined.items():
            all_sm[(reg["id"], month_key)] = vals
        print(f"[fetch_smap]   -> {len(combined)} months")

    # Merge into existing CSV
    rows = []
    with open(RAW_CSV, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames) + ["sm_rootzone", "sm_surface"]
        for row in reader:
            key = (int(row["region_id"]), row["month"][:7])
            sm = all_sm.get(key, {"sm_rootzone": 0.0, "sm_surface": 0.0})
            row["sm_rootzone"] = sm["sm_rootzone"]
            row["sm_surface"] = sm["sm_surface"]
            rows.append(row)

    with open(RAW_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[fetch_smap] Updated {len(rows)} rows -> {RAW_CSV}")


if __name__ == "__main__":
    main()
