# infrastructure/ingestion/ffd_bulk_ingest.py
# Bulk ingest FFD bulletin HTML files from archive directory into water_observations.
# Uses the new HTML parser (pmd_html_parser) instead of the old text parser.
#
# Usage:
#   python -m infrastructure.ingestion.ffd_bulk_ingest --archive-dir <path> [--dry-run]
#   python -m infrastructure.ingestion.ffd_bulk_ingest --archive-dir raw_archive/ffl
#
# Archive naming: FFD_DD-MM-YYYY.html (e.g., FFD_18-08-2026.html)
# The date is extracted from the filename.
#
# Data flow:
#   HTML files → pmd_html_parser.parse_ffd_html() → water_observations (source=FFD/PMD)
#
# This script:
#   1. Scans archive directory for FFD HTML files
#   2. Parses each file using data-ffd-* attributes
#   3. Stores observations in water_observations (normalized table)
#   4. Archives raw HTML in raw_source_records for re-parseability
#   5. Handles deduplication (idempotent)
import hashlib
import io
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAsset, WaterObservation, WaterSource, RawSourceRecord
from infrastructure.ingestion.pmd_html_parser import parse_ffd_html

logger = logging.getLogger(__name__)

# Source priority for FFD observations
FFD_PRIORITY = 2


def _get_or_create_ffd_source(db) -> WaterSource:
    """Get or create the FFD/PMD source record."""
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == "FFD/PMD")
    ).scalar_one_or_none()
    if not source:
        source = WaterSource(
            authority="FFD/PMD",
            source_url="https://ffd.pmd.gov.pk",
            source_type="HTML_BULLETIN",
            update_frequency="DAILY",
            description="Pakistan Meteorological Department - Flood Forecasting Division",
        )
        db.add(source)
        db.flush()
        return source
    return source


def _get_asset_id(db, canonical_name: str) -> Optional[int]:
    """Get asset ID by canonical name."""
    asset = db.execute(
        select(WaterAsset).where(WaterAsset.canonical_name == canonical_name)
    ).scalar_one_or_none()
    return asset.id if asset else None


def _extract_date_from_filename(filename: str) -> Optional[date]:
    """Extract date from FFD filename like FFD_18-08-2026.html or FFD-18-08-2026.html."""
    match = re.search(r'(\d{2})-(\d{2})-(\d{4})', filename)
    if match:
        day, month, year = match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            pass
    return None


def ingest_ffd_html_file(html_path: Path, target_date: date = None, dry_run: bool = False) -> dict:
    """Ingest a single FFD HTML file into the database.
    
    Returns summary dict with counts.
    """
    # Extract date from filename if not provided
    if target_date is None:
        target_date = _extract_date_from_filename(html_path.name)
    if target_date is None:
        logger.warning(f"Cannot extract date from filename: {html_path.name}")
        return {"error": f"Cannot extract date from {html_path.name}", "parsed": 0, "stored": 0, "skipped": 0}

    # Read and parse HTML
    try:
        html = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html = html_path.read_text(encoding="latin-1")

    content_hash = hashlib.sha256(html.encode()).hexdigest()
    observations = parse_ffd_html(html, target_date)

    if not observations:
        logger.warning(f"No observations parsed from {html_path.name}")
        return {"date": str(target_date), "file": html_path.name, "parsed": 0, "stored": 0, "skipped": 0}

    if dry_run:
        logger.info(f"[DRY RUN] Would ingest {len(observations)} observations from {html_path.name}")
        return {"date": str(target_date), "file": html_path.name, "parsed": len(observations), "stored": 0, "skipped": 0, "dry_run": True}

    with SessionLocal() as db:
        source = _get_or_create_ffd_source(db)

        # Check for duplicate (same hash)
        existing_raw = db.execute(
            select(RawSourceRecord).where(
                RawSourceRecord.source_id == source.id,
                RawSourceRecord.source_date == target_date,
                RawSourceRecord.content_hash == content_hash,
            )
        ).scalar_one_or_none()

        if existing_raw:
            logger.info(f"Duplicate FFD bulletin detected (hash={content_hash[:16]}...), skipping {html_path.name}")
            db.commit()
            return {
                "date": str(target_date),
                "file": html_path.name,
                "parsed": len(observations),
                "stored": 0,
                "skipped": len(observations),
                "duplicate": True,
            }

        # Archive raw HTML
        raw_record = RawSourceRecord(
            source_id=source.id,
            retrieved_at=datetime.now(timezone.utc),
            source_date=target_date,
            file_name=html_path.name,
            content_hash=content_hash,
            raw_content=html.encode("utf-8"),
            parser_version="pmd_html_parser_v2.0",
            record_count=len(observations),
        )
        db.add(raw_record)
        db.flush()

        stored = 0
        skipped = 0

        for obs in observations:
            asset_id = _get_asset_id(db, obs.canonical_name)
            if asset_id is None:
                logger.debug(f"Station '{obs.canonical_name}' not matched to asset, skipping")
                skipped += 1
                continue

            # Check for existing observation (idempotent)
            existing = db.execute(
                select(WaterObservation).where(
                    WaterObservation.asset_id == asset_id,
                    WaterObservation.observed_at == target_date,
                    WaterObservation.source_id == source.id,
                )
            ).scalar_one_or_none()

            if existing:
                skipped += 1
                continue

            # Convert headroom_current (thousands of cusecs) to discharge_cusecs
            discharge_cusecs = obs.headroom_current * 1000 if obs.headroom_current else None

            # Store observation
            water_obs = WaterObservation(
                asset_id=asset_id,
                source_id=source.id,
                observed_at=target_date,
                discharge_cusecs=discharge_cusecs,
                data_status="FORECAST_FFD",
                data_origin="REAL",
                quality_status="VALID",
                quality_flag="FFD_BULLETIN",
                raw_record_id=raw_record.id,
                source_authority="FFD/PMD",
                source_publication_time=datetime.combine(target_date, datetime.min.time()),
                source_parser_version="pmd_html_parser_v2.0",
                source_content_hash=content_hash,
                source_priority=FFD_PRIORITY,
                notes=f"FFD headroom={obs.headroom_current}K, design={obs.headroom_design}K, status={obs.flood_status}",
            )
            db.add(water_obs)
            stored += 1
            logger.info(f"Stored: {obs.canonical_name} = {discharge_cusecs} cusecs, status={obs.flood_status}")

        db.commit()

    return {
        "date": str(target_date),
        "file": html_path.name,
        "parsed": len(observations),
        "stored": stored,
        "skipped": skipped,
    }


