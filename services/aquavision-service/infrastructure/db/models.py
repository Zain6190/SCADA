# infrastructure/db/models.py
# ORM entities mapped to the shared PostGIS database.
#   aquavision.*  -> owned by this service (read/write)
#   shared.*      -> read-only (regions, assets); other schemas untouched.
from datetime import date, datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.db.engine import Base


# ---------------------------------------------------------------------------
# SHARED SCHEMA (READ-ONLY - never written by AquaVision)
# ---------------------------------------------------------------------------
class User(Base):
    """Minimal mapping so FKs to shared.users resolve (read-only)."""

    __tablename__ = "users"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # province | district | tehsil
    parent_region_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shared.regions.id")
    )
    geom = mapped_column(Geometry("MultiPolygon", 4326), nullable=False)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    region_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    geom = mapped_column(Geometry("Polygon", 4326), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# AQUAVISION SCHEMA (OWNED BY THIS SERVICE)
# ---------------------------------------------------------------------------
class WaterIndicator(Base):
    __tablename__ = "water_indicators_weekly"
    __table_args__ = (
        UniqueConstraint("region_id", "week_start_date", name="uq_water_indicator_region_week"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    week_number: Mapped[Optional[int]] = mapped_column(Integer)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    surface_water_area_km2: Mapped[Optional[float]] = mapped_column(Numeric)
    surface_water_change_pct: Mapped[Optional[float]] = mapped_column(Numeric)
    rainfall_mm_30day: Mapped[Optional[float]] = mapped_column(Numeric)
    rainfall_anomaly: Mapped[Optional[float]] = mapped_column(Numeric)
    et_mm_8day: Mapped[Optional[float]] = mapped_column(Numeric)
    et_anomaly: Mapped[Optional[float]] = mapped_column(Numeric)
    wai_score: Mapped[Optional[float]] = mapped_column(Numeric)
    severity: Mapped[Optional[str]] = mapped_column(Text)
    data_source_version: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    region: Mapped[Region] = relationship("Region")


class WaterPrediction(Base):
    __tablename__ = "water_predictions_weekly"
    __table_args__ = (
        UniqueConstraint(
            "region_id", "target_week_start_date", "model_version",
            name="uq_water_prediction_region_week_version",
        ),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    target_week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_type: Mapped[Optional[str]] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_severity: Mapped[Optional[str]] = mapped_column(Text)
    predicted_wai_score: Mapped[Optional[float]] = mapped_column(Numeric)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    region: Mapped[Region] = relationship("Region")


class WaterAlert(Base):
    __tablename__ = "water_alerts"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    wai_score: Mapped[Optional[float]] = mapped_column(Numeric)
    rainfall_anomaly: Mapped[Optional[float]] = mapped_column(Numeric)
    et_anomaly: Mapped[Optional[float]] = mapped_column(Numeric)
    surface_water_change_pct: Mapped[Optional[float]] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, default="New")
    assigned_to_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    region: Mapped[Region] = relationship("Region")


class WaterReport(Base):
    __tablename__ = "water_reports"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    region_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.regions.id"))
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    generated_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(Text, default="Success")


class WaterThreshold(Base):
    __tablename__ = "water_thresholds"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    threshold_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
