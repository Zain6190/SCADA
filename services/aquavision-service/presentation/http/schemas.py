# presentation/http/schemas.py
# View / serialization layer: HTTP request bodies.
# Response schemas are the application DTOs (FastAPI response_model serializes them).
from typing import Optional

from pydantic import BaseModel, Field

from application.dtos import (
    AlertStatusInput,
    ReportGenerateInput,
    WaterIndicatorCreate,
)

__all__ = [
    "WaterIndicatorCreate",
    "AlertStatusInput",
    "ReportGenerateInput",
    "IndicatorQueryParams",
]


class IndicatorQueryParams(BaseModel):
    region_id: Optional[int] = None
    severity: Optional[str] = Field(
        default=None, pattern="^(Normal|Moderate|Stressed|Critical|Severe)$"
    )
    week_start_date: Optional[str] = None
    limit: int = Field(100, ge=1, le=1000)
