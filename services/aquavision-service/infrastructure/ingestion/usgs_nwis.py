# infrastructure/ingestion/usgs_nwis.py
# Pull 15-minute river telemetry from the USGS NWIS Instantaneous Values service
# and feed it through the AquaVision sensor ingest API.
#
# Why: AquaVision's river stations (assets 9-11) are fed by FFD/PMD bulletins,
# which publish daily. USGS publishes genuine RTU telemetry every 15 minutes,
# which is what the sub-daily threshold rules were written for.
#
# Units already match AquaVision - no conversion is required:
#   parameterCd 00060 = discharge, cubic feet per second (= cusecs)
#   parameterCd 00065 = gauge height, feet
#
# PROVENANCE: the measurement is real, but its attribution to a Pakistani asset
# is not. Rows are written with data_origin=SYNTHETIC and a sensor_id naming the
# USGS site, so nobody has to guess whether a row describes the Chenab or the
# Mississippi.
#
# Docs: https://nwis.waterservices.usgs.gov/docs/instantaneous-values/
#
# Usage:
#   python -m infrastructure.ingestion.usgs_nwis --days 7
#   python -m infrastructure.ingestion.usgs_nwis --days 3 --dry-run

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterator, List, Optional

import requests

logger = logging.getLogger("aquavision.usgs_nwis")

# ─── Constants ─────────────────────────────────────────────────────────────

# Base URL lives here rather than inline: USGS is migrating to modernised APIs
# (https://api.waterdata.usgs.gov/docs/ogcapi/migration/), so the eventual
# cutover should be a one-line change.
NWIS_BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"
DEFAULT_API = "http://127.0.0.1:8100/water/sensors/ingest"
SOURCE_AUTHORITY = "USGS_NWIS"
BATCH_SIZE = 100

PARAM_DISCHARGE = "00060"  # ft3/s -> discharge_cusecs
PARAM_GAUGE_HT = "00065"   # ft    -> water_level_ft

PARAM_TO_FIELD = {
    PARAM_DISCHARGE: "discharge_cusecs",
    PARAM_GAUGE_HT: "water_level_ft",
}

# USGS reports "no data" as -999999
NODATA = -999998.0


@dataclass(frozen=True)
class SiteMapping:
    """Maps a USGS gauge site onto an AquaVision river station.

    Only river stations are mapped. A USGS site IS a gauge station, so the
    signal semantics line up; mapping one onto a reservoir would not.
    """
    site_no: str
    asset_id: int
    asset_name: str
    note: str


# Sites verified to serve BOTH 00060 and 00065 on the instantaneous-values
# service. Each is matched to its target by flow regime, not by size alone.
SITE_MAPPINGS: List[SiteMapping] = [
    SiteMapping("06610000", 9, "Kabul @ Nowshera",
                "Missouri R. at Omaha NE - snowmelt-fed tributary proxy"),
    SiteMapping("05331000", 10, "Chenab @ Marala",
                "Mississippi R. at St. Paul MN - upper-reach snowmelt proxy"),
    SiteMapping("03612600", 11, "Panjnad",
                "Ohio R. at Olmsted IL - pre-confluence discharge proxy"),
]


# ─── Fetch ─────────────────────────────────────────────────────────────────