def bulk_ingest_ffd_archive(archive_dir: Path, dry_run: bool = False) -> dict:
    """Bulk ingest all FFD HTML files from archive directory.
    
    Scans for files matching FFD_DD-MM-YYYY.html pattern.
    Returns summary with per-file results.
    """
    if not archive_dir.exists():
        return {"error": f"Archive directory not found: {archive_dir}", "files": []}

    # Find all FFD HTML files
    html_files = sorted(archive_dir.glob("FFD*.html"))
    if not html_files:
        return {"error": f"No FFD HTML files found in {archive_dir}", "files": []}

    logger.info(f"Found {len(html_files)} FFD HTML files in {archive_dir}")

    results = []
    total_stored = 0
    total_skipped = 0
    errors = 0

    for html_path in html_files:
        try:
            result = ingest_ffd_html_file(html_path, dry_run=dry_run)
            results.append(result)
            total_stored += result.get("stored", 0)
            total_skipped += result.get("skipped", 0)
            if "error" in result:
                errors += 1
        except Exception as e:
            logger.error(f"Failed to ingest {html_path.name}: {e}")
            results.append({"file": html_path.name, "error": str(e)})
            errors += 1

    summary = {
        "archive_dir": str(archive_dir),
        "total_files": len(html_files),
        "processed": len(results),
        "total_stored": total_stored,
        "total_skipped": total_skipped,
        "errors": errors,
        "files": results,
    }

    if dry_run:
        summary["dry_run"] = True

    logger.info(
        f"Bulk ingestion complete: {total_stored} stored, {total_skipped} skipped, {errors} errors"
    )
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bulk ingest FFD bulletin HTML files")
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path(__file__).parent / "raw_archive" / "ffl",
        help="Directory containing FFD HTML files",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    result = bulk_ingest_ffd_archive(args.archive_dir, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print(f"FFD Bulk Ingestion Summary")
    print("=" * 60)
    print(f"Archive dir: {result.get('archive_dir', 'N/A')}")
    print(f"Total files: {result.get('total_files', 0)}")
    print(f"Processed:   {result.get('processed', 0)}")
    print(f"Stored:      {result.get('total_stored', 0)}")
    print(f"Skipped:     {result.get('total_skipped', 0)}")
    print(f"Errors:      {result.get('errors', 0)}")
    if result.get("dry_run"):
        print("  *** DRY RUN - no data written ***")
    print()

    for f in result.get("files", []):
        status = "OK" if f.get("stored", 0) > 0 else "SKIP" if f.get("duplicate") else "ERR" if "error" in f else "EMPTY"
        print(f"  {f.get('date', '?'):12s} {f.get('file', '?'):30s} {status:5s} stored={f.get('stored', 0):3d} skipped={f.get('skipped', 0):3d}")
