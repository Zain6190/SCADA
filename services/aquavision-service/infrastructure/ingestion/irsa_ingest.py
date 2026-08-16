# infrastructure/ingestion/irsa_ingest.py
# Ingest IRSA PDFs into the database: parse → archive raw → validate → normalize → store.
import hashlib
import logging
from datetime import date, datetime
from typing import List

from sqlalchemy import select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import (
    WaterSource, WaterAsset, RawSourceRecord, WaterObservation,
    WaterObservationQuarantine, DataQualityLog,
)
from infrastructure.ingestion.irsa_scraper import IRSAObservation, parse_irsa_pdf
from infrastructure.ingestion.validators import validate_observation, build_quarantine_record

logger = logging.getLogger("aquavision.ingest")


def _get_or_create_source(db) -> WaterSource:
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == "IRSA")
    ).scalar_one_or_none()
    if not source:
        source = WaterSource(
            authority="IRSA",
            source_url="http://pakirsa.gov.pk",
            source_type="PDF_DAILY_REPORT",
            update_frequency="DAILY",
            description="Indus River System Authority - Daily Water Situation Report",
        )
        db.add(source)
        db.flush()
    return source


def _get_asset_id(db, canonical_name: str) -> int:
    asset = db.execute(
        select(WaterAsset).where(WaterAsset.canonical_name == canonical_name)
    ).scalar_one_or_none()
    if not asset:
        raise ValueError(f"Asset '{canonical_name}' not found in water_assets. Seed first.")
    return asset.id


def _obs_to_row(obs: IRSAObservation, asset_id: int, source_id: int, raw_record_id: int) -> dict:
    """Map parser observation fields to DB row fields.
    
    For barrages/river stations, map upstream_discharge -> outflow, downstream_discharge -> discharge.
    This ensures barrage data is available for ML training.
    """
    outflow = obs.outflow_cusecs
    discharge = obs.discharge_cusecs
    inflow = obs.inflow_cusecs

    # Barrages: upstream_discharge is the inflow to the barrage
    if inflow is None and obs.upstream_discharge_cusecs is not None:
        inflow = obs.upstream_discharge_cusecs
    if outflow is None and obs.downstream_discharge_cusecs is not None:
        outflow = obs.downstream_discharge_cusecs

    return {
        "asset_id": asset_id,
        "source_id": source_id,
        "observed_at": datetime.combine(obs.observed_at, datetime.min.time()),
        "water_level_ft": obs.water_level_ft,
        "inflow_cusecs": inflow,
        "outflow_cusecs": outflow,
        "discharge_cusecs": discharge,
        "upstream_discharge_cusecs": obs.upstream_discharge_cusecs,
        "downstream_discharge_cusecs": obs.downstream_discharge_cusecs,
        "unit": "cusecs" if inflow or obs.upstream_discharge_cusecs else "feet",
        "data_status": "OBSERVED_OFFICIAL",
        "quality_status": "VALID",
        "quality_flag": "OFFICIAL_DAILY_REPORT",
        "raw_record_id": raw_record_id,
    }


