"""
scripts/propagate_surface_water.py
AquaVision - Publish Sentinel-2 water area into the weekly indicator rows.

water_indicators_weekly carries the dashboard's Reservoir/Storage card, but
sync_indicators cannot derive area (JRC GSW monthly history ends 2021, so
water_extent is -1 for every 2026 month and the area column stays NULL).

The real surface-water source of record is aquavision.surface_water_weekly
(Sentinel-2 NDWI from gee/surface_water.py -> scripts/sync_surface_water.py).
This stage propagates the LATEST water_area_km2 inside each indicator period
onto the indicator row, and computes the period-over-period change:

    change_pct = (current_period_area - previous_period_area)
                 / previous_period_area * 100

It runs AFTER sync_indicators in the pipeline so indicator re-syncs can never
wipe published values (sync_indicators only writes the extent-based change on
fresh INSERT, never on UPDATE). Rows with no surface_water_weekly data in
their period are left untouched.

Usage:
    python -m scripts.propagate_surface_water   (run from services/ml-pipeline)
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, pool_pre_ping=True)
    return _engine


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _prev_period_bounds(start: date) -> tuple[date, date]:
    first_of_month = start.replace(day=1)
    prev_end = first_of_month - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    return prev_start, prev_end


def _intersecting(
    rows_by_region: dict,
    region_id: int,
    lo: date,
    hi: date,
    before: date | None = None,
) -> list[tuple[date, float]]:
    """Weeks whose [week_start, week_start+6] window intersects [lo, hi],
    optionally restricted to week_start < `before` (for the prior-period
    lookup, so a boundary week cannot be compared against itself)."""
    week = timedelta(days=6)
    out = []
    for wk, area in rows_by_region.get(region_id, []):
        if area is None:
            continue
        if wk > hi or (wk + week) < lo:
            continue
        if before is not None and wk >= before:
            continue
        out.append((wk, area))
    out.sort()
    return out


def _changed(old, new, tol: float = 0.005) -> bool:
    if old is None and new is None:
        return False
    if old is None or new is None:
        return True
    return abs(float(old) - float(new)) > tol


def run() -> dict:
    eng = engine()
    with eng.connect() as conn:
        indicators = conn.execute(
            text(
                """
                SELECT id, region_id, period_start, period_end,
                       surface_water_area_km2, surface_water_change_pct
                FROM aquavision.water_indicators_weekly
                """
            )
        ).fetchall()
        sw_rows = conn.execute(
            text(
                """
                SELECT region_id, week_start_date, water_area_km2
                FROM aquavision.surface_water_weekly
                ORDER BY region_id, week_start_date
                """
            )
        ).fetchall()

    rows_by_region: dict[int, list[tuple[date, float | None]]] = {}
    for region_id, week_start, area in sw_rows:
        wk = _to_date(week_start)
        if wk is None:
            continue
        rows_by_region.setdefault(int(region_id), []).append(
            (wk, float(area) if area is not None else None)
        )

    updates = []
    for ind_id, region_id, period_start, period_end, cur_area, cur_change in indicators:
        start = _to_date(period_start)
        end = _to_date(period_end) or start
        if start is None:
            continue
        current = _intersecting(rows_by_region, int(region_id), start, end)
        if not current:
            continue
        cur_week, area = current[-1]
        prev_start, prev_end = _prev_period_bounds(start)
        previous = _intersecting(
            rows_by_region, int(region_id), prev_start, prev_end, before=cur_week
        )
        change = None
        if previous:
            prev_area = previous[-1][1]
            if prev_area > 0:
                change = round((area - prev_area) / prev_area * 100.0, 2)
        if _changed(cur_area, area) or _changed(cur_change, change):
            updates.append((round(area, 2), change, ind_id))

    propagated = 0
    if updates:
        with eng.begin() as conn:
            for area, change, ind_id in updates:
                conn.execute(
                    text(
                        """
                        UPDATE aquavision.water_indicators_weekly
                        SET surface_water_area_km2 = :area,
                            surface_water_change_pct = :change,
                            last_validated_at = now()
                        WHERE id = :id
                        """
                    ),
                    {"area": area, "change": change, "id": ind_id},
                )
                propagated += 1

    print(
        f"[propagate_surface_water] Propagated {propagated} rows "
        f"(indicators={len(indicators)}, sw_regions={len(rows_by_region)})"
    )
    return {"propagated": propagated, "indicators": len(indicators)}


def main() -> None:
    run()


if __name__ == "__main__":
    main()
