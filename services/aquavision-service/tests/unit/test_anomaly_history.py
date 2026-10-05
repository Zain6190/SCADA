"""score_history: windowed scoring over real observations must (a) match
predict() exactly (features built on the FULL series, then filtered to the
window), (b) band severity from the score thresholds, (c) return None when
no trained artifact exists, and (d) keep the 19-column feature contract."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml.models import anomaly_detector as ad_mod
from ml.models.anomaly_detector import AnomalyDetector
from infrastructure.db.models import WaterObservation


def _session(engine):
    return sessionmaker(bind=engine)()


def _sqlite_engine():
    eng = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with eng.begin() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS aquavision"))
    WaterObservation.__table__.create(bind=eng)
    return eng


def _seed(session, asset_id=1, n_days=60, spike_days_ago=3):
    now = datetime.utcnow().replace(microsecond=0)
    for i in range(n_days):
        ts = now - timedelta(days=n_days - 1 - i)
        level = 1500.0 + (i % 10) * 0.4
        inflow = 50000.0 + (i % 7) * 500.0
        outflow = 48000.0 + (i % 5) * 400.0
        if (n_days - 1 - i) == spike_days_ago:
            level += 80.0
            inflow *= 4.0
        session.add(WaterObservation(
            id=i + 1,
            asset_id=asset_id,
            source_id=1,
            observed_at=ts,
            water_level_ft=level,
            inflow_cusecs=inflow,
            outflow_cusecs=outflow,
        ))
    session.commit()


@pytest.fixture()
def trained(tmp_path, monkeypatch):
    monkeypatch.setattr(ad_mod, "MODEL_DIR", str(tmp_path))
    eng = _sqlite_engine()
    session = _session(eng)
    _seed(session)
    result = AnomalyDetector().train(
        asset_id=1, asset_name="Test Asset", session=session
    )
    assert result and result["samples"] == 60
    yield session, tmp_path
    session.close()


def test_score_history_returns_window_sorted_points(trained):
    session, _ = trained
    history = AnomalyDetector().score_history(1, session, days=7)
    assert history is not None
    points = history["points"]
    assert points, "window must contain seeded observations"
    observed = [p["observed_at"] for p in points]
    assert observed == sorted(observed)
    cutoff = datetime.utcnow() - timedelta(days=7)
    for p in points:
        assert datetime.fromisoformat(p["observed_at"]) >= cutoff
        assert set(p) >= {
            "observed_at", "anomaly_score", "is_anomaly", "severity",
            "anomaly_features", "level_ft", "inflow_cusecs", "outflow_cusecs",
        }
    assert history["anomaly_count"] == sum(1 for p in points if p["is_anomaly"])


def test_score_history_matches_predict(trained):
    session, _ = trained
    detector = AnomalyDetector()
    history = detector.score_history(1, session, days=365)
    flagged = {p["observed_at"]: p for p in history["points"] if p["is_anomaly"]}

    expected = detector.predict(asset_id=1, asset_name="Test Asset",
                                session=session, top_n=20)
    assert expected, "planted spike must be detected"
    assert set(flagged) == {r.observed_at for r in expected}
    for r in expected:
        assert flagged[r.observed_at]["anomaly_score"] == pytest.approx(
            r.anomaly_score, abs=1e-3
        )


def test_severity_bands_from_score(trained):
    session, _ = trained
    history = AnomalyDetector().score_history(1, session, days=365)
    assert history["points"]
    for p in history["points"]:
        s = p["anomaly_score"]
        if p["is_anomaly"]:
            assert s < 0
            if s < -0.3:
                assert p["severity"] == "HIGH"
            elif s < -0.15:
                assert p["severity"] == "MODERATE"
            else:
                assert p["severity"] == "LOW"
        else:
            assert s >= 0
            assert p["severity"] == "LOW"


def test_score_history_missing_artifact_returns_none(trained):
    session, _ = trained
    assert AnomalyDetector().score_history(999, session, days=30) is None


def test_score_many_matches_score_history(trained):
    session, _ = trained
    detector = AnomalyDetector()
    many = detector.score_many(session, [1, 2], days=365)
    assert set(many) == {1, 2}
    assert many[2] is None
    single = detector.score_history(1, session, days=365)
    assert many[1] is not None
    assert many[1] == single
    assert many[1]["anomaly_count"] == sum(
        1 for p in many[1]["points"] if p["is_anomaly"]
    )


def test_artifact_cache_reloads_on_file_change(trained):
    session, tmp_path = trained
    detector = AnomalyDetector()
    first = detector._load_artifact(1)
    assert first is not None
    assert detector._load_artifact(1) is first

    path = tmp_path / "anomaly_1.joblib"
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    reloaded = detector._load_artifact(1)
    assert reloaded is not first
    assert reloaded["model"] is not None


def test_series_cache_invalidates_on_new_observation(trained):
    session, _ = trained
    detector = AnomalyDetector()
    first = detector.score_many(session, [1], days=365)
    assert first[1] is not None
    n_first = len(first[1]["points"])
    assert n_first == 60

    now = datetime.utcnow().replace(microsecond=0)
    for k in range(3):
        session.add(WaterObservation(
            id=900 + k,
            asset_id=1,
            source_id=1,
            observed_at=now + timedelta(days=k + 1),
            water_level_ft=1501.0 + k,
            inflow_cusecs=51000.0,
            outflow_cusecs=49000.0,
        ))
    session.commit()

    second = detector.score_many(session, [1], days=365)
    assert second[1] is not None
    assert len(second[1]["points"]) == n_first + 3


def test_build_features_contract():
    import numpy as np
    n = 30
    levels = np.linspace(1500, 1510, n)
    inflows = np.full(n, 50000.0)
    outflows = np.full(n, 48000.0)
    stamps = [datetime(2026, 7, 1) + timedelta(days=i) for i in range(n)]
    X, names = AnomalyDetector()._build_features(
        levels, inflows, outflows, np.array(stamps, dtype=object)
    )
    assert names == [
        "level", "inflow", "outflow",
        "level_lag_1", "inflow_lag_1",
        "level_lag_3", "inflow_lag_3",
        "level_lag_7", "inflow_lag_7",
        "level_rollmean_7", "level_rollstd_7", "inflow_rollmean_7",
        "level_roc_1d", "level_roc_3d", "inflow_roc_1d",
        "inflow_outflow_ratio", "level_deviation",
        "doy_sin", "doy_cos",
    ]
    assert X.shape == (n, len(names))
    assert np.isfinite(X).all()
