"""
scripts/run_risk_alerts.py
AquaVision - Complete risk-and-alert workflow.

Combines the trained models into an operational decision layer:
  1. Load latest GEE features + trained WAI model + anomaly detector
  2. Compute per-region risk score (WAI + anomaly + thresholds)
  3. Auto-generate / update alerts in aquavision.water_alerts

Alert generation rules (aligned with DB check constraints + water_thresholds):
  - WAI < 25           -> alert_type=WAI_CRITICAL, severity=Critical
  - WAI < 40           -> alert_type=WAI_SEVERE,   severity=Severe
  - rainfall_anomaly   -> alert_type=RAINFALL_DEFICIT, severity=Warning
  - et_anomaly         -> alert_type=HIGH_ET,          severity=Warning
  - IsolationForest -1 -> extra anomaly flag (writes to notes)

Usage:
    python -m scripts.run_risk_alerts   (run from packages/ml-pipeline)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ML_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ML_ROOT / "models" / "artifacts"
RAW_CSV = ML_ROOT / "Data" / "raw" / "region_features.csv"
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:1234@localhost:5433/ibcp_scada"
)
FEATURE_COLS = ["rainfall_mm", "et_mm", "water_extent", "ndvi", "month_idx"]
RULE_VERSION = os.getenv("GEE_RULE_VERSION", "risk-v1.0")
_ONE_MONTH = timedelta(days=31)

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
    return _engine


def latest_artifact(pattern: str) -> Path:
    files = sorted(ARTIFACT_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No artifact matching {pattern}")
    return files[-1]


def load_thresholds() -> dict:
    with engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT threshold_name, value FROM aquavision.water_thresholds"
            )
        ).fetchall()
    return {r.threshold_name: float(r.value) for r in rows}


def anomaly_ratio(feats: pd.DataFrame, detector) -> pd.Series:
    """Normalize IsolationForest score to a 0..1 anomaly ratio (1 = extreme)."""
    scores = detector.decision_function(feats[FEATURE_COLS])
    return (1.0 - scores) / 2.0


def _confidence(wai: float, anom_ratio: float) -> float:
    """MODEL confidence 0..1: distance from the nearest severity boundary +
    anomaly strength. Far below a boundary (very dry) is high confidence."""
    boundaries = sorted(
        {th[k] for k in ("wai_critical_min", "wai_severe_min", "wai_stressed_min")}
    )
    margin = min(abs(wai - b) for b in boundaries)
    return round(min(0.99, max(0.5, 0.5 + margin / 40.0 * 0.35 + float(anom_ratio) * 0.3)), 3)


def build_alert_rows(region_rows: list[dict]) -> list[dict]:
    """Decide which alerts to create for each region based on model outputs."""
    alerts = []
    for r in region_rows:
        wai = r["wai"]
        rain_anom = r["rainfall_anomaly"]  # % anomaly (negative = deficit)
        et_anom = r["et_anomaly"]          # % anomaly (positive = high ET)
        anom_ratio = r["anomaly_ratio"]
        conf = _confidence(wai, anom_ratio)

        if wai < th["wai_critical_min"]:
            alerts.append(
                dict(
                    region_id=r["region_id"], alert_type="WAI_CRITICAL",
                    severity="Critical", wai_score=wai, rainfall_anomaly=rain_anom,
                    et_anomaly=et_anom, anom_ratio=anom_ratio, confidence=conf,
                )
            )
        elif wai < th["wai_severe_min"]:
            alerts.append(
                dict(
                    region_id=r["region_id"], alert_type="WAI_SEVERE",
                    severity="Severe", wai_score=wai, rainfall_anomaly=rain_anom,
                    et_anomaly=et_anom, anom_ratio=anom_ratio, confidence=conf,
                )
            )
        if rain_anom < th["rainfall_deficit_pct"]:
            alerts.append(
                dict(
                    region_id=r["region_id"], alert_type="RAINFALL_DEFICIT",
                    severity="Warning", wai_score=wai, rainfall_anomaly=rain_anom,
                    et_anomaly=et_anom, anom_ratio=anom_ratio, confidence=conf,
                )
            )
        if et_anom > th["et_anomaly_high"]:
            alerts.append(
                dict(
                    region_id=r["region_id"], alert_type="HIGH_ET",
                    severity="Warning", wai_score=wai, rainfall_anomaly=rain_anom,
                    et_anomaly=et_anom, anom_ratio=anom_ratio, confidence=conf,
                )
            )
    return alerts


def write_alerts(alerts: list[dict], week: date) -> tuple[int, int]:
    """Insert/update alerts for the given period; resolve episodes that cleared.

    Dedup rule: one alert row per (region_id, week_start_date, alert_type,
    rule_version). If the same condition still holds on a re-run, the existing
    row is updated (fresh wai/confidence, source, rule_version). If a condition
    clears, the previous model-generated alert for that period is resolved so
    users never get a pile-up of duplicate alerts across re-runs.

    Returns (written_count, resolved_count).
    """
    eng = engine()
    written = 0
    resolved = 0
    now_ts = f"{datetime.now(timezone.utc).isoformat()}"
    with eng.begin() as conn:
        for a in alerts:
            exists = conn.execute(
                text(
                    "SELECT id FROM aquavision.water_alerts "
                    "WHERE region_id=:r AND week_start_date=:w AND alert_type=:t AND rule_version=:v"
                ),
                {"r": a["region_id"], "w": week, "t": a["alert_type"], "v": RULE_VERSION},
            ).fetchone()
            if exists:
                conn.execute(
                    text(
                        """
                        UPDATE aquavision.water_alerts
                        SET severity=:severity, wai_score=:wai, rainfall_anomaly=:rain,
                            et_anomaly=:et, confidence=:conf, source='MODEL', notes=:notes
                        WHERE id=:id
                        """
                    ),
                    {
                        "id": exists[0], "severity": a["severity"], "wai": a["wai_score"],
                        "rain": a["rainfall_anomaly"], "et": a["et_anomaly"],
                        "conf": a["confidence"], "notes": f"auto (anomaly_ratio={a['anom_ratio']:.2f})",
                    },
                )
                written += 1
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO aquavision.water_alerts
                        (region_id, week_start_date, alert_type, severity,
                         wai_score, rainfall_anomaly, et_anomaly,
                         surface_water_change_pct, status, notes, source,
                         confidence, rule_version, created_at)
                    VALUES (:region_id, :week, :alert_type, :severity,
                            :wai, :rain, :et, 0, 'New', :notes, 'MODEL',
                            :conf, :rule_version, :now_ts)
                    """
                ),
                {
                    "region_id": a["region_id"],
                    "week": week,
                    "alert_type": a["alert_type"],
                    "severity": a["severity"],
                    "wai": a["wai_score"],
                    "rain": a["rainfall_anomaly"],
                    "et": a["et_anomaly"],
                    "notes": f"auto (anomaly_ratio={a['anom_ratio']:.2f})",
                    "conf": a["confidence"],
                    "rule_version": RULE_VERSION,
                    "now_ts": now_ts,
                },
            )
            written += 1

        # Resolve model alerts for the PREVIOUS period whose condition cleared
        # (still in an open lifecycle state, auto-generated by us).
        prev_week = (week - _ONE_MONTH).strftime("%Y-%m-%d") if week else None
        if prev_week:
            active_statuses = ("'New','ACTIVE','ACKNOWLEDGED','INVESTIGATING','ACTION_REQUIRED',"
                               "'RESPONSE_COMPLETED','WAITING_FOR_VERIFICATION','ESCALATED','HANDOVER_REQUIRED'")
            still_active = {(a["region_id"], a["alert_type"]) for a in alerts}
            stale_rows = conn.execute(
                text(
                    f"""
                    SELECT id, region_id, alert_type FROM aquavision.water_alerts
                    WHERE source='MODEL' AND rule_version=:v
                      AND week_start_date=:prev
                      AND status IN ({active_statuses})
                    """
                ),
                {"v": RULE_VERSION, "prev": prev_week},
            ).fetchall()
            for row in stale_rows:
                if (row[1], row[2]) in still_active:
                    continue  # condition persists -> keep the episode open
                conn.execute(
                    text(
                        "UPDATE aquavision.water_alerts SET status='RESOLVED', "
                        "resolved_at=:now, notes=COALESCE(notes,'') || ' (condition cleared; auto-resolved)' "
                        "WHERE id=:id"
                    ),
                    {"now": now_ts, "id": row[0]},
                )
                resolved += 1
    print(f"[risk_alerts] Wrote {written} alerts (upserted/inserted) for {week} "
          f"| auto-resolved {resolved} cleared conditions")
    return written, resolved


