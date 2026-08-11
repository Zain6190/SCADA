# presentation/http/routers/reports.py
# GET /water/reports - list generated reports.
# POST /water/reports/generate - stub generator (metadata row + placeholder path).
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from application.dtos import ReportGenerateInput, WaterReportResponse
from application.use_cases.generate_water_report import GenerateWaterReportUseCase
from application.use_cases.list_water_reports import ListWaterReportsUseCase
from infrastructure.db.engine import get_session
from infrastructure.db.repositories.water_indicator_repo import WaterIndicatorRepository
from infrastructure.db.repositories.water_report_repo import WaterReportRepository

router = APIRouter()


def get_list_use_case(session: Session = Depends(get_session)) -> ListWaterReportsUseCase:
    return ListWaterReportsUseCase(WaterReportRepository(session))


def get_generate_use_case(session: Session = Depends(get_session)) -> GenerateWaterReportUseCase:
    return GenerateWaterReportUseCase(
        WaterReportRepository(session), WaterIndicatorRepository(session)
    )


@router.get("/reports", response_model=List[WaterReportResponse])
async def list_reports(
    scope: Optional[str] = Query(None, pattern="^(National|Province|District)$"),
    use_case: ListWaterReportsUseCase = Depends(get_list_use_case),
):
    """Metadata for generated weekly water reports."""
    return use_case.execute(scope=scope)


@router.post("/reports/generate", response_model=WaterReportResponse, status_code=201)
async def generate_report(
    payload: ReportGenerateInput,
    use_case: GenerateWaterReportUseCase = Depends(get_generate_use_case),
):
    """
    Stub: records report metadata with a placeholder PDF path.
    TODO(AquaVision): wire real PDF generation in report-service.
    """
    return use_case.execute(payload)
