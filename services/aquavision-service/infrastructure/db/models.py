# infrastructure/db/models.py
# ORM entities mapped to the shared PostGIS database.
#   aquavision.*  -> owned by this service (read/write)
#   shared.*      -> read-only (regions, assets); other schemas untouched.
from datetime import date, datetime
from typing import List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSON, JSONB, BYTEA
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

    # Alert lineage
    alert_source: Mapped[str] = mapped_column(Text, nullable=False, default="WAI_MODEL")
    alert_domain: Mapped[str] = mapped_column(Text, nullable=False, default="WATER_STRESS")
    model_version: Mapped[Optional[str]] = mapped_column(Text)

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





# ---------------------------------------------------------------------------
# WATER ASSET OBSERVATION SCHEMA (INGESTION LAYER)
# ---------------------------------------------------------------------------
class WaterSource(Base):
    """Data source registry (IRSA, PMD/FFD, GEE, PCRWR, etc.)."""
    __tablename__ = "water_sources"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    authority: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)  # PDF_DAILY_REPORT, CSV, API, SATELLITE
    update_frequency: Mapped[Optional[str]] = mapped_column(Text)  # DAILY, WEEKLY, MONTHLY
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WaterAsset(Base):
    """Canonical water asset registry (one row per physical asset)."""
    __tablename__ = "water_assets"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)  # reservoir, barrage, river_station, canal, lake
    river: Mapped[Optional[str]] = mapped_column(Text)
    province: Mapped[Optional[str]] = mapped_column(Text)
    district: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric)
    capacity_maf: Mapped[Optional[float]] = mapped_column(Numeric)
    normal_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    dead_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    warning_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    critical_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    source_authority: Mapped[Optional[str]] = mapped_column(Text)
    source_identifier: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RawSourceRecord(Base):
    """Immutable archive of every raw file downloaded from a source."""
    __tablename__ = "raw_source_records"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_sources.id"), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_date: Mapped[date] = mapped_column(Date, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)  # SHA-256 of raw content
    raw_content: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WaterObservation(Base):
    """Normalized water observations from any source."""
    __tablename__ = "water_observations"
    __table_args__ = (
        UniqueConstraint("asset_id", "observed_at", "source_id", name="uq_observation_asset_time_source"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_sources.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    water_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    storage_volume: Mapped[Optional[float]] = mapped_column(Numeric)
    storage_percent: Mapped[Optional[float]] = mapped_column(Numeric)
    inflow_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    outflow_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    discharge_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    upstream_discharge_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    downstream_discharge_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    unit: Mapped[Optional[str]] = mapped_column(Text)  # cusecs, feet, MAF
    data_status: Mapped[str] = mapped_column(Text, nullable=False, default="OBSERVED_OFFICIAL")
    # OBSERVED_OFFICIAL | OBSERVED_TELEMETRY | ESTIMATED_GEE | FORECAST_FFD | MODEL_PREDICTION | SIMULATED | SYNTHETIC_HISTORICAL
    data_origin: Mapped[str] = mapped_column(Text, nullable=False, default="REAL")
    # REAL | SYNTHETIC
    quality_status: Mapped[str] = mapped_column(Text, nullable=False, default="VALID")
    # VALID | PARTIAL | SUSPECT | STALE | INVALID | MISSING
    quality_flag: Mapped[Optional[str]] = mapped_column(Text)  # OFFICIAL_DAILY_REPORT, FFD_BULLETIN, etc.
    raw_record_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.raw_source_records.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Source-aware tracking (migration 013)
    source_authority: Mapped[Optional[str]] = mapped_column(Text)  # IRSA, FFD/PMD, KAGGLE
    source_publication_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_parser_version: Mapped[Optional[str]] = mapped_column(Text)
    source_content_hash: Mapped[Optional[str]] = mapped_column(Text)
    source_priority: Mapped[Optional[int]] = mapped_column(Integer, default=3)  # 1=IRSA, 2=FFD, 3=Kaggle, 4=Synthetic

    asset: Mapped[WaterAsset] = relationship("WaterAsset")
    source: Mapped[WaterSource] = relationship("WaterSource")


class WaterAssetForecast(Base):
    """Model-generated forecasts per asset."""
    __tablename__ = "water_asset_forecasts"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    predicted_storage: Mapped[Optional[float]] = mapped_column(Numeric)
    predicted_inflow: Mapped[Optional[float]] = mapped_column(Numeric)
    predicted_outflow: Mapped[Optional[float]] = mapped_column(Numeric)
    predicted_discharge: Mapped[Optional[float]] = mapped_column(Numeric)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# THRESHOLD & ALERT SYSTEM
# ---------------------------------------------------------------------------
class WaterAssetThreshold(Base):
    """Per-asset threshold rules for alert generation."""
    __tablename__ = "water_asset_thresholds"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False, unique=True)

    # Level thresholds (reservoirs)
    warning_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    danger_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    critical_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)

    # Inflow thresholds (cusecs)
    warning_inflow: Mapped[Optional[float]] = mapped_column(Numeric)
    danger_inflow: Mapped[Optional[float]] = mapped_column(Numeric)

    # Discharge thresholds (cusecs) - river stations
    warning_discharge: Mapped[Optional[float]] = mapped_column(Numeric)
    danger_discharge: Mapped[Optional[float]] = mapped_column(Numeric)

    # Rate of change thresholds
    level_rise_watch_6h: Mapped[Optional[float]] = mapped_column(Numeric)
    level_rise_warning_6h: Mapped[Optional[float]] = mapped_column(Numeric)
    level_rise_critical_6h: Mapped[Optional[float]] = mapped_column(Numeric)

    inflow_rise_watch_6h: Mapped[Optional[float]] = mapped_column(Numeric)
    inflow_rise_warning_6h: Mapped[Optional[float]] = mapped_column(Numeric)

    # Data staleness
    stale_hours_warning: Mapped[int] = mapped_column(Integer, default=48)
    stale_hours_critical: Mapped[int] = mapped_column(Integer, default=72)

    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[WaterAsset] = relationship("WaterAsset")


