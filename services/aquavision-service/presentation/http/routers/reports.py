# presentation/http/routers/reports.py
# GET /water/reports - list generated reports.
# POST /water/reports/generate - record report metadata.
# GET /water/reports/{report_id}/download - render the PDF and return it.
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from application.dtos import ReportGenerateInput, WaterReportResponse
from application.report_pdf import build_report_pdf, collect_report_data
from application.use_cases.generate_water_report import GenerateWaterReportUseCase
from application.use_cases.list_water_reports import ListWaterReportsUseCase
from infrastructure.auth.jwt import decode_token, security
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


@router.get("/reports/ot-section")
def ot_report(session: Session = Depends(get_session)):
    """Soft OT weekly section: mode, official date, interlocks, scenario divergence."""
    from infrastructure.ot.persist import get_runtime, ot_report_section
    return ot_report_section(get_runtime(db=session))


@router.get("/reports", response_model=List[WaterReportResponse])
def list_reports(
    scope: Optional[str] = Query(None, pattern="^(National|Province|District)$"),
    use_case: ListWaterReportsUseCase = Depends(get_list_use_case),
):
    """Metadata for generated weekly water reports."""
    return use_case.execute(scope=scope)


@router.post("/reports/generate", response_model=WaterReportResponse, status_code=201)
def generate_report(
    payload: Optional[ReportGenerateInput] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    use_case: GenerateWaterReportUseCase = Depends(get_generate_use_case),
):
    """Record a new weekly report row; the PDF is rendered on download."""
    generated_by_user_id = None
    if credentials is not None:
        try:
            generated_by_user_id = int(decode_token(credentials.credentials).get("sub"))
        except (ValueError, TypeError):
            generated_by_user_id = None
    return use_case.execute(payload or ReportGenerateInput(), generated_by_user_id)


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    session: Session = Depends(get_session),
):
    """Render the report's PDF on demand and return it as a file download."""
    report = WaterReportRepository(session).get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    data = collect_report_data(session, report.week_start_date, report.scope, report.region_id)
    pdf = build_report_pdf(report.title, data)
    filename = f"aqua-report-{report.week_start_date.isoformat()}-{report.scope.lower()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
