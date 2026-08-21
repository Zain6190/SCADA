# presentation/http/routers/sensors.py
# Real-time sensor data ingestion API.
# Accepts POST requests from external sensors/devices pushing live readings.
# Supports batch ingestion, validation, and automatic threshold evaluation.
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.engine import get_session
from infrastructure.db.models import WaterAsset, WaterObservation, WaterSource

logger = logging.getLogger("aquavision.api.sensors")

router = APIRouter(prefix="/sensors", tags=["Sensors"])


# ─── Request/Response Models ───────────────────────────────────────────────

class SensorReading(BaseModel):
    """Single sensor reading from an external device."""
    asset_id: int = Field(..., description="Water asset ID (1-11)")
    timestamp: datetime = Field(..., description="Reading timestamp (ISO 8601)")
    water_level_ft: Optional[float] = Field(None, description="Water level in feet")
    inflow_cusecs: Optional[float] = Field(None, description="Inflow in cusecs")
    outflow_cusecs: Optional[float] = Field(None, description="Outflow in cusecs")
    discharge_cusecs: Optional[float] = Field(None, description="Discharge in cusecs")
    sensor_id: Optional[str] = Field(None, description="Unique sensor identifier")
    quality: Optional[str] = Field("VALID", description="Data quality: VALID, SUSPECT, STALE")


class SensorBatchRequest(BaseModel):
    """Batch of sensor readings."""
    readings: List[SensorReading] = Field(..., min_length=1, max_length=100)
    source: str = Field("SENSOR_API", description="Source identifier")
    api_key: Optional[str] = Field(None, description="API key for authentication")


class SensorBatchResponse(BaseModel):
    """Response for batch sensor ingestion."""
    accepted: int
    rejected: int
    errors: List[str]
    observation_ids: List[int]


# ─── API Key Validation ────────────────────────────────────────────────────

# In production, store API keys in the database.
# For now, use a simple env-var based key.
VALID_API_KEYS = set()  # Populated from settings at startup


def _validate_api_key(api_key: Optional[str]) -> bool:
    """Validate API key. Returns True if valid or if no keys are configured."""
    if not VALID_API_KEYS:
        return True  # No keys configured = open access (dev mode)
    if not api_key:
        return False
    return api_key in VALID_API_KEYS


