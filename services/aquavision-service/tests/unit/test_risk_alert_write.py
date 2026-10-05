"""write_alerts dedup + auto-resolve: re-runs must never leave stale New
alerts for the current period, must supersede rows from an older
rule_version, must keep still-active episodes open, and prev-period must be
the previous calendar month (not week - 31 days, which misses February for
a March target)."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

ML_ROOT = Path(__file__).resolve().parents[3] / "ml-pipeline"


def _load():
    if str(ML_ROOT) not in sys.path:
        sys.path.insert(0, str(ML_ROOT))
    spec = importlib.util.spec_from_file_location(
        "wai_risk_alerts_write", ML_ROOT / "scripts" / "run_risk_alerts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sqlite_engine():
    eng = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with eng.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS aquavision"))
        conn.execute(
            text(
                """
                CREATE TABLE aquavision.water_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    region_id INTEGER,
                    week_start_date TEXT,
                    alert_type TEXT,
                    severity TEXT,
                    wai_score REAL,
                    rainfall_anomaly REAL,
                    et_anomaly REAL,
                    surface_water_change_pct REAL,
                    status TEXT,
                    notes TEXT,
                    source TEXT,
                    confidence REAL,
                    rule_version TEXT,
                    created_at TEXT,
                    resolved_at TEXT
                )
                """
            )
        )
    return eng


def _seed(conn, region, week, atype, rule, wai, source="MODEL", status="New"):
    conn.execute(
        text(
            "INSERT INTO aquavision.water_alerts (region_id, week_start_date, "
            "alert_type, severity, wai_score, rainfall_anomaly, et_anomaly, "
            "surface_water_change_pct, status, notes, source, confidence, "
            "rule_version, created_at) "
            "VALUES (:r, :w, :t, 'Severe', :wai, 0, 0, 0, :st, '', :src, 0.5, "
            ":rule, '2026-10-03')"
        ),
        {"r": region, "w": week, "t": atype, "wai": wai, "st": status,
         "src": source, "rule": rule},
    )


def _alert(region, atype, wai):
    return dict(
        region_id=region, alert_type=atype, severity="Severe", wai_score=wai,
        rainfall_anomaly=-5.0, et_anomaly=10.0, confidence=0.8, anom_ratio=0.5,
    )


def _rows(eng, week=None):
    q = "SELECT region_id, week_start_date, alert_type, rule_version, status, wai_score, notes FROM aquavision.water_alerts"
    params = {}
    if week:
        q += " WHERE week_start_date = :w"
        params["w"] = week
    q += " ORDER BY id"
    with eng.connect() as conn:
        return [tuple(r) for r in conn.execute(text(q), params)]


def test_write_alerts_resolves_stale_current_week_and_supersedes_rule(monkeypatch):
    mod = _load()
    eng = _sqlite_engine()
    mod.engine = lambda: eng
    rule = mod.RULE_VERSION
    with eng.begin() as conn:
        _seed(conn, 1, "2026-09-01", "WAI_SEVERE", rule, 35.0)
        _seed(conn, 3, "2026-09-01", "WAI_SEVERE", rule, 35.39)
        _seed(conn, 7, "2026-08-01", "HIGH_ET", rule, 40.0)
        _seed(conn, 4, "2026-08-01", "HIGH_ET", rule, 41.0)
        _seed(conn, 9, "2026-09-01", "RAINFALL_DEFICIT", "risk-v0.9", 30.0)
        _seed(conn, 11, "2026-09-01", "HIGH_ET", "risk-v0.9", 50.0)
        _seed(conn, 13, "2026-09-01", "WAI_SEVERE", None, 36.0, source=None)

    active = [
        _alert(1, "WAI_SEVERE", 31.0),
        _alert(4, "HIGH_ET", 44.0),
        _alert(9, "RAINFALL_DEFICIT", 30.5),
    ]
    written, resolved = mod.write_alerts(active, date(2026, 9, 1))
    assert written == 3
    assert resolved == 4

    rows = _rows(eng)
    by_key = {(r[0], r[1], r[2], r[3]): r for r in rows}
    assert len(rows) == len(by_key) == 9

    r1 = by_key[(1, "2026-09-01", "WAI_SEVERE", rule)]
    assert r1[4] == "New" and r1[5] == 31.0 and r1[3] == rule

    assert by_key[(3, "2026-09-01", "WAI_SEVERE", rule)][4] == "RESOLVED"
    assert by_key[(7, "2026-08-01", "HIGH_ET", rule)][4] == "RESOLVED"

    r4 = by_key[(4, "2026-08-01", "HIGH_ET", rule)]
    assert r4[4] == "New", "condition persists -> previous-period episode stays open"

    r9_old = by_key[(9, "2026-09-01", "RAINFALL_DEFICIT", "risk-v0.9")]
    assert r9_old[4] == "RESOLVED" and "superseded" in r9_old[6]
    r9_new = by_key[(9, "2026-09-01", "RAINFALL_DEFICIT", rule)]
    assert r9_new[4] == "New"

    assert by_key[(11, "2026-09-01", "HIGH_ET", "risk-v0.9")][4] == "New"

    r13 = by_key[(13, "2026-09-01", "WAI_SEVERE", None)]
    assert r13[4] == "RESOLVED" and "condition cleared" in r13[6]

    active_keys = [(r[0], r[1], r[2]) for r in rows if r[4] != "RESOLVED"]
    assert len(active_keys) == len(set(active_keys)), "no duplicate active alerts"


def test_prev_period_is_the_previous_calendar_month():
    mod = _load()
    assert mod._prev_month(date(2026, 9, 1)) == date(2026, 8, 1)
    assert mod._prev_month(date(2026, 3, 1)) == date(2026, 2, 1)
    assert mod._prev_month(date(2026, 5, 1)) == date(2026, 4, 1)
    assert mod._prev_month(date(2026, 1, 1)) == date(2025, 12, 1)
