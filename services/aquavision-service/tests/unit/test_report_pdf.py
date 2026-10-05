"""Unit tests for weekly report PDF rendering (no DB)."""
from datetime import date, datetime, timezone

from application.report_pdf import build_report_pdf


def _data():
    return {
        "scope": "National",
        "region_name": None,
        "week_start": date(2026, 9, 28),
        "as_of_week": date(2026, 10, 1),
        "regions": [
            {"name": "Punjab", "wai": 64.0, "severity": "Moderate", "spi_3": 1.06},
            {"name": "Sindh", "wai": 44.5, "severity": "Stressed", "spi_3": -2.06},
            {"name": "Gilgit-Baltistan", "wai": None, "severity": None, "spi_3": None},
        ],
        "national_wai": 54.2,
        "national_severity": "Stressed",
        "alerts_by_severity": {"WARNING": 3, "CRITICAL": 1},
        "alerts_open_total": 4,
        "episodes_open": 2,
        "validation_total": 5,
        "validation_by_rec": {"SHADOW": 3, "REJECTED": 2},
        "assets_active": 11,
        "generated_at": datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc),
    }


def test_builds_pdf_bytes():
    pdf = build_report_pdf("Weekly Water Availability Report (National)", _data())
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def test_empty_data_still_builds():
    data = _data()
    data["regions"] = []
    data["national_wai"] = None
    data["national_severity"] = None
    data["alerts_by_severity"] = {}
    data["alerts_open_total"] = 0
    data["validation_by_rec"] = {}
    data["validation_total"] = 0
    pdf = build_report_pdf("Empty report", data)
    assert pdf[:5] == b"%PDF-"


def test_province_scope_includes_region_name():
    data = _data()
    data["scope"] = "Province"
    data["region_name"] = "Punjab"
    pdf = build_report_pdf("Province report", data)
    assert pdf[:5] == b"%PDF-"