# ─── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=SensorBatchResponse)
async def ingest_sensor_readings(
    request: SensorBatchRequest,
    db: Session = Depends(get_session),
):
    """Ingest a batch of real-time sensor readings.
    
    Validates each reading, stores in water_observations, and triggers
    threshold evaluation for any critical values.
    
    Authentication: API key in request body (or open access if no keys configured).
    """
    # Validate API key
    if not _validate_api_key(request.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get or create SENSOR_API source
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == "SENSOR_API")
    ).scalar_one_or_none()
    if not source:
        source = WaterSource(
            authority="SENSOR_API",
            source_url="sensor-api",
            source_type="REALTIME_SENSOR",
            update_frequency="REALTIME",
            description="Real-time sensor data ingestion API",
        )
        db.add(source)
        db.flush()

    accepted = 0
    rejected = 0
    errors = []
    observation_ids = []

    for reading in request.readings:
        try:
            # Validate asset exists
            asset = db.get(WaterAsset, reading.asset_id)
            if not asset:
                errors.append(f"Asset {reading.asset_id} not found")
                rejected += 1
                continue

            # Validate at least one measurement
            has_measurement = any([
                reading.water_level_ft is not None,
                reading.inflow_cusecs is not None,
                reading.outflow_cusecs is not None,
                reading.discharge_cusecs is not None,
            ])
            if not has_measurement:
                errors.append(f"No measurement values for asset {reading.asset_id}")
                rejected += 1
                continue

            # Validate ranges
            if reading.water_level_ft is not None and (reading.water_level_ft < 0 or reading.water_level_ft > 2000):
                errors.append(f"Invalid water_level_ft {reading.water_level_ft} for asset {reading.asset_id}")
                rejected += 1
                continue

            if reading.inflow_cusecs is not None and reading.inflow_cusecs < 0:
                errors.append(f"Negative inflow_cusecs for asset {reading.asset_id}")
                rejected += 1
                continue

            # Check for duplicate (same asset + timestamp + source)
            existing = db.execute(
                select(WaterObservation).where(
                    WaterObservation.asset_id == reading.asset_id,
                    WaterObservation.observed_at == reading.timestamp,
                    WaterObservation.source_id == source.id,
                )
            ).scalar_one_or_none()

            if existing:
                errors.append(f"Duplicate reading for asset {reading.asset_id} at {reading.timestamp}")
                rejected += 1
                continue

            # Store observation
            obs = WaterObservation(
                asset_id=reading.asset_id,
                source_id=source.id,
                observed_at=reading.timestamp,
                water_level_ft=reading.water_level_ft,
                inflow_cusecs=reading.inflow_cusecs,
                outflow_cusecs=reading.outflow_cusecs,
                discharge_cusecs=reading.discharge_cusecs,
                data_status="OBSERVED_TELEMETRY",
                data_origin="REAL",
                quality_status=reading.quality or "VALID",
                quality_flag=f"SENSOR_{reading.sensor_id}" if reading.sensor_id else "SENSOR_API",
                source_authority="SENSOR_API",
                source_publication_time=datetime.now(timezone.utc),
                source_parser_version="sensor_api_v1.0",
                source_priority=1,
                notes=f"sensor_id={reading.sensor_id}" if reading.sensor_id else None,
            )
            db.add(obs)
            db.flush()
            observation_ids.append(obs.id)
            accepted += 1

        except Exception as e:
            errors.append(f"Error processing asset {reading.asset_id}: {str(e)}")
            rejected += 1

    db.commit()

    # Trigger threshold evaluation if any readings accepted
    if accepted > 0:
        try:
            from infrastructure.thresholds.engine import evaluate_all_assets
            evaluate_all_assets()
        except Exception as e:
            logger.warning(f"Threshold evaluation failed after sensor ingestion: {e}")

    logger.info(f"Sensor ingestion: {accepted} accepted, {rejected} rejected")

    return SensorBatchResponse(
        accepted=accepted,
        rejected=rejected,
        errors=errors,
        observation_ids=observation_ids,
    )


@router.get("/assets")
async def list_sensor_assets(db: Session = Depends(get_session)):
    """List all water assets that can receive sensor data."""
    assets = db.execute(
        select(WaterAsset).where(WaterAsset.is_active == True).order_by(WaterAsset.id)
    ).scalars().all()

    return [
        {
            "id": a.id,
            "canonical_name": a.canonical_name,
            "asset_type": a.asset_type,
            "river": a.river,
            "province": a.province,
            "latitude": float(a.latitude) if a.latitude else None,
            "longitude": float(a.longitude) if a.longitude else None,
        }
        for a in assets
    ]


@router.get("/status")
async def sensor_api_status(db: Session = Depends(get_session)):
    """Get sensor API status and statistics."""
    from sqlalchemy import func

    # Count observations from SENSOR_API source
    source = db.execute(
        select(WaterSource).where(WaterSource.authority == "SENSOR_API")
    ).scalar_one_or_none()

    if not source:
        return {
            "status": "NO_SOURCE",
            "total_readings": 0,
            "latest_reading": None,
        }

    total = db.execute(
        select(func.count(WaterObservation.id)).where(
            WaterObservation.source_id == source.id
        )
    ).scalar()

    latest = db.execute(
        select(WaterObservation.observed_at).where(
            WaterObservation.source_id == source.id
        ).order_by(WaterObservation.observed_at.desc()).limit(1)
    ).scalar_one_or_none()

    return {
        "status": "OPERATIONAL",
        "total_readings": total,
        "latest_reading": str(latest) if latest else None,
    }