def fetch_site(site_no: str, start: date, end: date, timeout: int = 60,
               retries: int = 4) -> dict:
    """Fetch instantaneous values for one site as parsed JSON.

    NWIS returns 503 under load, and a long export issues enough requests to
    trigger it. Without a retry a whole site can come back empty while every
    individual window merely logs a warning - so back off and retry rather than
    losing the site.
    """
    import time

    params = {
        "format": "json",
        "sites": site_no,
        "parameterCd": f"{PARAM_DISCHARGE},{PARAM_GAUGE_HT}",
        "startDT": start.isoformat(),
        "endDT": end.isoformat(),
    }

    last_exc = None
    for attempt in range(retries):
        try:
            resp = requests.get(NWIS_BASE_URL, params=params, timeout=timeout)
            # 503/429 are transient; 4xx (other than 429) are not worth retrying.
            if resp.status_code in (429, 503):
                raise requests.HTTPError(f"{resp.status_code} transient", response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status not in (429, 503) and status < 500:
                raise
            if attempt < retries - 1:
                backoff = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning("  %s %s..%s: %s - retrying in %ds (%d/%d)",
                               site_no, start, end, status or type(exc).__name__,
                               backoff, attempt + 1, retries - 1)
                time.sleep(backoff)

    raise last_exc


def parse_timeseries(payload: dict) -> Dict[str, Dict[str, float]]:
    """Flatten the NWIS response into {iso_timestamp: {field: value}}.

    NWIS nests as value.timeSeries[] -> values[] -> value[], with the parameter
    code in variable.variableCode[0].value.
    """
    merged: Dict[str, Dict[str, float]] = {}

    for series in payload.get("value", {}).get("timeSeries", []):
        codes = series.get("variable", {}).get("variableCode", [])
        if not codes:
            continue
        param = codes[0].get("value")
        field = PARAM_TO_FIELD.get(param)
        if field is None:
            continue

        for block in series.get("values", []):
            for point in block.get("value", []):
                raw = point.get("value")
                ts = point.get("dateTime")
                if raw is None or ts is None:
                    continue
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    continue
                if val <= NODATA:  # USGS no-data sentinel
                    continue
                merged.setdefault(ts, {})[field] = val

    return merged


# ─── Reading construction ──────────────────────────────────────────────────

def build_readings(mapping: SiteMapping, series: Dict[str, Dict[str, float]]) -> List[dict]:
    """Convert one site's flattened series into sensor-API reading payloads."""
    readings: List[dict] = []

    for ts in sorted(series):
        fields = series[ts]
        if not fields:
            continue

        reading = {
            "asset_id": mapping.asset_id,
            "timestamp": ts,
            "sensor_id": f"USGS_{mapping.site_no}",
            "quality": "VALID",
            # Real measurement, but not of this asset. Never REAL here.
            "origin": "SYNTHETIC",
            "status": "SIMULATED",
        }

        level = fields.get("water_level_ft")
        if level is not None and 0 <= level <= 2000:  # matches ingest range check
            reading["water_level_ft"] = round(level, 2)

        discharge = fields.get("discharge_cusecs")
        if discharge is not None and discharge >= 0:
            reading["discharge_cusecs"] = round(discharge, 1)

        # Endpoint rejects readings with no measurement at all
        if "water_level_ft" in reading or "discharge_cusecs" in reading:
            readings.append(reading)

    return readings


def batches(readings: List[dict], size: int = BATCH_SIZE) -> Iterator[List[dict]]:
    for i in range(0, len(readings), size):
        yield readings[i:i + size]


# ─── Historical export (real RTU training corpus) ──────────────────────────
#
# The ingest path above proxies USGS telemetry onto Pakistani assets so the
# alert chain can be exercised at realistic cadence. That is a DEMO path, and
# those rows are marked SYNTHETIC because the asset attribution is invented.
#
# This path is different: it exports the telemetry as-is, under its own site
# identity, for TRAINING. Nothing is proxied and nothing is written to the
# database, so real measurements never masquerade as Pakistani observations.
# Every row carries the site it actually came from.
#
# Depth verified live: all three mapped sites serve 15-minute level+discharge
# back to at least 2013 - roughly 10 years of genuine RTU output per site.

CHUNK_DAYS = 180  # ~8x faster per point than year-long requests

CSV_COLUMNS = [
    "observed_at",
    "site_no",
    "site_name",
    "water_level_ft",
    "discharge_cusecs",
    "source_authority",
    "data_origin",
]


def _chunk_ranges(start: date, end: date, days: int = CHUNK_DAYS) -> Iterator[tuple]:
    """Split a date range into request-sized windows."""
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=days), end)
        yield cursor, stop
        cursor = stop


def fetch_range(site_no: str, start: date, end: date) -> Dict[str, Dict[str, float]]:
    """Fetch a multi-year span for one site, chunked. Returns merged series."""
    merged: Dict[str, Dict[str, float]] = {}
    windows = list(_chunk_ranges(start, end))

    for i, (win_start, win_end) in enumerate(windows, start=1):
        try:
            series = parse_timeseries(fetch_site(site_no, win_start, win_end, timeout=180))
        except Exception as exc:  # noqa: BLE001 - one dead window must not lose the rest
            logger.error("  %s %s..%s failed: %s", site_no, win_start, win_end, exc)
            continue
        merged.update(series)
        logger.info("  %s [%d/%d] %s..%s -> %d points (total %d)",
                    site_no, i, len(windows), win_start, win_end, len(series), len(merged))

    return merged


def export_csv(
    out_path: str,
    start: date,
    end: date,
    sites: Optional[List[str]] = None,
    require_both: bool = False,
) -> dict:
    """Export real USGS telemetry to CSV for model training.

    No proxying, no database, no synthetic values - each row is a real reading
    labelled with the site that produced it.

    Args:
        require_both: keep only timestamps carrying BOTH level and discharge.
    """
    import csv as _csv

    site_list = sites or [m.site_no for m in SITE_MAPPINGS]
    names = {m.site_no: m.note for m in SITE_MAPPINGS}
    summary = {"rows": 0, "sites": {}, "path": out_path}

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for site_no in site_list:
            logger.info("Exporting %s (%s .. %s)", site_no, start, end)
            series = fetch_range(site_no, start, end)
            written = 0

            for ts in sorted(series):
                fields = series[ts]
                level = fields.get("water_level_ft")
                discharge = fields.get("discharge_cusecs")

                if require_both and (level is None or discharge is None):
                    continue
                if level is None and discharge is None:
                    continue

                writer.writerow({
                    "observed_at": ts,
                    "site_no": site_no,
                    "site_name": names.get(site_no, ""),
                    "water_level_ft": level if level is not None else "",
                    "discharge_cusecs": discharge if discharge is not None else "",
                    "source_authority": SOURCE_AUTHORITY,
                    # This IS a real measurement - it is simply not Pakistani.
                    # The site columns carry that distinction; nothing is proxied here.
                    "data_origin": "REAL",
                })
                written += 1

            summary["sites"][site_no] = written
            summary["rows"] += written
            if written == 0:
                # A silently empty site is how a "successful" export ends up
                # missing a third of its corpus.
                logger.error("  %s -> 0 ROWS - site exported NOTHING", site_no)
            else:
                logger.info("  %s -> %d rows", site_no, written)

    empty = [s for s, n in summary["sites"].items() if n == 0]
    if empty:
        logger.error("EXPORT INCOMPLETE: %d of %d sites returned no data: %s",
                     len(empty), len(summary["sites"]), ", ".join(empty))
    summary["empty_sites"] = empty

    logger.info("Wrote %d rows -> %s", summary["rows"], out_path)
    return summary


