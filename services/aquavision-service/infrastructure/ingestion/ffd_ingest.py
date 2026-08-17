# infrastructure/ingestion/ffd_ingest.py
# Ingest FFD/PMD flood bulletin data into the database.
# Pipeline: scrape FFD → validate → match to assets → store observations.
# Includes raw HTML archival for re-parseability.

import hashlib
import logging
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict

from sqlalchemy import select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterSource, WaterAsset, WaterFFDObservation, RawSourceRecord
from infrastructure.ingestion.pmd_scraper import PMDScraper, PMDObservation

logger = logging.getLogger("aquavision.ffd_ingest")

FFD_ARCHIVE_DIR = Path(__file__).parent / "raw_archive" / "ffl"


def _get_or_create_source(db) -> WaterSource:
    """Get or create FFD/PMD source."""
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


def _get_asset_id(db, canonical_name: str) -> int:
    """Get asset ID by canonical name."""
    asset = db.execute(
        select(WaterAsset).where(WaterAsset.canonical_name == canonical_name)
    ).scalar_one_or_none()
    if not asset:
        return None
    return asset.id


def ingest_ffd_bulletin(target_date: date = None) -> dict:
    """Full pipeline: scrape FFD → archive raw HTML → validate → match assets → store.
    
    Returns summary dict with counts.
    """
    if target_date is None:
        target_date = date.today()
    
    # 1. Scrape FFD bulletin
    scraper = PMDScraper()
    try:
        html = scraper.fetch_bulletin_page()
        observations = scraper.parse_flood_bulletin(html, target_date)
        fetch_status = "SUCCESS"
    except Exception as e:
        logger.error(f"Failed to scrape FFD: {e}")
        return {"error": str(e), "parsed": 0, "stored": 0, "skipped": 0, "fetch_status": "FAILED"}
    finally:
        scraper.close()
    
    if not observations:
        logger.warning("No observations parsed from FFD bulletin")
        return {"date": str(target_date), "parsed": 0, "stored": 0, "skipped": 0, "fetch_status": fetch_status}
    
    # 2. Archive raw HTML
    content_hash = hashlib.sha256(html.encode()).hexdigest()
    FFD_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = FFD_ARCHIVE_DIR / f"FFD_{target_date.strftime('%d-%m-%Y')}.html"
    archive_path.write_text(html, encoding="utf-8")
    logger.info(f"Archived FFD HTML to {archive_path}")
    
    # 3. Store in database
    with SessionLocal() as db:
        source = _get_or_create_source(db)
        
        # Check for duplicate (same hash + date)
        existing_raw = db.execute(
            select(RawSourceRecord).where(
                RawSourceRecord.source_id == source.id,
                RawSourceRecord.source_date == target_date,
                RawSourceRecord.content_hash == content_hash,
            )
        ).scalar_one_or_none()

        if existing_raw:
            logger.info(f"Duplicate FFD bulletin detected (hash={content_hash[:16]}...), skipping ingestion for {target_date}")
            db.commit()
            return {
                "date": str(target_date),
                "parsed": len(observations),
                "stored": 0,
                "skipped": len(observations),
                "fetch_status": fetch_status,
                "duplicate": True,
            }
        
        # Archive raw record
        raw_record = RawSourceRecord(
            source_id=source.id,
            retrieved_at=datetime.utcnow(),
            source_date=target_date,
            file_name=f"FFD_Bulletin_{target_date.strftime('%d-%m-%Y')}.html",
            content_hash=content_hash,
            raw_content=html.encode("utf-8"),
            parser_version="pmd_scraper_v1.0",
            record_count=len(observations),
        )
        db.add(raw_record)
        db.flush()
        
        stored = 0
        skipped = 0
        
        for obs in observations:
            asset_id = _get_asset_id(db, obs.station_name)
            
            if asset_id is None:
                logger.debug(f"Station '{obs.station_name}' not matched to asset, skipping")
                skipped += 1
                continue
            
            # Check for existing observation (idempotent)
            existing = db.execute(
                select(WaterFFDObservation).where(
                    WaterFFDObservation.asset_id == asset_id,
                    WaterFFDObservation.observed_at == target_date,
                    WaterFFDObservation.source_id == source.id,
                )
            ).scalar_one_or_none()
            
            if existing:
                skipped += 1
                continue
            
            # Basic validation
            if obs.discharge_cusecs is not None and obs.discharge_cusecs < 0:
                logger.warning(f"FFD {obs.station_name}: negative discharge {obs.discharge_cusecs}, setting to None")
                obs.discharge_cusecs = None
            
            # Store observation
            ffd_obs = WaterFFDObservation(
                asset_id=asset_id,
                source_id=source.id,
                station_name=obs.station_name,
                river_name=obs.river,
                observed_at=target_date,
                gauge_level_ft=obs.gauge_level_ft,
                discharge_cusecs=obs.discharge_cusecs,
                flood_status=obs.flood_status,
                forecast_trend=obs.forecast_trend,
                bulletin_url="https://ffd.pmd.gov.pk/bulletin/bulletin",
                content_hash=content_hash,
                data_status="FORECAST_FFD",
            )
            db.add(ffd_obs)
            stored += 1
            logger.info(f"Stored FFD: {obs.station_name} - inflow={obs.discharge_cusecs}, outflow={obs.gauge_level_ft}, status={obs.flood_status}")
        
        db.commit()
    
    # 4. Run threshold engine for FFD status
    try:
        from infrastructure.thresholds.engine import evaluate_all_assets
        threshold_result = evaluate_all_assets()
        logger.info(f"FFD threshold evaluation: {threshold_result.get('new_alerts', 0)} new alerts")
    except Exception as e:
        logger.warning(f"Threshold engine failed (non-fatal): {e}")
    
    return {
        "date": str(target_date),
        "parsed": len(observations),
        "stored": stored,
        "skipped": skipped,
        "fetch_status": fetch_status,
    }


def get_ffd_status_for_asset(asset_id: int, target_date: date = None) -> dict:
    """Get FFD status for a specific asset."""
    if target_date is None:
        target_date = date.today()
    
    with SessionLocal() as db:
        obs = db.execute(
            select(WaterFFDObservation).where(
                WaterFFDObservation.asset_id == asset_id,
                WaterFFDObservation.observed_at == target_date,
            ).order_by(WaterFFDObservation.created_at.desc())
        ).scalar_one_or_none()
        
        if not obs:
            return {"status": "NO_DATA"}
        
        return {
            "status": "OK",
            "station_name": obs.station_name,
            "river_name": obs.river_name,
            "gauge_level_ft": float(obs.gauge_level_ft) if obs.gauge_level_ft else None,
            "discharge_cusecs": float(obs.discharge_cusecs) if obs.discharge_cusecs else None,
            "flood_status": obs.flood_status,
            "forecast_trend": obs.forecast_trend,
            "observed_at": str(obs.observed_at),
        }


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    result = ingest_ffd_bulletin()
    print(f"\nFFD Ingestion result: {result}")
