"""Unit tests for ModelRegistry status transitions (Phase 3)."""
from unittest.mock import MagicMock

from ml.validation.model_registry import ModelRegistry, ModelStatus


class FakeVersion:
    def __init__(self, status: str):
        self.status = status
        self.version = "xgb-flood-v1.2-h7"
        self.approved_at = None
        self.approved_by = None
        self.notes = None


def _registry(status):
    session = MagicMock()
    session.get.return_value = None if status is None else FakeVersion(status)
    return ModelRegistry(session), session


def test_shadow_to_approved_stamps_approval():
    reg, session = _registry("SHADOW")
    assert reg.transition(1, ModelStatus.APPROVED, approved_by="alice") is True
    mv = session.get.return_value
    assert mv.status == "APPROVED"
    assert mv.approved_by == "alice"
    assert mv.approved_at is not None
    session.commit.assert_called_once()


def test_experimental_cannot_approve_directly():
    reg, session = _registry("EXPERIMENTAL")
    assert reg.transition(1, ModelStatus.APPROVED, approved_by="alice") is False
    assert session.get.return_value.status == "EXPERIMENTAL"
    session.commit.assert_not_called()


def test_approved_to_production():
    reg, session = _registry("APPROVED")
    assert reg.transition(1, ModelStatus.PRODUCTION) is True
    assert session.get.return_value.status == "PRODUCTION"


def test_rejected_is_terminal():
    for target in (ModelStatus.APPROVED, ModelStatus.PRODUCTION, ModelStatus.SHADOW):
        reg, session = _registry("REJECTED")
        assert reg.transition(1, target) is False
        assert session.get.return_value.status == "REJECTED"


def test_missing_version_returns_false():
    reg, session = _registry(None)
    assert reg.transition(999, ModelStatus.APPROVED) is False
    session.commit.assert_not_called()


def test_valid_transitions_cover_every_status():
    for status in ModelStatus:
        assert status in ModelRegistry.VALID_TRANSITIONS


def test_experimental_can_reject_but_not_produce():
    allowed = ModelRegistry.VALID_TRANSITIONS[ModelStatus.EXPERIMENTAL]
    assert ModelStatus.REJECTED in allowed
    assert ModelStatus.APPROVED not in allowed
    assert ModelStatus.PRODUCTION not in allowed