class WaterOperationalAlert(Base):
    """Real-time operational alerts generated by threshold engine."""
    __tablename__ = "water_operational_alerts"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False)

    # Alert identity
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="WATCH")

    # Alert lineage
    alert_source: Mapped[str] = mapped_column(Text, nullable=False, default="RULE")
    alert_domain: Mapped[str] = mapped_column(Text, nullable=False, default="OPERATIONAL")
    rule_version: Mapped[Optional[str]] = mapped_column(Text)
    model_version: Mapped[Optional[str]] = mapped_column(Text)
    episode_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_alert_episodes.id"))

    # Triggering observation
    observation_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_observations.id"))

    # Alert details
    triggered_value: Mapped[Optional[float]] = mapped_column(Numeric)
    threshold_value: Mapped[Optional[float]] = mapped_column(Numeric)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Current readings at time of alert
    reading_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    reading_inflow_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    reading_outflow_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    reading_discharge_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)
    rate_of_change_ft_6h: Mapped[Optional[float]] = mapped_column(Numeric)

    # Status tracking
    status: Mapped[str] = mapped_column(Text, nullable=False, default="NEW")

    # Workflow
    assigned_to: Mapped[Optional[str]] = mapped_column(Text)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(Text)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[Optional[str]] = mapped_column(Text)

    # Audit
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Downstream impact (computed when alert is created)
    downstream_impact_summary: Mapped[Optional[str]] = mapped_column(Text)  # JSON summary
    downstream_population_exposed: Mapped[Optional[int]] = mapped_column(BigInteger)
    downstream_bridges_at_risk: Mapped[Optional[int]] = mapped_column(Integer)
    downstream_hospitals_at_risk: Mapped[Optional[int]] = mapped_column(Integer)
    downstream_furthest_asset: Mapped[Optional[str]] = mapped_column(Text)
    downstream_furthest_arrival_hours: Mapped[Optional[float]] = mapped_column(Numeric)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[WaterAsset] = relationship("WaterAsset")
    observation: Mapped[Optional[WaterObservation]] = relationship("WaterObservation")


class WaterAlertAuditLog(Base):
    """Full audit trail for alert actions."""
    __tablename__ = "water_alert_audit_log"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_operational_alerts.id"), nullable=False)

    action: Mapped[str] = mapped_column(Text, nullable=False)
    performed_by: Mapped[str] = mapped_column(Text, nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    old_status: Mapped[Optional[str]] = mapped_column(Text)
    new_status: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    alert: Mapped[WaterOperationalAlert] = relationship("WaterOperationalAlert")


class WaterAlertEpisode(Base):
    """Groups related alerts into flood episodes / incidents."""
    __tablename__ = "water_alert_episodes"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    episode_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="WATCH")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="OPEN")
    triggered_by_asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    triggered_by_asset: Mapped[Optional[WaterAsset]] = relationship("WaterAsset")