# ─── POST loop ─────────────────────────────────────────────────────────────

def post_readings(
    readings: List[dict],
    api_url: str = DEFAULT_API,
    api_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """POST readings in batches. Returns an aggregate summary."""
    total = {"accepted": 0, "rejected": 0, "batches": 0, "failed_batches": 0}
    batch_list = list(batches(readings))

    if dry_run:
        logger.info("DRY RUN - %d readings in %d batches, nothing sent",
                    len(readings), len(batch_list))
        if batch_list:
            logger.info("First reading: %s", batch_list[0][0])
        total["batches"] = len(batch_list)
        return total

    for i, batch in enumerate(batch_list, start=1):
        payload = {"source": SOURCE_AUTHORITY, "readings": batch}
        if api_key:
            payload["api_key"] = api_key
        try:
            resp = requests.post(api_url, json=payload, timeout=60)
            resp.raise_for_status()
            body = resp.json()
            total["accepted"] += body.get("accepted", 0)
            total["rejected"] += body.get("rejected", 0)
            total["batches"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad batch must not kill the run
            total["failed_batches"] += 1
            logger.error("batch %d/%d failed: %s", i, len(batch_list), exc)

    return total


def ingest_usgs(
    days: int = 7,
    api_url: str = DEFAULT_API,
    api_key: Optional[str] = None,
    dry_run: bool = False,
    mappings: Optional[List[SiteMapping]] = None,
) -> dict:
    """Full pipeline: fetch each mapped site -> parse -> POST."""
    mappings = mappings or SITE_MAPPINGS
    end = date.today()
    start = end - timedelta(days=days)

    summary = {"accepted": 0, "rejected": 0, "batches": 0,
               "failed_batches": 0, "sites": [], "readings_built": 0}

    for mapping in mappings:
        logger.info("Fetching USGS %s -> asset %d (%s)",
                    mapping.site_no, mapping.asset_id, mapping.asset_name)
        try:
            payload = fetch_site(mapping.site_no, start, end)
        except Exception as exc:  # noqa: BLE001 - a dead site must not stop the rest
            logger.error("USGS fetch failed for %s: %s", mapping.site_no, exc)
            summary["sites"].append(
                {"site": mapping.site_no, "asset_id": mapping.asset_id, "error": str(exc)}
            )
            continue

        series = parse_timeseries(payload)
        readings = build_readings(mapping, series)
        logger.info("  %d timestamps -> %d readings", len(series), len(readings))
        summary["readings_built"] += len(readings)

        result = post_readings(readings, api_url=api_url, api_key=api_key, dry_run=dry_run)
        for key in ("accepted", "rejected", "batches", "failed_batches"):
            summary[key] += result[key]
        summary["sites"].append({
            "site": mapping.site_no,
            "asset_id": mapping.asset_id,
            "asset_name": mapping.asset_name,
            "readings": len(readings),
            "accepted": result["accepted"],
            "rejected": result["rejected"],
        })

    logger.info("USGS ingestion complete: accepted=%d rejected=%d failed_batches=%d",
                summary["accepted"], summary["rejected"], summary["failed_batches"])
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="USGS NWIS real river telemetry: ingest as proxy, or export for training"
    )
    parser.add_argument("--days", type=int, default=7,
                        help="Ingest mode: days of history (default 7)")
    parser.add_argument("--api", default=DEFAULT_API, help=f"Ingest URL (default {DEFAULT_API})")
    parser.add_argument("--api-key", default=None, help="API key, if configured")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and report without sending")

    parser.add_argument("--export-csv", metavar="PATH", default=None,
                        help="Export mode: write real telemetry to CSV for training "
                             "(no proxying, no database writes)")
    parser.add_argument("--start", default=None, help="Export start date, YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Export end date, YYYY-MM-DD (default today)")
    parser.add_argument("--sites", default=None,
                        help="Comma-separated USGS site numbers (default: all mapped sites)")
    parser.add_argument("--require-both", action="store_true",
                        help="Keep only timestamps carrying BOTH level and discharge")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.export_csv:
        if not args.start:
            raise SystemExit("--start is required with --export-csv")
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else date.today()
        site_list = [s.strip() for s in args.sites.split(",")] if args.sites else None
        export_csv(args.export_csv, start, end,
                   sites=site_list, require_both=args.require_both)
    else:
        ingest_usgs(days=args.days, api_url=args.api,
                    api_key=args.api_key, dry_run=args.dry_run)
