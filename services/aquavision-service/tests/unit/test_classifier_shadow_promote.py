"""Classifier shadow->promote workflow: walk-forward validation, registry
report keying, daily outcome scoring, and the REJECTED serving gate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest


def _make_df(n=420, status_mode="episodic"):
    t = np.arange(n)
    if status_mode == "episodic":
        status = np.where((t % 60) < 20, "HIGH", "NORMAL")
        rng = np.random.RandomState(42)
        inflow = 1000.0 + (status == "HIGH") * 800.0 + rng.normal(0, 25, n)
    elif status_mode == "all_high":
        status = np.full(n, "HIGH")
        inflow = np.full(n, 1800.0)
    elif status_mode == "constant":
        status = None
        inflow = np.full(n, 1500.0)
    else:
        raise ValueError(status_mode)

    data = {
        "observed_at": pd.date_range("2025-01-01", periods=n, freq="D"),
        "inflow_cusecs": inflow,
        "outflow_cusecs": inflow * 0.9,
        "water_level_ft": inflow / 100.0,
        "discharge_cusecs": inflow * 0.95,
    }
    if status is not None:
        data["flood_status"] = status
    return pd.DataFrame(data)


class TestWalkForwardClassifier:
    def test_separable_series_reaches_shadow(self):
        from scripts.validate_all_models import walk_forward_classifier

        metrics = walk_forward_classifier(1, _make_df())

        assert "error" not in metrics
        assert metrics["n_folds"] >= 3
        assert metrics["flood_events"] > 0
        assert 0.0 <= metrics["auc"] <= 1.0
        assert metrics["auc"] > 0.7
        assert metrics["brier"] >= 0.0
        assert metrics["baseline_brier"] >= 0.0
        assert 0 <= metrics["score"] <= 100
        assert len(metrics["fold_details"]) == metrics["n_folds"]
        assert metrics["recommendation"] == "SHADOW"

    def test_small_frame_rejected(self):
        from scripts.validate_all_models import walk_forward_classifier

        metrics = walk_forward_classifier(1, _make_df(n=50))
        assert metrics["error"].startswith("insufficient_data")

    def test_no_flood_labels_rejected(self):
        from scripts.validate_all_models import walk_forward_classifier

        metrics = walk_forward_classifier(1, _make_df(status_mode="constant"))
        assert metrics["error"].startswith("no_positive_labels")

    def test_all_flood_labels_rejected(self):
        from scripts.validate_all_models import walk_forward_classifier

        metrics = walk_forward_classifier(1, _make_df(status_mode="all_high"))
        assert metrics["error"].startswith("no_negative_labels")


class TestBuildLatestReports:
    def test_keys_by_model_type_and_newest_wins(self):
        from scripts.register_models import build_latest_reports

        new = SimpleNamespace(model_type="flood_predictor", asset_id=1, horizon=7, id=2)
        old = SimpleNamespace(model_type="flood_predictor", asset_id=1, horizon=7, id=1)
        clf = SimpleNamespace(model_type="flood_classifier", asset_id=1, horizon=7, id=3)

        latest = build_latest_reports([new, old, clf])

        assert set(latest) == {("flood_predictor", 1, 7), ("flood_classifier", 1, 7)}
        assert latest[("flood_predictor", 1, 7)] is new
        assert latest[("flood_classifier", 1, 7)] is clf


class _ScalarRes:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _ScriptedSession:
    def __init__(self, scalars):
        self._scalars = list(scalars)
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append(str(query))
        return _ScalarRes(self._scalars.pop(0))


class TestFloodOutcome:
    def test_ffd_high_is_flood(self):
        from scripts.compute_accuracy import _flood_outcome

        session = _ScriptedSession(["HIGH"])
        assert _flood_outcome(session, 1, datetime.now(timezone.utc)) == 1
        assert "water_ffd_observations" in session.queries[0]

    def test_ffd_moderate_is_not_flood(self):
        from scripts.compute_accuracy import _flood_outcome

        session = _ScriptedSession(["MODERATE"])
        assert _flood_outcome(session, 1, datetime.now(timezone.utc)) == 0

    def test_fallback_uses_trailing_p90(self):
        from scripts.compute_accuracy import _flood_outcome

        target = datetime(2026, 9, 1, tzinfo=timezone.utc)
        session = _ScriptedSession([None, 1000.0, 1500.0])
        assert _flood_outcome(session, 1, target) == 1
        assert "percentile_cont" in session.queries[1]
        assert "data_origin = 'REAL'" in session.queries[1]

        session = _ScriptedSession([None, 1000.0, 900.0])
        assert _flood_outcome(session, 1, target) == 0

    def test_fallback_without_data_is_unknown(self):
        from scripts.compute_accuracy import _flood_outcome

        target = datetime(2026, 9, 1, tzinfo=timezone.utc)
        session = _ScriptedSession([None, None, None])
        assert _flood_outcome(session, 1, target) is None


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._one

    def scalar(self):
        return None


class TestComputeAccuracyClassifier:
    def _pred(self, needs_reg, needs_clf, prob=0.8):
        now = datetime.now(timezone.utc)
        return {
            "id": 1, "asset_id": 1,
            "generated_at": now - timedelta(days=7),
            "target_time": now - timedelta(hours=1),
            "predicted_level_ft": 10.0, "predicted_inflow": 5000.0,
            "predicted_outflow": None, "predicted_discharge": None,
            "flood_probability": prob,
            "model_version": "xgb_1_7d",
            "needs_reg": needs_reg, "needs_clf": needs_clf,
        }

    def _run(self, pred, scalar_results, actual_row=None):
        from scripts.compute_accuracy import compute_accuracy

        session = MagicMock()
        inserts = []
        scalars = iter(scalar_results)

        def _execute(query, params=None):
            sql = str(query)
            if "water_asset_forecasts" in sql:
                return _FakeResult(rows=[pred])
            if "water_ffd_observations" in sql:
                return _ScalarRes(next(scalars))
            if "percentile_cont" in sql:
                return _ScalarRes(next(scalars))
            if "SELECT inflow_cusecs FROM" in sql:
                return _ScalarRes(next(scalars))
            if "SELECT water_level_ft" in sql:
                return _FakeResult(one=actual_row)
            if "INSERT" in sql:
                inserts.append(params)
                return _FakeResult()
            return _FakeResult()

        session.execute.side_effect = _execute
        return compute_accuracy(session, dry_run=False), session, inserts

    def test_classifier_row_scored_without_regression(self):
        pred = self._pred(needs_reg=False, needs_clf=True)
        results, session, inserts = self._run(pred, ["HIGH"])

        assert results == {
            "matched": 0, "errors": 0, "skipped": 0,
            "clf_scored": 1, "clf_skipped": 0,
        }
        assert len(inserts) == 1
        assert inserts[0]["model_version"] == "flood_classifier_h7"
        assert inserts[0]["predicted_value"] == 0.8
        assert inserts[0]["actual_value"] == 1.0
        assert inserts[0]["error_pct"] == pytest.approx(20.0)
        session.commit.assert_called_once()

    def test_unknown_outcome_skips_without_insert(self):
        pred = self._pred(needs_reg=False, needs_clf=True)
        results, session, inserts = self._run(pred, [None, None, None])

        assert results["clf_skipped"] == 1
        assert results["clf_scored"] == 0
        assert inserts == []
        session.commit.assert_not_called()

    def test_both_branches_score_on_same_row(self):
        pred = self._pred(needs_reg=True, needs_clf=True, prob=0.6)
        actual_row = {
            "water_level_ft": None, "inflow_cusecs": 4000.0,
            "outflow_cusecs": None, "discharge_cusecs": None,
            "observed_at": datetime.now(timezone.utc), "data_origin": "REAL",
        }
        results, session, inserts = self._run(
            pred, ["HIGH"], actual_row=actual_row
        )

        assert results["clf_scored"] == 1
        assert results["matched"] == 1
        assert len(inserts) == 2
        versions = {p["model_version"] for p in inserts}
        assert versions == {"flood_classifier_h7", "xgb_1_7d"}
        session.commit.assert_called_once()


class TestRejectedServingGate:
    def test_rejected_classifier_never_serves(self):
        from ml.models.prediction_v2 import AquaVisionPredictionModel

        session = MagicMock()
        session.execute.return_value = _ScalarRes("REJECTED")
        model = AquaVisionPredictionModel(session=session)

        assert model._get_flood_probability(1) is None
        assert session.execute.call_count == 1

    def test_active_status_passes_gate(self, monkeypatch):
        from ml.models import flood_classifier as fc_module
        from ml.models.prediction_v2 import AquaVisionPredictionModel

        monkeypatch.setattr(Path, "exists", lambda self: True)
        monkeypatch.setattr(fc_module, "FloodClassifier", MagicMock())
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarRes("SHADOW"),
            _FakeResult(rows=[]),
        ]
        model = AquaVisionPredictionModel(session=session)

        assert model._get_flood_probability(1) is None
        assert session.execute.call_count == 2
