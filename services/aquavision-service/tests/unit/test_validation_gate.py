from types import SimpleNamespace

from ml.models.prediction_v2 import AquaVisionPredictionModel


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.queries = 0

    def execute(self, *args, **kwargs):
        self.queries += 1
        return _FakeResult(self._rows)


def test_validation_by_lead_parses_registry_versions():
    session = _FakeSession([
        ("xgb-flood-v1.2-h7", "REJECTED"),
        ("xgb-flood-v1.2-h3", "SHADOW"),
        ("xgb-flood-v1.2-h14", "EXPERIMENTAL"),
        ("xgb-flood-v1.2-h30", "SHADOW"),
    ])
    model = AquaVisionPredictionModel(session=session)

    got = model._get_validation_by_lead(10, [3, 7, 14])

    assert got == {3: "SHADOW", 7: "REJECTED", 14: "EXPERIMENTAL"}
    assert session.queries == 1


def test_validation_by_lead_marks_missing_rows_unregistered():
    model = AquaVisionPredictionModel(session=_FakeSession([]))
    assert model._get_validation_by_lead(1, [7]) == {7: "UNREGISTERED"}


def test_validation_by_lead_without_session_is_empty():
    model = AquaVisionPredictionModel(session=None)
    assert model._get_validation_by_lead(1, [3, 7]) == {}


def test_validation_by_lead_prefers_newest_duplicate_horizon():
    session = _FakeSession([
        ("xgb-flood-v1.2-h7", "SHADOW"),
        ("xgb-flood-v1.2-h7", "REJECTED"),
    ])
    model = AquaVisionPredictionModel(session=session)
    assert model._get_validation_by_lead(2, [7]) == {7: "SHADOW"}


def test_validation_by_lead_ignores_unparseable_versions():
    session = _FakeSession([
        ("legacy-model", "SHADOW"),
        ("xgb-flood-v1.2-hx", "REJECTED"),
    ])
    model = AquaVisionPredictionModel(session=session)
    assert model._get_validation_by_lead(3, [7]) == {7: "UNREGISTERED"}
