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


@router.get("/reports/satellite-section")
async def satellite_report(session: Session = Depends(get_session)):
    """Worst districts, rainfall, ET, surface water, and the image week."""
    from sqlalchemy import text

    from infrastructure.ingestion.satellite_publish import REPO, satellite_section

    names = {}
    try:
        found = session.execute(text("SELECT id, name FROM shared.regions WHERE type = 'district'")).all()
        names = {int(row.id): row.name for row in found}
    except Exception:
        names = {}
    section = satellite_section(names=names)
    out = REPO / "data" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    stamp = (section.get("image_week") or "pending").replace("-", "")
    text_path = out / f"satellite-section-{stamp}.txt"
    lines = [f"Image week: {section.get('image_week') or 'not fetched'}", f"Districts: {section.get('districts')}"]
    for row in section.get("worst_districts") or []:
        lines.append(
            f"{row['name']}: rain {row['rainfall_mm']} mm, ET {row['et_mm']} mm, "
            f"surface water {row.get('surface_water_km2')} km2, NDVI {row['ndvi']}"
        )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    section["file_path"] = str(text_path)
    return section


@router.get("/reports/ot-section")
async def ot_report(session: Session = Depends(get_session)):
    """Soft OT weekly section: mode, official date, interlocks, scenario divergence."""
    from infrastructure.ot.persist import get_runtime, ot_report_section
    return ot_report_section(get_runtime(db=session))


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
