# domain/entities.py
# Pure domain entities (no framework imports). Data holders + behaviour.
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional


@dataclass
class WaterIndicatorWeekly:
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


@dataclass
class WaterPredictionWeekly:
    region_id: int
    target_week_start_date: date
    model_type: Optional[str] = None
    model_version: Optional[str] = None
    predicted_severity: Optional[str] = None
    predicted_wai_score: Optional[float] = None
    confidence: Optional[float] = None


@dataclass
class WaterAlert:
    id: Optional[int]
    region_id: int
    week_start_date: date
    alert_type: str
    severity: str
    status: str = "New"
    wai_score: Optional[float] = None
    rainfall_anomaly: Optional[float] = None
    et_anomaly: Optional[float] = None
    surface_water_change_pct: Optional[float] = None
    assigned_to_user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None

    def acknowledge(self, at: Optional[datetime] = None) -> None:
        """New -> Acknowledged."""
        if self.status == "Resolved":
            raise DomainValidationError(
                "Cannot acknowledge a resolved alert."
            )
        self.status = "Acknowledged"
        self.acknowledged_at = at or datetime.now(timezone.utc)

    def resolve(self, at: Optional[datetime] = None) -> None:
        """(New | Acknowledged) -> Resolved."""
        if self.status == "Resolved":
            raise DomainValidationError("Alert is already resolved.")
        self.status = "Resolved"
        if self.acknowledged_at is None:
            self.acknowledged_at = at or datetime.now(timezone.utc)
        self.resolved_at = at or datetime.now(timezone.utc)


@dataclass
class WaterReport:
    week_start_date: date
    title: str
    scope: str
    region_id: Optional[int] = None
    file_path: Optional[str] = None
    generated_by_user_id: Optional[int] = None
    status: str = "Success"


@dataclass
class WaterThreshold:
    threshold_name: str
    value: float
    description: Optional[str] = None


class DomainValidationError(Exception):
    """Raised when a domain invariant is violated."""