def ingest_irsa_pdf(pdf_path: str, target_date: date, source_url: str = "") -> dict:
    """Full pipeline: parse PDF → archive raw → store observations.

    Returns summary dict with counts.
    """
    # 1. Parse PDF
    observations = parse_irsa_pdf(pdf_path, target_date, source_url)
    if not observations:
        return {"error": "No observations parsed", "count": 0}

    # 2. Read raw bytes
    with open(pdf_path, "rb") as f:
        raw_bytes = f.read()
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    with SessionLocal() as db:
        # 3. Get/create source
        source = _get_or_create_source(db)

        # 4. Archive raw record (idempotent: skip if same hash+date already exists)
        existing_raw = db.execute(
            select(RawSourceRecord).where(
                RawSourceRecord.source_id == source.id,
                RawSourceRecord.source_date == target_date,
                RawSourceRecord.content_hash == content_hash,
            )
        ).scalar_one_or_none()

        if existing_raw:
            raw_record_id = existing_raw.id
        else:
            raw_record = RawSourceRecord(
                source_id=source.id,
                retrieved_at=datetime.utcnow(),
                source_date=target_date,
                file_name=f"IRSA_Daily_{target_date.strftime('%d-%m-%Y')}.pdf",
                content_hash=content_hash,
                raw_content=raw_bytes,
                parser_version="irsa_scraper_v1.0",
                record_count=len(observations),
            )
            db.add(raw_record)
            db.flush()
            raw_record_id = raw_record.id

        # 5. Store observations with validation
        stored = 0
        skipped = 0
        invalid = 0
        for obs in observations:
            # Skip aggregate/release observations (not per-asset)
            if obs.asset_type in ("aggregate", "provincial_release"):
                continue

            try:
                asset_id = _get_asset_id(db, obs.asset_name)
            except ValueError:
                skipped += 1
                continue

            # Check for existing observation (idempotent)
            existing = db.execute(
                select(WaterObservation).where(
                    WaterObservation.asset_id == asset_id,
                    WaterObservation.observed_at == datetime.combine(obs.observed_at, datetime.min.time()),
                    WaterObservation.source_id == source.id,
                )
            ).scalar_one_or_none()

            if existing:
                skipped += 1
                continue

            row = _obs_to_row(obs, asset_id, source.id, raw_record_id)
            
            # Validate observation
            validation = validate_observation(row, asset_id, source_date=target_date)
            
            if validation.quality_status == "INVALID":
                # Quarantine invalid observations
                quarantine = build_quarantine_record(
                    row, asset_id, validation,
                    source_record_id=raw_record_id,
                    parser_version="irsa_scraper_v1.0",
                )
                if quarantine:
                    db.add(WaterObservationQuarantine(
                        asset_id=quarantine.asset_id,
                        source_record_id=quarantine.source_record_id,
                        raw_payload=quarantine.raw_payload,
                        parsed_values=quarantine.parsed_values,
                        failure_reason=quarantine.failure_reason,
                        field_name=quarantine.field_name,
                        raw_value=quarantine.raw_value,
                        parser_version=quarantine.parser_version,
                        data_status=quarantine.data_status,
                    ))
                    # Log to data quality
                    for v in validation.violations:
                        db.add(DataQualityLog(
                            asset_id=asset_id,
                            check_type=v.get("check", "UNKNOWN"),
                            field_name=v.get("field", "unknown"),
                            raw_value=float(v.get("raw_value", 0)) if v.get("raw_value") else None,
                            quality_status="INVALID",
                            details=v.get("detail", ""),
                            source_record_id=raw_record_id,
                        ))
                invalid += 1
                logger.warning(f"Asset {asset_id}: INVALID observation quarantined - {validation.violations}")
            else:
                # Store valid/suspect observations
                row["quality_status"] = validation.quality_status
                db.add(WaterObservation(**row))
                stored += 1

        db.commit()

    # 6. Run threshold engine (outside main transaction)
    try:
        from infrastructure.thresholds.engine import evaluate_all_assets
        threshold_result = evaluate_all_assets()
        logger.info(f"Threshold evaluation: {threshold_result['new_alerts']} new alerts from {threshold_result['assets_checked']} assets")
    except Exception as e:
        logger.warning(f"Threshold engine failed (non-fatal): {e}")
        threshold_result = {"assets_checked": 0, "new_alerts": 0, "alerts": {}}

    return {
        "date": str(target_date),
        "parsed": len(observations),
        "stored": stored,
        "skipped": skipped,
        "invalid": invalid,
        "raw_record_id": raw_record_id,
        "thresholds": threshold_result,
    }


if __name__ == "__main__":
    import sys
    test_files = [
        ("Data15-08-2026.pdf", date(2026, 8, 15)),
        ("Data14-08-2026.pdf", date(2026, 8, 14)),
        ("Data09-08-2026.pdf", date(2026, 8, 9)),
    ]
    for path, dt in test_files:
        print(f"\n--- Ingesting {path} ({dt}) ---")
        result = ingest_irsa_pdf(path, dt, f"http://pakirsa.gov.pk/Doc/{path}")
        print(f"  Result: {result}")
