# infrastructure/channels/compute_condition.py
# Module 6.4 Phase 4: turn measured canal discharges into condition rows.
#
# Reads  aquavision.water_canal_observations  (written by the IRSA ingest)
# Writes aquavision.water_channel_condition   (the module's main output)
#
# Only the GAUGE_DISCHARGE producer lives here. The NDWI_MASK producer writes
# the same table with a different `method` once Earth Engine is available; the
# two never overwrite each other because `method` is part of the unique key.
#
# Usage:
#   python -m infrastructure.channels.compute_condition
#   python -m infrastructure.channels.compute_condition --dry-run

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text

from domain.services.channel_condition_service import assess_gauge_series, needs_attention
from infrastructure.db.engine import SessionLocal

logger = logging.getLogger("aquavision.channels.condition")

METHOD = "GAUGE_DISCHARGE"


def _week_start(d: date) -> date:
    """Monday of the week containing d - the grain the scope works in."""
    return d - timedelta(days=d.weekday())


def load_weekly_discharge(db) -> Dict[str, List[tuple]]:
    """Weekly mean discharge per canal label, ascending by week.

    Aggregate '_total' rows are excluded: they are a barrage's combined
    withdrawal, not a single channel, so they have no geometry to attach to.
    """
    rows = db.execute(text("""
        SELECT canal_label,
               observed_at::date AS observed_on,
               AVG(discharge_cusecs) AS discharge
        FROM aquavision.water_canal_observations
        WHERE canal_label <> '_total'
          AND data_origin = 'REAL'
        GROUP BY canal_label, observed_at::date
        ORDER BY canal_label, observed_on
    """)).mappings().all()

    weekly: Dict[str, Dict[date, List[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        weekly[r["canal_label"]][_week_start(r["observed_on"])].append(float(r["discharge"]))

    out: Dict[str, List[tuple]] = {}
    for label, weeks in weekly.items():
        out[label] = [(w, sum(v) / len(v)) for w, v in sorted(weeks.items())]
    return out


def resolve_channels(db) -> Dict[str, int]:
    """Map each IRSA canal label to the channel_id carrying its geometry."""
    rows = db.execute(text("""
        SELECT irsa_label, id
        FROM aquavision.water_channels
        WHERE irsa_label IS NOT NULL
    """)).mappings().all()
    return {r["irsa_label"]: r["id"] for r in rows}


def compute(dry_run: bool = False) -> dict:
    summary = {
        "labels_with_data": 0, "labels_without_geometry": 0,
        "rows_written": 0, "needing_attention": 0, "unmatched": [],
    }

    with SessionLocal() as db:
        series_by_label = load_weekly_discharge(db)
        channel_ids = resolve_channels(db)
        summary["labels_with_data"] = len(series_by_label)

        for label, readings in sorted(series_by_label.items()):
            channel_id = channel_ids.get(label)
            if channel_id is None:
                # Readings exist but no geometry has been loaded for this canal.
                # Report it rather than dropping it silently - it means the OSM
                # load has not run, or the name mapping needs an entry.
                summary["labels_without_geometry"] += 1
                summary["unmatched"].append(label)
                continue

            assessed = assess_gauge_series(readings)
            for row in assessed:
                if needs_attention(row["condition"]):
                    summary["needing_attention"] += 1
                if dry_run:
                    continue
                db.execute(text("""
                    INSERT INTO aquavision.water_channel_condition
                        (channel_id, observed_week, method, discharge_cusecs,
                         baseline, change_pct, condition, sample_count)
                    VALUES
                        (:channel_id, :week, :method, :discharge,
                         :baseline, :change_pct, :condition, :samples)
                    ON CONFLICT (channel_id, observed_week, method)
                    DO UPDATE SET
                        discharge_cusecs = EXCLUDED.discharge_cusecs,
                        baseline = EXCLUDED.baseline,
                        change_pct = EXCLUDED.change_pct,
                        condition = EXCLUDED.condition,
                        sample_count = EXCLUDED.sample_count
                """), {
                    "channel_id": channel_id,
                    "week": row["observed_week"],
                    "method": METHOD,
                    "discharge": row["discharge_cusecs"],
                    "baseline": row["baseline"],
                    "change_pct": row["change_pct"],
                    "condition": row["condition"],
                    "samples": row["sample_count"],
                })
                summary["rows_written"] += 1

            worst = [r for r in assessed if needs_attention(r["condition"])]
            logger.info("%-26s %2d weeks, %d needing attention%s",
                        label, len(assessed), len(worst),
                        f" (worst: {worst[-1]['condition']})" if worst else "")

        if not dry_run:
            db.commit()

    if summary["unmatched"]:
        logger.warning("No geometry for %d canal(s): %s - run the OSM loader",
                       len(summary["unmatched"]), ", ".join(summary["unmatched"]))
    logger.info("Condition computed: %s", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute river/canal condition from measured IRSA discharges"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify and report without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    compute(dry_run=args.dry_run)
