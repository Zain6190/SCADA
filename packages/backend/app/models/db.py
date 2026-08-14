# packages/backend/app/models/db.py
# SQLAlchemy ORM models mapped to the PostGIS database (all 5 schemas).
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, CheckConstraint, Date, DateTime, ForeignKey, Integer,
    Index, Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from sqlalchemy.orm import relationship, mapped_column, Mapped

from app.core.database import Base

# ---------------------------------------------------------------------------
# shared schema
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Access lifecycle (Phase 2): PENDING|APPROVED|REJECTED|ACTIVE|SUSPENDED|REVOKED
    access_status: Mapped[str] = mapped_column(Text, default="ACTIVE", server_default="ACTIVE")
    access_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "shared"}

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.roles.id"), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = {"schema": "shared"}

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.permissions.id"), primary_key=True)


class UserRegionScope(Base):
    """Explicit geographic scope for a user. FAIL-CLOSED: a user with no active
    scope is DENIED protected regional data. NATIONAL must be explicit.

    scope_type: NATIONAL | PROVINCE | DISTRICT | ASSET
    - NATIONAL: region_id/asset_id must be NULL (no restrictions).
    - PROVINCE: region_id = a province; grants that province + its districts.
    - DISTRICT: region_id = one district.
    - ASSET:    asset_id = one asset (resolved to its owning region).
    """
    __tablename__ = "user_region_scopes"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('NATIONAL','PROVINCE','DISTRICT','ASSET')",
            name="ck_user_region_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'NATIONAL' AND region_id IS NULL AND asset_id IS NULL) OR "
            "(scope_type IN ('PROVINCE','DISTRICT') AND region_id IS NOT NULL AND asset_id IS NULL) OR "
            "(scope_type = 'ASSET' AND asset_id IS NOT NULL AND region_id IS NULL)",
            name="ck_user_region_scope_target",
        ),
Index(
            "uq_user_region_scope_active",
            "user_id", "scope_type", "region_id", "asset_id",
            unique=True, postgresql_where=text("is_active"),
        ),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.users.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    region_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.regions.id"))
    asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.assets.id"))
    granted_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    parent_region_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.regions.id"))
    geom = mapped_column(Geometry("MultiPolygon", 4326, spatial_index=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = {"schema": "shared"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    region_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.regions.id"))
    geom = mapped_column(Geometry("Polygon", 4326, spatial_index=False), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)


# ---------------------------------------------------------------------------
# aquavision schema
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
    spi_1: Mapped[Optional[float]] = mapped_column(Numeric, comment="SPI-1 month")
    spi_3: Mapped[Optional[float]] = mapped_column(Numeric, comment="SPI-3 month")
    spi_6: Mapped[Optional[float]] = mapped_column(Numeric, comment="SPI-6 month")
    spi_12: Mapped[Optional[float]] = mapped_column(Numeric, comment="SPI-12 month")
    spi_drought_class: Mapped[Optional[str]] = mapped_column(Text, comment="WMO drought classification")
    wai_score: Mapped[Optional[float]] = mapped_column(Numeric)
    severity: Mapped[Optional[str]] = mapped_column(Text)
    data_source_version: Mapped[Optional[str]] = mapped_column(Text)
    # --- #8 / #9 provenance + status (backend-enforced) ---
    data_status: Mapped[Optional[str]] = mapped_column(Text, comment="Actual|Calibrated|Estimate|Missing")
    data_quality: Mapped[Optional[str]] = mapped_column(Text, comment="Good|Ok|Stale|Missing")
    data_provider: Mapped[Optional[str]] = mapped_column(Text, comment="Data origin e.g. GEE-JRC, SATE, Field")
    wai_model_version: Mapped[Optional[str]] = mapped_column(Text, comment="Version of the WAI scoring model")
    source_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), comment="Freshness of underlying observation")
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # --- #15 completeness / data-quality (partial periods never look like zero) ---
    period_start: Mapped[Optional[date]] = mapped_column(Date, comment="Start of the observation period")
    period_end: Mapped[Optional[date]] = mapped_column(Date, comment="End of the observation period")
    is_complete_period: Mapped[Optional[bool]] = mapped_column(Boolean, comment="True when the period fully closed")
    coverage_percent: Mapped[Optional[float]] = mapped_column(Numeric, comment="Share of expected observations present")
    observation_count: Mapped[Optional[int]] = mapped_column(Integer)
    expected_observation_count: Mapped[Optional[int]] = mapped_column(Integer)
    quality_status: Mapped[Optional[str]] = mapped_column(Text, comment="VALID|PARTIAL|STALE|SUSPECT|INVALID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    region: Mapped[Region] = relationship("Region")


class WaterPrediction(Base):
    __tablename__ = "water_predictions_weekly"
    __table_args__ = (
        UniqueConstraint("region_id", "target_week_start_date", "model_version",
                         name="uq_water_prediction_region_week_version"),
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
    # --- #9 prediction versioning metadata ---
    trained_on_week_start: Mapped[Optional[date]] = mapped_column(Date, comment="Cutoff week used to train the model")
    dataset_version: Mapped[Optional[str]] = mapped_column(Text, comment="Version of training dataset")
    feature_importance_hash: Mapped[Optional[str]] = mapped_column(Text)
    # --- #15 forecast-vs-actual validation ---
    lower_bound: Mapped[Optional[float]] = mapped_column(Numeric, comment="Forecast lower bound")
    upper_bound: Mapped[Optional[float]] = mapped_column(Numeric, comment="Forecast upper bound")
    feature_version: Mapped[Optional[str]] = mapped_column(Text, comment="GEE feature snapshot version")
    training_cutoff: Mapped[Optional[date]] = mapped_column(Date, comment="Last date used in training")
    actual_value: Mapped[Optional[float]] = mapped_column(Numeric, comment="Verified outcome for the period")
    error: Mapped[Optional[float]] = mapped_column(Numeric, comment="forecast - actual")
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), comment="When forecast was scored against actuals")
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
    # --- #12 SCADA alarm lifecycle (ISA-18.2 mindset) ---
    acknowledged_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shared.users.id", ondelete="SET NULL"), comment="Who accepted responsibility")
    initial_assessment: Mapped[Optional[str]] = mapped_column(
        Text, comment="Operator's first read on acknowledging")
    estimated_response_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="ETA for the initial operational response")
    investigation_notes: Mapped[Optional[str]] = mapped_column(Text)
    action_taken: Mapped[Optional[str]] = mapped_column(
        Text, comment="Approved operational action performed")
    action_result: Mapped[Optional[str]] = mapped_column(
        Text, comment="Measured outcome of the action")
    action_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evidence_refs: Mapped[Optional[list]] = mapped_column(JSONB, comment="Evidence refs (JSONB list)")
    escalated_to: Mapped[Optional[str]] = mapped_column(
        Text, comment="Supervisor / regional authority / national authority")
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shared.users.id", ondelete="SET NULL"), comment="Who confirmed the response")
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("shared.users.id", ondelete="SET NULL"), comment="Who cleared the alert")
    # --- #15 source attribution (RULE|MODEL|DATA_QUALITY|SYSTEM) ---
    source: Mapped[Optional[str]] = mapped_column(
        Text, comment="Alert origin: RULE|MODEL|DATA_QUALITY|SYSTEM")
    confidence: Mapped[Optional[float]] = mapped_column(
        Numeric, comment="Model/rule confidence 0..1")
    rule_version: Mapped[Optional[str]] = mapped_column(
        Text, comment="Version of the rule/model that raised the alert")

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


