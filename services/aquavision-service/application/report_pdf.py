# application/report_pdf.py
# Weekly water report: data aggregation + PDF rendering (reportlab).
from datetime import date, datetime, timezone
from io import BytesIO
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SEVERITY_RANK = ["CRITICAL", "WARNING", "ADVISORY", "WATCH", "NORMAL"]


def collect_report_data(
    session: Session,
    week_start: date,
    scope: str,
    region_id: Optional[int] = None,
) -> dict:
    """Aggregate indicators, alerts, episodes, and validation stats for a report."""
    rows = session.execute(
        text(
            """
            SELECT r.name, i.wai_score, i.severity, i.spi_3, i.week_start_date
            FROM aquavision.water_indicators_weekly i
            JOIN shared.regions r ON r.id = i.region_id
            WHERE i.week_start_date = (
                SELECT MAX(i2.week_start_date)
                FROM aquavision.water_indicators_weekly i2
                WHERE i2.region_id = i.region_id
                  AND i2.week_start_date <= :week
            )
            AND (:region_id IS NULL OR i.region_id = :region_id)
            ORDER BY i.wai_score ASC NULLS LAST, r.name
            """
        ),
        {"week": week_start, "region_id": region_id},
    ).mappings().all()

    as_of = None
    if rows:
        as_of = rows[0]["week_start_date"]
    else:
        fallback = session.execute(
            text("SELECT MAX(week_start_date) FROM aquavision.water_indicators_weekly")
        ).scalar()
        if fallback:
            as_of = fallback
            rows = session.execute(
                text(
                    """
                    SELECT r.name, i.wai_score, i.severity, i.spi_3, i.week_start_date
                    FROM aquavision.water_indicators_weekly i
                    JOIN shared.regions r ON r.id = i.region_id
                    WHERE i.week_start_date = :week
                    AND (:region_id IS NULL OR i.region_id = :region_id)
                    ORDER BY i.wai_score ASC NULLS LAST, r.name
                    """
                ),
                {"week": fallback, "region_id": region_id},
            ).mappings().all()

    regions: List[dict] = [
        {
            "name": r["name"],
            "wai": float(r["wai_score"]) if r["wai_score"] is not None else None,
            "severity": r["severity"],
            "spi_3": float(r["spi_3"]) if r["spi_3"] is not None else None,
        }
        for r in rows
    ]

    scores = [r["wai"] for r in regions if r["wai"] is not None]
    national_wai = round(sum(scores) / len(scores), 1) if scores else None
    national_severity = None
    if national_wai is not None:
        from domain.water_classifier import classify_severity
        national_severity = classify_severity(national_wai)

    alert_rows = session.execute(
        text(
            """
            SELECT severity, count(*) AS n
            FROM aquavision.water_operational_alerts
            WHERE status IN ('NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'ESCALATED')
            GROUP BY severity
            """
        )
    ).all()
    alerts_by_severity = {sev: int(n) for sev, n in alert_rows}

    episodes_open = int(
        session.execute(
            text("SELECT count(*) FROM aquavision.water_alert_episodes WHERE status = 'OPEN'")
        ).scalar() or 0
    )

    validation_rows = session.execute(
        text(
            """
            SELECT recommendation, count(*) AS n
            FROM aquavision.validation_reports
            GROUP BY recommendation
            """
        )
    ).all()
    validation_by_rec = {rec: int(n) for rec, n in validation_rows}

    assets_active = int(
        session.execute(
            text("SELECT count(*) FROM aquavision.water_assets WHERE is_active = true")
        ).scalar() or 0
    )

    region_name = None
    if region_id is not None:
        region_name = session.execute(
            text("SELECT name FROM shared.regions WHERE id = :rid"),
            {"rid": region_id},
        ).scalar()

    return {
        "scope": scope,
        "region_name": region_name,
        "week_start": week_start,
        "as_of_week": as_of,
        "regions": regions,
        "national_wai": national_wai,
        "national_severity": national_severity,
        "alerts_by_severity": alerts_by_severity,
        "alerts_open_total": sum(alerts_by_severity.values()),
        "episodes_open": episodes_open,
        "validation_total": sum(validation_by_rec.values()),
        "validation_by_rec": validation_by_rec,
        "assets_active": assets_active,
        "generated_at": datetime.now(timezone.utc),
    }


def build_report_pdf(title: str, data: dict) -> bytes:
    """Render the collected report data to PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    heading = styles["Heading2"]
    body = styles["BodyText"]
    small = styles["Normal"]
    small.fontSize = 8
    small.textColor = colors.HexColor("#667085")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
    )

    story = []
    story.append(Paragraph(title, styles["Title"]))
    meta = (
        f"Scope: {data['scope']}"
        + (f" ({data['region_name']})" if data.get("region_name") else "")
        + f" &nbsp;|&nbsp; Report week: {data['week_start'].isoformat()}"
        + f" &nbsp;|&nbsp; Generated: {data['generated_at'].strftime('%Y-%m-%d %H:%M UTC')}"
    )
    story.append(Paragraph(meta, small))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Executive Summary", heading))
    summary_lines = [
        f"National Water Availability Index: <b>{data['national_wai'] if data['national_wai'] is not None else 'n/a'}</b>"
        + (f" ({data['national_severity']})" if data.get("national_severity") else ""),
        f"Open operational alerts: <b>{data['alerts_open_total']}</b>",
        f"Open flood episodes: <b>{data['episodes_open']}</b>",
        f"Active water assets monitored: <b>{data['assets_active']}</b>",
        f"Model validation reports on file: <b>{data['validation_total']}</b>",
    ]
    for line in summary_lines:
        story.append(Paragraph(f"&bull; {line}", body))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(f"Regional Water Availability (week {data['as_of_week'] or 'n/a'})", heading))
    if data["regions"]:
        table_data = [["Region", "WAI (0-100)", "Severity", "SPI-3"]]
        for r in data["regions"]:
            table_data.append([
                r["name"],
                f"{r['wai']:.1f}" if r["wai"] is not None else "-",
                r["severity"] or "-",
                f"{r['spi_3']:.2f}" if r["spi_3"] is not None else "-",
            ])
        table = Table(table_data, hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No indicator rows available for this report week.", body))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Open Operational Alerts", heading))
    if data["alerts_by_severity"]:
        ordered = [s for s in SEVERITY_RANK if s in data["alerts_by_severity"]]
        ordered += [s for s in data["alerts_by_severity"] if s not in SEVERITY_RANK]
        alert_data = [["Severity", "Open alerts"]]
        for sev in ordered:
            alert_data.append([sev, str(data["alerts_by_severity"][sev])])
        alert_data.append(["TOTAL", str(data["alerts_open_total"])])
        at = Table(alert_data, hAlign="LEFT")
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F4F7")),
        ]))
        story.append(at)
    else:
        story.append(Paragraph("No open operational alerts.", body))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Model Validation", heading))
    if data["validation_by_rec"]:
        parts = ", ".join(f"{rec}: {n}" for rec, n in sorted(data["validation_by_rec"].items()))
        story.append(Paragraph(f"{data['validation_total']} reports &mdash; {parts}", body))
    else:
        story.append(Paragraph("No validation reports on file.", body))
    story.append(Spacer(1, 8 * mm))

    story.append(
        Paragraph(
            "Generated by AquaVision (IBCP SCADA). Indicators are advisory; "
            "operational decisions require human review.",
            small,
        )
    )

    doc.build(story)
    return buf.getvalue()
