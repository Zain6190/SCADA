# packages/backend/app/models/water.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime

class Region(BaseModel):
    id: int
    name: str
    code: str
    type: str  # province, district, tehsil
    parent_region_id: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class WaterIndicator(BaseModel):
    id: int
    region_id: int
    week_start_date: date
    week_number: Optional[int] = None
    year: Optional[int] = None
    surface_water_area_km2: Optional[float] = None
    surface_water_change_pct: Optional[float] = None
    rainfall_mm_30day: Optional[float] = None
    rainfall_anomaly: Optional[float] = None
    et_mm_8day: Optional[float] = None
    et_anomaly: Optional[float] = None
    spi_1: Optional[float] = None
    spi_3: Optional[float] = None
    spi_6: Optional[float] = None
    spi_12: Optional[float] = None
    spi_drought_class: Optional[str] = None
    wai_score: float
    severity: Optional[str] = None  # Normal, Moderate, Stressed, Critical, Severe
    data_source_version: Optional[str] = None
    data_status: Optional[str] = None  # Actual, Calibrated, Estimate, Missing
    data_quality: Optional[str] = None  # Good, Ok, Stale, Missing
    data_provider: Optional[str] = None
    wai_model_version: Optional[str] = None
    source_observed_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WaterIndicatorCreate(BaseModel):
    region_id: int
    week_start_date: date
    surface_water_area_km2: Optional[float] = None
    surface_water_change_pct: Optional[float] = None
    rainfall_mm_30day: Optional[float] = None
    rainfall_anomaly: Optional[float] = None
    et_mm_8day: Optional[float] = None
    et_anomaly: Optional[float] = None
    spi_1: Optional[float] = None
    spi_3: Optional[float] = None
    spi_6: Optional[float] = None
    spi_12: Optional[float] = None
    spi_drought_class: Optional[str] = None
    wai_score: float
    data_source_version: Optional[str] = None
    data_status: Optional[str] = None
    data_quality: Optional[str] = None
    data_provider: Optional[str] = None
    wai_model_version: Optional[str] = None
    source_observed_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None

class WaterPrediction(BaseModel):
    id: int
    region_id: int
    target_week_start_date: date
    model_type: str  # RandomForest, XGBoost
    model_version: str
    predicted_severity: str
    predicted_wai_score: Optional[float] = None
    confidence: float
    trained_on_week_start: Optional[date] = None
    dataset_version: Optional[str] = None
    feature_importance_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WaterAlert(BaseModel):
    id: int
    region_id: int
    week_start_date: date
    alert_type: str  # WAI_CRITICAL, WAI_SEVERE, RAINFALL_DEFICIT, HIGH_ET
    severity: str  # Critical, Severe, Warning
    wai_score: Optional[float] = None
    rainfall_anomaly: Optional[float] = None
    et_anomaly: Optional[float] = None
    surface_water_change_pct: Optional[float] = None
    status: str = "New"  # ACTIVE/ACKNOWLEDGED/INVESTIGATING/ACTION_REQUIRED/...
    assigned_to_user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None
    # --- #12 alarm lifecycle fields ---
    acknowledged_by_user_id: Optional[str] = None
    initial_assessment: Optional[str] = None
    estimated_response_time: Optional[datetime] = None
    investigation_notes: Optional[str] = None
    action_taken: Optional[str] = None
    action_result: Optional[str] = None
    action_time: Optional[datetime] = None
    evidence_refs: Optional[List[str]] = Field(default_factory=list)
    escalated_to: Optional[str] = None
    escalated_at: Optional[datetime] = None
    verified_by_user_id: Optional[str] = None
    verified_at: Optional[datetime] = None
    resolved_by_user_id: Optional[str] = None

class WaterAlertUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    notes: Optional[str] = None


class AlertAcknowledge(BaseModel):
    """Operator accepted responsibility. This NEVER resolves the alert."""
    initial_assessment: str
    estimated_response_time: Optional[datetime] = None
    notes: Optional[str] = None


class AlertInvestigate(BaseModel):
    """Findings from checking SCADA / local control / field team."""
    investigation_notes: str
    status: Optional[str] = None  # e.g. ACTION_REQUIRED


class AlertRespond(BaseModel):
    """Approved operational action + recorded outcome."""
    action_taken: str
    action_result: Optional[str] = None
    action_time: Optional[datetime] = None
    evidence_refs: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None
    require_verification: bool = True  # False = direct resolve (procedure-allowed)


class AlertEscalate(BaseModel):
    escalated_to: str  # Supervisor / Regional authority / National authority
    reason: Optional[str] = None


class AlertVerify(BaseModel):
    """Supervisor confirms the response is complete and sound."""
    verified: bool = True  # False = send back for rework (re-open response)


class AlertHandover(BaseModel):
    """Shift handover: record open items for the next operator."""
    notes: Optional[str] = None
    assign_to_user_id: Optional[str] = None

class WaterReport(BaseModel):
    id: int
    week_start_date: date
    title: str
    scope: str  # National, Province, District
    region_id: Optional[int] = None
    file_path: Optional[str] = None
    generated_by_user_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "Success"

class WaterThreshold(BaseModel):
    id: int
    threshold_name: str
    value: float
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class WaterOverview(BaseModel):
    week_start_date: date
    regions_monitored: int
    avg_wai_score: float
    critical_regions: int
    active_alerts: int
    national_status: str

class MapStation(BaseModel):
    region_id: int
    name: str
    lat: float
    lon: float
    wai_score: float
    severity: str


class AssetReading(BaseModel):
    id: int
    asset_id: int
    recorded_at: datetime
    reservoir_level_m: Optional[float] = None
    storage_pct: Optional[float] = None
    inflow_cumecs: Optional[float] = None
    outflow_cumecs: Optional[float] = None
    discharge_cumecs: Optional[float] = None
    data_status: Optional[str] = None
    source: Optional[str] = None


class AssetSummary(BaseModel):
    id: int
    name: str
    asset_type: str
    region_id: Optional[int] = None
    latest: Optional[AssetReading] = None


class AssetOperationalNote(BaseModel):
    id: int
    asset_id: int
    note: str
    created_by_user_id: str
    created_at: datetime


class AssetOperationalNoteCreate(BaseModel):
    note: str


class AssetOperationalNoteList(BaseModel):
    asset_id: int
    notes: List[AssetOperationalNote]
