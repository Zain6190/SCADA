# application/dtos.py
# Use-case input/output DTOs. These also serve as the View (serialization)
# contract for the HTTP layer (FastAPI response_model).
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Output DTOs
# ---------------------------------------------------------------------------
class WaterOverviewResponse(BaseModel):
    week_start_date: Optional[date]
    regions_monitored: int
    avg_wai_score: float
    critical_regions: int
    active_alerts: int
    national_status: str


class WaterIndicatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    wai_score: Optional[float] = None
    severity: Optional[str] = None
    data_source_version: Optional[str] = None


class WaterPredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_id: int
    target_week_start_date: date
    model_type: Optional[str] = None
    model_version: str
    predicted_severity: Optional[str] = None
    predicted_wai_score: Optional[float] = None
    confidence: Optional[float] = None


class WaterReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_start_date: date
    title: str
    scope: str
    region_id: Optional[int] = None
    file_path: Optional[str] = None
    generated_by_user_id: Optional[int] = None
    generated_at: datetime
    status: str


class RegionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: Optional[str] = None
    type: str
    parent_region_id: Optional[int] = None


class MapFeatureResponse(BaseModel):
    type: str = "Feature"
    geometry: dict
    properties: dict


class WaterMapResponse(BaseModel):
    type: str = "FeatureCollection"
    week: Optional[str] = None
    features: List[MapFeatureResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Input DTOs
# ---------------------------------------------------------------------------
class WaterIndicatorCreate(BaseModel):
    region_id: int
    week_start_date: date
    surface_water_area_km2: Optional[float] = None
    surface_water_change_pct: Optional[float] = None
    rainfall_mm_30day: Optional[float] = None
    rainfall_anomaly: Optional[float] = None
    et_mm_8day: Optional[float] = None
    et_anomaly: Optional[float] = None
    wai_score: Optional[float] = Field(default=None, ge=0, le=100)
    data_source_version: Optional[str] = None


class ReportGenerateInput(BaseModel):
    week_start_date: Optional[date] = None
    title: Optional[str] = None
    scope: str = Field("National", pattern="^(National|Province|District)$")
    region_id: Optional[int] = None