class WaterDownstreamImpact(Base):
    """Downstream risk mapping for each asset."""
    __tablename__ = "water_downstream_impacts"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False)
    downstream_asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"))

    # Travel time
    travel_time_hours_min: Mapped[Optional[float]] = mapped_column(Numeric)
    travel_time_hours_max: Mapped[Optional[float]] = mapped_column(Numeric)
    travel_time_hours_expected: Mapped[Optional[float]] = mapped_column(Numeric)
    distance_km: Mapped[Optional[float]] = mapped_column(Numeric)

    # Affected area
    affected_population_est: Mapped[Optional[int]] = mapped_column(Integer)
    affected_village_count: Mapped[Optional[int]] = mapped_column(Integer)
    affected_town_count: Mapped[Optional[int]] = mapped_column(Integer)
    affected_city_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Critical infrastructure
    bridges_count: Mapped[int] = mapped_column(Integer, default=0)
    hospitals_count: Mapped[int] = mapped_column(Integer, default=0)
    roads_km: Mapped[Optional[float]] = mapped_column(Numeric, default=0)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_asset: Mapped[WaterAsset] = relationship("WaterAsset", foreign_keys=[source_asset_id])
    downstream_asset: Mapped[Optional[WaterAsset]] = relationship("WaterAsset", foreign_keys=[downstream_asset_id])


# ---------------------------------------------------------------------------
# RIVER NETWORK & TRAVEL TIME MODELS
# ---------------------------------------------------------------------------
class WaterRiverNetwork(Base):
    """River segments connecting upstream/downstream assets."""
    __tablename__ = "water_river_network"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    river_name: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False)
    downstream_asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"), nullable=False)
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_km: Mapped[Optional[float]] = mapped_column(Numeric)

    source_name: Mapped[str] = mapped_column(Text, default="IRSA/PDMA")
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="PLANNING_ESTIMATE")

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    upstream_asset: Mapped[WaterAsset] = relationship("WaterAsset", foreign_keys=[upstream_asset_id])
    downstream_asset: Mapped[WaterAsset] = relationship("WaterAsset", foreign_keys=[downstream_asset_id])


class WaterTravelTimeModel(Base):
    """Flow-band-based travel time estimates for river segments."""
    __tablename__ = "water_travel_time_models"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    river_segment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_river_network.id"), nullable=False)

    # Flow band
    flow_min_cusecs: Mapped[float] = mapped_column(Numeric, nullable=False)
    flow_max_cusecs: Mapped[float] = mapped_column(Numeric, nullable=False)

    # Travel time
    travel_time_min_hours: Mapped[float] = mapped_column(Numeric, nullable=False)
    travel_time_max_hours: Mapped[float] = mapped_column(Numeric, nullable=False)
    travel_time_expected_hours: Mapped[float] = mapped_column(Numeric, nullable=False)

    # Confidence
    method: Mapped[str] = mapped_column(Text, default="Historical flood-wave observation")
    source_name: Mapped[str] = mapped_column(Text, default="IRSA/PDMA")
    calibration_event: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(Text, default="MEDIUM")

    effective_from: Mapped[Optional[date]] = mapped_column(Date)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    segment: Mapped[WaterRiverNetwork] = relationship("WaterRiverNetwork")


