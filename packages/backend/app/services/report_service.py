# packages/backend/app/services/report_service.py
# AquaVision weekly PDF reports + CSV / GeoJSON data exports.
#
# Exports always honour the caller's geographic scope AND access level: the
# same backend filter used by the live endpoints (`filter_indicators`) is
# applied so analysis fields (rainfall / ET / anomaly) never leak to viewers.
import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import select, func, and_
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

from app.core.database import SessionLocal
from app.models import db as orm
from app.services import water_service

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = BACKEND_ROOT / "reports" / "water"

SEVERITY_COLORS = {
    "Normal": colors.HexColor("#15803d"),
    "Moderate": colors.HexColor("#65a30d"),
    "Stressed": colors.HexColor("#ca8a04"),
    "Warning": colors.HexColor("#d97706"),
    "Severe": colors.HexColor("#ea580c"),
    "Critical": colors.HexColor("#dc2626"),
}

# ---------------------------------------------------------------------------
# CSV / GeoJSON exports
# ---------------------------------------------------------------------------
def indicators_to_csv(indicators: List[dict]) -> str:
    """Serialize access-filtered indicator dicts to CSV text (with header)."""
    if not indicators:
        return ", ".join(water_service._VIEWER_FIELDS) + "\n"
    fieldnames = list(indicators[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in indicators:
        writer.writerow({k: _csv_value(v) for k, v in row.items()})
    return buf.getvalue()


def _csv_value(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def _json_safe(obj):
    """Recursively convert datetime/date objects for JSON serialization."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def latest_geojson(scope: Optional[List[int]], permissions: Optional[list]) -> dict:
    """GeoJSON FeatureCollection: region polygons joined with the latest
    weekly indicators, access-level filtered."""
    with SessionLocal() as db:
        regions_q = select(
            orm.Region, func.st_asgeojson(orm.Region.geom).label("geometry")
        )
        if scope:
            regions_q = regions_q.where(orm.Region.id.in_(scope))
        regions = db.execute(regions_q).all()

    indicators = water_service.get_latest_indicators(scope=scope)
    by_region = {i.region_id: i for i in indicators}

    week = max((i.week_start_date for i in indicators), default=None)
    features = []
    for region, geometry in regions:
        ind = by_region.get(region.id)
        props: dict = {"region_id": region.id, "name": region.name, "region_type": region.type}
        if ind is not None:
            filtered = water_service.filter_indicators([ind], permissions)
            props.update(_json_safe(filtered[0]) if filtered else {})
        features.append({
            "type": "Feature",
            "geometry": json.loads(geometry) if geometry else None,
            "properties": props,
        })
    return {
        "type": "FeatureCollection",
        "week": str(week) if week else None,
        "features": features,
    }


def indicators_geojson(
    indicators: List[orm.WaterIndicator],
    scope: Optional[List[int]],
    permissions: Optional[list],
) -> dict:
    """FeatureCollection built from already-fetched indicator rows (centroid
    points). Used by the analyst CSV/GeoJSON companion export."""
    rows = water_service.filter_indicators(indicators, permissions)
    with SessionLocal() as db:
        centroids_q = select(
            orm.Region.id,
            func.st_y(func.st_centroid(orm.Region.geom)).label("lat"),
            func.st_x(func.st_centroid(orm.Region.geom)).label("lon"),
        )
        if scope:
            centroids_q = centroids_q.where(orm.Region.id.in_(scope))
        centroids = {r.id: (float(r.lat), float(r.lon)) for r in db.execute(centroids_q).all()}
    week = max((i.week_start_date for i in indicators), default=None)
    features = []
    for row in rows:
        lat, lon = centroids.get(row.get("region_id"), (0.0, 0.0))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": _json_safe(row),
        })
    return {
        "type": "FeatureCollection",
        "week": str(week) if week else None,
        "features": features,
    }


# ---------------------------------------------------------------------------
# Weekly PDF report generation
# ---------------------------------------------------------------------------
def generate_weekly_report(
    user_id: int,
    scope: Optional[List[int]],
) -> Tuple[date, str, str]:
    """Build the weekly PDF report on disk.

    Returns (week_start_date, title, file_path) where file_path is
    repository-relative (e.g. reports/water/2026-07-27.pdf) so the caller can
    persist it in water_reports and serve it back via /reports/{id}/download.
    """
    latest = water_service.get_latest_indicators(scope=scope)
    regions = {r.id: r.name for r in water_service.get_regions(scope=scope)}
    overview = water_service.get_overview(scope=scope)
    predictions = water_service.get_predictions(scope=scope)
    alerts = water_service.get_alerts(status="New", scope=scope)

    week = overview.week_start_date if overview else (latest[0].week_start_date if latest else date.today())
    title = f"Weekly Water Availability Report - {week.isoformat()}"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{week.isoformat()}.pdf"
    file_path = f"reports/water/{filename}"
    full_path = REPORTS_DIR / filename

    _write_pdf(full_path, latest, regions, overview, predictions, alerts, week)
    return week, title, file_path


def _write_pdf(full_path, latest, regions, overview, predictions, alerts, week: date) -> None:
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16, leading=20,
                                textColor=colors.HexColor("#0f172a"), alignment=TA_CENTER),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9, leading=12,
                                   textColor=colors.HexColor("#475569"), alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=12, leading=15,
                             textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12,
                               textColor=colors.HexColor("#1e293b")),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10,
                               textColor=colors.HexColor("#1e293b")),
        "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8, leading=10,
                                textColor=colors.white),
    }
    doc = SimpleDocTemplate(str(full_path), pagesize=landscape(A4),
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"AquaVision Weekly Report {week.isoformat()}",
                            author="IBCP-SCADA / AquaVision")

    story = []
    story.append(Paragraph("Weekly Water Availability Report", styles["title"]))
    story.append(Paragraph(
        f"Indus Basin Cyber-Physical SCADA System - AquaVision | "
        f"Week starting {week.isoformat()} | Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        styles["subtitle"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284c7")))

    # ---- Executive summary ----
    story.append(Paragraph("1. Executive Summary", styles["h1"]))
    regions_monitored = overview.regions_monitored if overview else len(latest)
    avg_wai = overview.avg_wai_score if overview else 0.0
    critical = overview.critical_regions if overview else 0
    active = overview.active_alerts if overview else 0
    status = overview.national_status if overview else "Unknown"
    kpi = Table(
        [
            ["Regions", "Avg WAI", "National Status", "Critical/Severe", "Active Alerts"],
            [str(regions_monitored), f"{avg_wai:.1f}", status, str(critical), str(active)],
        ],
        colWidths=None,
    )
    kpi.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e0f2fe")),
        ("FONTSIZE", (0, 1), (-1, 1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94a3b8")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(kpi)

    # ---- District table ----
    story.append(Paragraph("2. District Water Availability (WAI)", styles["h1"]))
    if latest:
        header = ["District", "WAI", "Severity", "Rain 30d (mm)", "Rain Anom (%)",
                  "ET 8d (mm)", "ET Anom (%)", "SW Area (km/sq)", "SW Change (%)"]
        rows = [header]
        order = sorted(latest, key=lambda i: (i.severity or ""), reverse=True)
        severity_rank = {"Critical": 5, "Severe": 4, "Stressed": 3, "Moderate": 2, "Normal": 1}
        order.sort(key=lambda i: severity_rank.get(i.severity, 0), reverse=True)
        for i in order:
            rows.append([
                Paragraph(regions.get(i.region_id, f"Region #{i.region_id}"), styles["cell"]),
                f"{float(i.wai_score):.1f}",
                i.severity or "-",
                _fmt(i.rainfall_mm_30day, 1),
                _fmt(i.rainfall_anomaly, 1),
                _fmt(i.et_mm_8day, 1),
                _fmt(i.et_anomaly, 1),
                _fmt(i.surface_water_area_km2, 1),
                _fmt(i.surface_water_change_pct, 1),
            ])
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        for ri, i in enumerate(order, start=1):
            sev_color = SEVERITY_COLORS.get(i.severity)
            if sev_color:
                table.setStyle(TableStyle([
                    ("TEXTCOLOR", (2, ri), (2, ri), colors.white),
                    ("BACKGROUND", (2, ri), (2, ri), sev_color),
                    ("FONTNAME", (2, ri), (2, ri), "Helvetica-Bold"),
                ]))
        story.append(table)
    else:
        story.append(Paragraph("No indicator data available for the report period.", styles["body"]))

    # ---- Critical regions ----
    story.append(Paragraph("3. Critical & Severe Regions", styles["h1"]))
    critical_rows = [i for i in latest if i.severity in ("Critical", "Severe")]
    if critical_rows:
        body = "".join(
            f"<b>{regions.get(i.region_id, f'Region #{i.region_id}')}</b> - {i.severity} "
            f"(WAI {i.wai_score:.1f}); rainfall anomaly {_fmt(i.rainfall_anomaly, 1)}%, "
            f"ET anomaly {_fmt(i.et_anomaly, 1)}%, surface water change "
            f"{_fmt(i.surface_water_change_pct, 1)}%.<br/>"
            for i in sorted(critical_rows, key=lambda x: (x.severity == "Critical", x.severity == "Severe"), reverse=True)
        )
        story.append(Paragraph(body, styles["body"]))
    else:
        story.append(Paragraph("No districts in Critical or Severe scarcity this week.", styles["body"]))

    # ---- Predictions ----
    story.append(Paragraph("4. Two-Week Predictions", styles["h1"]))
    active_preds = [
        p for p in predictions
        if p.target_week_start_date >= date.today()
    ] if predictions else []
    pred_rows = [["District", "Target Week", "Predicted Severity", "Predicted WAI", "Confidence"]]
    for p in active_preds[:30] or predictions[:30]:
        pred_rows.append([
            regions.get(p.region_id, f"Region #{p.region_id}"),
            str(p.target_week_start_date),
            p.predicted_severity,
            _fmt(p.predicted_wai_score, 1),
            f"{float(p.confidence or 0.0) * 100:.0f}%",
        ])
    pred_table = Table(pred_rows, repeatRows=1)
    pred_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ea580c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(pred_table)

    # ---- Alerts ----
    story.append(Paragraph("5. Active Alerts", styles["h1"]))
    if alerts:
        body = "".join(
            f"<b>[{a.severity}]</b> {regions.get(a.region_id, f'Region #{a.region_id}')} - "
            f"{a.alert_type} (WAI {a.wai_score:.1f})<br/>" if a.wai_score is not None else
            f"<b>[{a.severity}]</b> {regions.get(a.region_id, f'Region #{a.region_id}')} - {a.alert_type}<br/>"
            for a in alerts
        )
        story.append(Paragraph(body, styles["body"]))
    else:
        story.append(Paragraph("No new alerts this week.", styles["body"]))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#94a3b8")))
    story.append(Paragraph(
        "Data sources: Sentinel-2 / Landsat (NDWI/MNDWI), MODIS MOD16 (ET), CHIRPS (rainfall), "
        "JRC Global Surface Water v1.4. Generated for internal decision support; not a substitute "
        "for official IRSA / WAPDA / PMD or provincial irrigation records.",
        styles["subtitle"]))
    doc.build(story)


def _fmt(value, digits: int) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


# ---------------------------------------------------------------------------
# Report metadata persistence
# ---------------------------------------------------------------------------
def create_report(
    week_start_date: date,
    title: str,
    scope: str,
    user_id: int,
    file_path: str,
    status: str = "Success",
) -> orm.WaterReport:
    """Persist a generated report row and return the ORM object."""
    with SessionLocal() as db:
        report = orm.WaterReport(
            week_start_date=week_start_date, title=title, scope=scope,
            file_path=file_path, generated_by_user_id=user_id, status=status,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report


def resolve_report_file(file_path: Optional[str]) -> Optional[Path]:
    """Resolve a stored report file_path to a real on-disk path (None if
    missing or unsafe). file_path stored as repo-relative like
    reports/water/2026-07-27.pdf."""
    if not file_path:
        return None
    candidate = (BACKEND_ROOT / file_path).resolve()
    if not candidate.is_file():
        return None
    if not str(candidate).startswith(str(BACKEND_ROOT.resolve())):
        return None
    return candidate