th = load_thresholds()


def main() -> dict:
    reg = joblib.load(latest_artifact("wai_reg_*.joblib"))
    detector = joblib.load(latest_artifact("anomaly_if.joblib"))

    feats = pd.read_csv(RAW_CSV)
    feats["month"] = pd.to_datetime(feats["month"])
    # Use the most recent COMPLETE month (skip trailing incomplete data where
    # rainfall is NaN / ET is 0 because CHIRPS & ERA5 haven't finalized).
    complete = feats.dropna(subset=["rainfall_mm"])
    complete = complete[complete["et_mm"] > 0]
    if complete.empty:
        raise RuntimeError("No complete month with rainfall + ET in GEE features")
    latest_month = complete["month"].max()
    X = complete[complete["month"] == latest_month].copy()
    print(f"[risk_alerts] using latest complete month: {latest_month.date()}")
    if X.empty:
        raise RuntimeError(f"No GEE features for latest complete month {latest_month}")

    # seasonality feature = NEXT month (we forecast one month ahead)
    X["month_idx"] = (latest_month + pd.DateOffset(months=1)).month
    X.loc[X["water_extent"] == -1, "water_extent"] = float("nan")
    for col in ["rainfall_mm", "et_mm", "water_extent", "ndvi"]:
        X[col] = X[col].fillna(feats[col].median())

    pred_wai = reg.predict(X[FEATURE_COLS])
    anom_ratio = anomaly_ratio(X, detector)

    # Build region_rows with rainfall/ET anomaly from the current month's data
    region_rows = []
    for row, wai, ar in zip(X.itertuples(), pred_wai, anom_ratio):
        # anomaly % vs that region's own historical mean (simple z-ish proxy)
        hist = feats[feats["region_id"] == row.region_id]
        hist = hist[hist["et_mm"] > 0]
        rain_mean = hist["rainfall_mm"].median()
        et_mean = hist["et_mm"].median()
        rain_anom = (
            (row.rainfall_mm - rain_mean) / rain_mean * 100.0 if rain_mean else 0.0
        )
        et_anom = (
            (row.et_mm - et_mean) / et_mean * 100.0 if et_mean else 0.0
        )
        region_rows.append(
            dict(
                region_id=int(row.region_id),
                wai=round(float(wai), 2),
                rainfall_anomaly=round(float(rain_anom), 2),
                et_anomaly=round(float(et_anom), 2),
                anomaly_ratio=round(float(ar), 4),
            )
        )

    alerts = build_alert_rows(region_rows)
    target_week = (latest_month + pd.DateOffset(months=1)).date()
    written, resolved = write_alerts(alerts, target_week)
    print(f"[risk_alerts] Read {len(region_rows)} rows")

    # summary table
    print(f"\n{'region':>7} {'WAI':>7} {'rain%':>7} {'et%':>7} {'anom':>6} {'risk':>8} alerts")
    risk_levels = []
    for r in region_rows:
        n_al = sum(1 for a in alerts if a["region_id"] == r["region_id"])
        risk = risk_level(r["wai"], r["anomaly_ratio"])
        risk_levels.append((r["region_id"], risk))
        print(
            f"{r['region_id']:>7} {r['wai']:>7} {r['rainfall_anomaly']:>7} "
            f"{r['et_anomaly']:>7} {r['anomaly_ratio']:>6} {risk:>8} {n_al}"
        )
    n_critical = sum(1 for _, lv in risk_levels if lv == "CRITICAL")
    n_high = sum(1 for _, lv in risk_levels if lv == "HIGH")
    print(
        f"\n[risk_alerts] Risk summary: CRITICAL={n_critical} HIGH={n_high} of "
        f"{len(risk_levels)} regions"
    )
    return {
        "records_read": len(region_rows),
        "records_written": written,
        "records_skipped": 0,
        "warning_count": 0,
        "period": target_week.strftime("%Y-%m"),
        "resolved": resolved,
    }


def run() -> dict:
    """Orchestrator entrypoint: mirrors main() but returns an observable dict."""
    return main()


def risk_level(wai: float, anomaly_ratio: float) -> str:
    """Composite risk: severity bucket + anomaly signal."""
    if wai < th["wai_critical_min"] or anomaly_ratio >= 0.6:
        return "CRITICAL"
    if wai < th["wai_severe_min"] or anomaly_ratio >= 0.55:
        return "HIGH"
    if wai < th["wai_stressed_min"]:
        return "MEDIUM"
    return "LOW"


if __name__ == "__main__":
    run()