# ---------------------------------------------------------------------------
# FFD/PMD FLOOD BULLETIN OBSERVATIONS
# ---------------------------------------------------------------------------
class WaterFFDObservation(Base):
    """FFD/PMD flood bulletin observations (river gauge, discharge, flood status)."""
    __tablename__ = "water_ffd_observations"
    __table_args__ = (
        UniqueConstraint("asset_id", "observed_at", "source_id", name="uq_ffd_observation_asset_date_source"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"))
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_sources.id"))

    # Station info
    station_name: Mapped[str] = mapped_column(Text, nullable=False)
    river_name: Mapped[Optional[str]] = mapped_column(Text)

    # Readings
    observed_at: Mapped[date] = mapped_column(Date, nullable=False)
    gauge_level_ft: Mapped[Optional[float]] = mapped_column(Numeric)
    discharge_cusecs: Mapped[Optional[float]] = mapped_column(Numeric)

    # FFD-specific
    flood_status: Mapped[str] = mapped_column(Text, default="NORMAL")
    forecast_trend: Mapped[str] = mapped_column(Text, default="STEADY")

    # Source
    bulletin_url: Mapped[Optional[str]] = mapped_column(Text)
    raw_html: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    data_status: Mapped[str] = mapped_column(Text, default="OBSERVED")
    quality_flag: Mapped[str] = mapped_column(Text, default="FFD_BULLETIN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Optional[WaterAsset]] = relationship("WaterAsset")
    source: Mapped[Optional[WaterSource]] = relationship("WaterSource")


# ─── Pipeline Run Tracking ────────────────────────────────────────────────


class PipelineRun(Base):
    """Tracks each ingestion pipeline execution."""

    __tablename__ = "pipeline_runs"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    pipeline_type: Mapped[str] = mapped_column(String(20), nullable=False)  # IRSA, FFD, ML
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # QUEUED, RUNNING, SUCCESS, PARTIAL_SUCCESS, FAILED, SKIPPED, CANCELLED
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SCHEDULED, MANUAL, RETRY
    lock_key: Mapped[Optional[str]] = mapped_column(String(100))
    code_version: Mapped[Optional[str]] = mapped_column(String(50))
    config_version: Mapped[Optional[str]] = mapped_column(String(50))
    source_version: Mapped[Optional[str]] = mapped_column(String(50))
    log_path: Mapped[Optional[str]] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stages: Mapped[List["PipelineRunStage"]] = relationship("PipelineRunStage", back_populates="pipeline_run")


class PipelineRunStage(Base):
    """Tracks individual stages within a pipeline run."""

    __tablename__ = "pipeline_run_stages"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(50), ForeignKey("aquavision.pipeline_runs.run_id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)  # fetch, parse, validate, store, alerts
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # QUEUED, RUNNING, SUCCESS, PARTIAL_SUCCESS, FAILED, SKIPPED
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_stored: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    log_path: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="stages")


# ─── Scheduler Heartbeat ──────────────────────────────────────────────────


class SchedulerHeartbeat(Base):
    """Tracks scheduler liveness via periodic heartbeats."""

    __tablename__ = "scheduler_heartbeats"
    __table_args__ = (
        UniqueConstraint("service_name", "instance_id", name="uq_scheduler_heartbeat"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(50), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    host_name: Mapped[Optional[str]] = mapped_column(String(100))
    container_id: Mapped[Optional[str]] = mapped_column(String(100))
    version: Mapped[Optional[str]] = mapped_column(String(50))
    process_id: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING, DEGRADED, STOPPED, UNKNOWN
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())


# ─── Data Quality ─────────────────────────────────────────────────────────


class DataQualityLog(Base):
    """Logs data quality issues found during ingestion."""

    __tablename__ = "data_quality_log"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    observation_id: Mapped[Optional[int]] = mapped_column(Integer)
    check_type: Mapped[str] = mapped_column(String(50), nullable=False)  # NEGATIVE_VALUE, OUT_OF_RANGE, DUPLICATE, etc.
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_value: Mapped[Optional[float]] = mapped_column(Float)
    expected_range_min: Mapped[Optional[float]] = mapped_column(Float)
    expected_range_max: Mapped[Optional[float]] = mapped_column(Float)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)  # SUSPECT, INVALID, MISSING
    details: Mapped[Optional[str]] = mapped_column(Text)
    source_record_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─── Quarantine ───────────────────────────────────────────────────────────


class WaterObservationQuarantine(Base):
    """Stores invalid observations for audit and potential reprocessing."""

    __tablename__ = "water_observation_quarantine"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_record_id: Mapped[Optional[int]] = mapped_column(Integer)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    parsed_values: Mapped[Optional[dict]] = mapped_column(JSON)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[Optional[str]] = mapped_column(String(50))
    raw_value: Mapped[Optional[float]] = mapped_column(Float)
    parser_version: Mapped[Optional[str]] = mapped_column(String(50))
    data_status: Mapped[Optional[str]] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─── Notification Deliveries ──────────────────────────────────────────────


class NotificationDelivery(Base):
    """Tracks notification deliveries for persistent deduplication."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("dedup_key", "recipient", name="uq_notification_dedup"),
        {"schema": "aquavision"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # EMAIL, SLACK, SMS
    dedup_key: Mapped[str] = mapped_column(String(300), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # SENT, FAILED, SUPPRESSED, RETRYING
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─── ML MODEL REGISTRY & VALIDATION ────────────────────────────────────────


class ModelVersionDB(Base):
    """Model version registry — tracks lifecycle: EXPERIMENTAL→SHADOW→APPROVED→PRODUCTION."""

    __tablename__ = "model_versions"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)  # xgb_flood, iforest_anomaly, persistence
    asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"))
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="EXPERIMENTAL")
    # EXPERIMENTAL | SHADOW | APPROVED | REJECTED | PRODUCTION
    metrics: Mapped[Optional[dict]] = mapped_column(JSON)
    validation_report_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ValidationReportDB(Base):
    """Validation reports from walk-forward backtesting."""

    __tablename__ = "validation_reports"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"))
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    data_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)  # EXPERIMENTAL, SHADOW, REJECTED
    reasons: Mapped[Optional[list]] = mapped_column(JSON)
    fold_details: Mapped[Optional[list]] = mapped_column(JSON)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionErrorDB(Base):
    """Stores individual prediction errors for audit and analysis."""

    __tablename__ = "prediction_errors"
    __table_args__ = {"schema": "aquavision"}

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("aquavision.water_assets.id"))
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prediction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    error: Mapped[float] = mapped_column(Float, nullable=False)
    error_pct: Mapped[float] = mapped_column(Float, nullable=False)
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False)  # REAL, SYNTHETIC
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