class AssetTelemetry(Base):
    """Operational SCADA readings for a water asset (reservoir level, storage
    %, inflow / outflow / discharge in cumecs). Drives the operator console."""

    __tablename__ = "asset_telemetry"
    __table_args__ = (
        Index("ix_asset_telemetry_asset_time", "asset_id", "recorded_at"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.assets.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reservoir_level_m: Mapped[Optional[float]] = mapped_column(Numeric)
    storage_pct: Mapped[Optional[float]] = mapped_column(Numeric)
    inflow_cumecs: Mapped[Optional[float]] = mapped_column(Numeric)
    outflow_cumecs: Mapped[Optional[float]] = mapped_column(Numeric)
    discharge_cumecs: Mapped[Optional[float]] = mapped_column(Numeric)
    data_status: Mapped[Optional[str]] = mapped_column(Text, comment="Actual|Calibrated|Estimate|Missing")
    source: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetOperationalNote(Base):
    """Operator logbook entries attached to a water asset."""

    __tablename__ = "asset_operational_notes"
    __table_args__ = (
        Index("ix_asset_operational_notes_asset", "asset_id"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.assets.id"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# crop schema
# ---------------------------------------------------------------------------
class CropFeature(Base):
    __tablename__ = "crop_features"
    __table_args__ = {"schema": "crop"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    crop_type: Mapped[str] = mapped_column(Text, nullable=False)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    feature_date: Mapped[date] = mapped_column(Date, nullable=False)
    ndvi: Mapped[Optional[float]] = mapped_column(Numeric)
    evi: Mapped[Optional[float]] = mapped_column(Numeric)
    savi: Mapped[Optional[float]] = mapped_column(Numeric)
    rainfall_mm: Mapped[Optional[float]] = mapped_column(Numeric)
    temperature_avg: Mapped[Optional[float]] = mapped_column(Numeric)
    soil_moisture: Mapped[Optional[float]] = mapped_column(Numeric)
    wai_score: Mapped[Optional[float]] = mapped_column(Numeric)
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CropModel(Base):
    __tablename__ = "crop_models"
    __table_args__ = {"schema": "crop"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    crop_type: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CropPrediction(Base):
    __tablename__ = "crop_predictions"
    __table_args__ = {"schema": "crop"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    crop_type: Mapped[str] = mapped_column(Text, nullable=False)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_yield: Mapped[float] = mapped_column(Numeric, nullable=False)
    yield_unit: Mapped[str] = mapped_column(Text, default="tons/ha")
    risk_category: Mapped[Optional[str]] = mapped_column(Text)
    model_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("crop.crop_models.id"))
    confidence: Mapped[Optional[float]] = mapped_column(Numeric)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CropAlert(Base):
    __tablename__ = "crop_alerts"
    __table_args__ = {"schema": "crop"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    crop_type: Mapped[str] = mapped_column(Text, nullable=False)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    risk_category: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="New")
    assigned_to_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)


class CropReport(Base):
    __tablename__ = "crop_reports"
    __table_args__ = {"schema": "crop"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    region_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.regions.id"))
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    generated_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(Text, default="Success")


# ---------------------------------------------------------------------------
# geo schema
# ---------------------------------------------------------------------------
class GeoOverlay(Base):
    __tablename__ = "geo_overlays"
    __table_args__ = {"schema": "geo"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shared.regions.id"), nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    wai_score: Mapped[Optional[float]] = mapped_column(Numeric)
    water_severity: Mapped[Optional[str]] = mapped_column(Text)
    predicted_yield: Mapped[Optional[float]] = mapped_column(Numeric)
    yield_risk: Mapped[Optional[str]] = mapped_column(Text)
    combined_risk_score: Mapped[Optional[float]] = mapped_column(Numeric)
    geom = mapped_column(Geometry("MultiPolygon", 4326, spatial_index=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemStatus(Base):
    __tablename__ = "system_status"
    __table_args__ = {"schema": "geo"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_successful_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# system schema
# ---------------------------------------------------------------------------
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = {"schema": "system"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pipeline_name: Mapped[str] = mapped_column(Text, nullable=False)
    week_start_date: Mapped[Optional[date]] = mapped_column(Date)
    season: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    log_path: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    # --- #15 observability ---
    run_id: Mapped[Optional[str]] = mapped_column(Text, comment="RUN-yyyy-mm-dd-NNN")
    trigger_type: Mapped[Optional[str]] = mapped_column(Text, comment="SCHEDULED|MANUAL|BOOTSTRAP")
    data_period: Mapped[Optional[str]] = mapped_column(Text, comment="e.g. 2026-07")
    records_read: Mapped[Optional[int]] = mapped_column(Integer)
    records_written: Mapped[Optional[int]] = mapped_column(Integer)
    records_skipped: Mapped[Optional[int]] = mapped_column(Integer)
    warning_count: Mapped[Optional[int]] = mapped_column(Integer)
    error_count: Mapped[Optional[int]] = mapped_column(Integer)
    source_version: Mapped[Optional[str]] = mapped_column(Text, comment="GEE snapshot version")
    code_version: Mapped[Optional[str]] = mapped_column(Text)
    model_version: Mapped[Optional[str]] = mapped_column(Text)
    error_summary: Mapped[Optional[str]] = mapped_column(Text)


class PipelineRunStage(Base):
    __tablename__ = "pipeline_run_stages"
    __table_args__ = (
        Index("uq_pipeline_run_stages_run_stage", "run_id", "stage_name", unique=True),
        {"schema": "system"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_pk: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("system.pipeline_runs.id"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    stage_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, comment="SUCCESS|PARTIAL_SUCCESS|FAILED|SKIPPED|CANCELLED"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    records_read: Mapped[Optional[int]] = mapped_column(Integer)
    records_written: Mapped[Optional[int]] = mapped_column(Integer)
    records_skipped: Mapped[Optional[int]] = mapped_column(Integer)
    warning_count: Mapped[Optional[int]] = mapped_column(Integer)
    error_count: Mapped[Optional[int]] = mapped_column(Integer)
    log_path: Mapped[Optional[str]] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "timestamp"),
        Index("ix_audit_logs_user", "user_id"),
        Index("ix_audit_logs_module", "module"),
        {"schema": "system"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("shared.users.id"))
    role: Mapped[Optional[str]] = mapped_column(Text)
    module: Mapped[Optional[str]] = mapped_column(Text)
    resource_type: Mapped[Optional[str]] = mapped_column(Text)
    resource_id: Mapped[Optional[str]] = mapped_column(Text)
    region_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    before_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    after_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)
    result: Mapped[Optional[str]] = mapped_column(Text)
    request_id: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(Text)
    entity_id: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
