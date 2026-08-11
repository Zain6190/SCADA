# infrastructure/db/seed.py
# Idempotent demo seeding for local development - only fills empty tables.
# Real data comes from the AquaVision ETL/ML pipeline (ml-pipeline).
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from infrastructure.db.engine import SessionLocal
from infrastructure.db.models import WaterAlert, WaterIndicator, WaterPrediction, WaterReport

DISTRICT_IDS = list(range(5, 19))  # 5..18 (matches shared.regions seed)
BASE_WAI = {
    5: 58, 6: 42, 7: 50, 8: 30, 9: 45,
    10: 35, 11: 22, 12: 40, 13: 52,
    14: 48, 15: 55, 16: 62, 17: 33, 18: 47,
}
LATEST_WEEK = date(2026, 7, 27)


def _classify(wai: float) -> str:
    if wai < 25:
        return "Critical"
    if wai < 40:
        return "Severe"
    if wai < 55:
        return "Stressed"
    if wai < 70:
        return "Moderate"
    return "Normal"


def seed_if_empty() -> None:
    with SessionLocal() as db:
        if db.execute(select(func.count()).select_from(WaterIndicator)).scalar() == 0:
            for i in range(1, 7):
                week_start = LATEST_WEEK - timedelta(weeks=6 - i)
                iso = week_start.isocalendar()
                for region_id in DISTRICT_IDS:
                    drift = random.uniform(-4, 4)
                    wai = max(5, min(95, BASE_WAI[region_id] + drift + (i - 6) * 1.5))
                    db.add(WaterIndicator(
                        region_id=region_id, week_start_date=week_start,
                        week_number=iso[1], year=iso[0],
                        surface_water_area_km2=round(region_id * 12.5 + random.uniform(-30, 30), 2),
                        surface_water_change_pct=round(random.uniform(-6, 8), 2),
                        rainfall_mm_30day=round(random.uniform(0, 45), 1),
                        rainfall_anomaly=round(random.uniform(-55, 40), 1),
                        et_mm_8day=round(random.uniform(25, 70), 1),
                        et_anomaly=round(random.uniform(-15, 30), 1),
                        wai_score=round(wai, 1), severity=_classify(wai),
                        data_source_version="GEE-JRC-2026.7",
                    ))
            db.commit()

        if db.execute(select(func.count()).select_from(WaterPrediction)).scalar() == 0:
            for region_id in DISTRICT_IDS:
                for delta in (1, 2):
                    target = LATEST_WEEK + timedelta(weeks=delta)
                    predicted = max(5, min(95, BASE_WAI[region_id] + random.uniform(-6, 6)))
                    db.add(WaterPrediction(
                        region_id=region_id, target_week_start_date=target,
                        model_type="RandomForest", model_version="rf-v1.3",
                        predicted_severity=_classify(predicted),
                        predicted_wai_score=round(predicted, 1),
                        confidence=round(random.uniform(0.72, 0.94), 2),
                    ))
            db.commit()

        if db.execute(select(func.count()).select_from(WaterAlert)).scalar() == 0:
            now = datetime.utcnow()
            seed_alerts = [
                dict(region_id=11, week=date(2026, 7, 20), alert_type="WAI_CRITICAL", severity="Critical",
                     wai=22.0, rainfall=-48.0, et=22.0, sw=-5.2, status="New"),
                dict(region_id=8, week=date(2026, 7, 20), alert_type="WAI_SEVERE", severity="Severe",
                     wai=30.0, rainfall=-35.0, et=18.0, sw=-3.1, status="New"),
                dict(region_id=17, week=date(2026, 7, 13), alert_type="RAINFALL_DEFICIT", severity="Severe",
                     wai=33.0, rainfall=-55.0, et=15.0, sw=-2.0, status="Acknowledged",
                     ack=now - timedelta(days=2), assign=2, created=now - timedelta(days=3)),
                dict(region_id=10, week=date(2026, 7, 20), alert_type="HIGH_ET", severity="Warning",
                     wai=35.0, rainfall=-22.0, et=28.0, sw=-1.5, status="Acknowledged",
                     ack=now - timedelta(days=1), assign=3, created=now - timedelta(days=2)),
                dict(region_id=6, week=date(2026, 7, 6), alert_type="WAI_SEVERE", severity="Severe",
                     wai=38.0, rainfall=-30.0, et=14.0, sw=-2.8, status="Resolved",
                     ack=now - timedelta(days=5), resolved=now - timedelta(days=4),
                     created=now - timedelta(days=12), notes="Irrigation releases restored"),
            ]
            for s in seed_alerts:
                db.add(WaterAlert(
                    region_id=s["region_id"], week_start_date=s["week"],
                    alert_type=s["alert_type"], severity=s["severity"],
                    wai_score=s["wai"], rainfall_anomaly=s["rainfall"],
                    et_anomaly=s["et"], surface_water_change_pct=s["sw"],
                    status=s["status"], assigned_to_user_id=s.get("assign"),
                    acknowledged_at=s.get("ack"), resolved_at=s.get("resolved"),
                    created_at=s.get("created", now), notes=s.get("notes"),
                ))
            db.commit()

        if db.execute(select(func.count()).select_from(WaterReport)).scalar() == 0:
            for week, scope, title, uid in [
                (date(2026, 7, 20), "Province", "Weekly Water Availability Report - Sindh", 1),
                (date(2026, 7, 13), "National", "National Water Stress Summary", 1),
                (date(2026, 7, 6), "District", "Bahawalpur District Water Report", 2),
            ]:
                db.add(WaterReport(
                    week_start_date=week, title=title, scope=scope,
                    file_path=f"/reports/water/{week.isoformat()}.pdf",
                    generated_by_user_id=uid, status="Success",
                ))
            db.commit()
