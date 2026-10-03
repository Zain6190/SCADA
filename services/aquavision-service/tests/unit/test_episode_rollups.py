"""Unit tests for episode closer (UC-8 rollups)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from infrastructure.thresholds.engine import close_resolved_episodes


def _result(rows):
    m = MagicMock()
    m.scalars.return_value.all.return_value = rows
    return m


def _episode(eid=1):
    return SimpleNamespace(
        id=eid,
        episode_key=f"asset{eid}_flood_rising_2026-10-03",
        status="OPEN",
        resolved_at=None,
    )


def test_closes_episode_when_all_members_terminal():
    ep = _episode()
    member = SimpleNamespace(id=10, status="RESOLVED")
    session = MagicMock()
    session.execute.side_effect = [_result([ep]), _result([member])]

    closed = close_resolved_episodes(session)

    assert closed == 1
    assert ep.status == "RESOLVED"
    assert ep.resolved_at is not None
    session.commit.assert_called_once()


def test_keeps_episode_open_while_members_open():
    ep = _episode()
    members = [SimpleNamespace(id=10, status="RESOLVED"), SimpleNamespace(id=11, status="NEW")]
    session = MagicMock()
    session.execute.side_effect = [_result([ep]), _result(members)]

    closed = close_resolved_episodes(session)

    assert closed == 0
    assert ep.status == "OPEN"
    assert ep.resolved_at is None
    session.commit.assert_not_called()


def test_episode_without_members_left_open():
    ep = _episode()
    session = MagicMock()
    session.execute.side_effect = [_result([ep]), _result([])]

    closed = close_resolved_episodes(session)

    assert closed == 0
    assert ep.status == "OPEN"
    session.commit.assert_not_called()


def test_false_invalid_counts_as_terminal():
    ep = _episode()
    member = SimpleNamespace(id=10, status="FALSE_OR_INVALID_DATA")
    session = MagicMock()
    session.execute.side_effect = [_result([ep]), _result([member])]

    assert close_resolved_episodes(session) == 1
    assert ep.status == "RESOLVED"


def test_mixed_episodes_close_independently():
    ep1, ep2 = _episode(1), _episode(2)
    session = MagicMock()
    session.execute.side_effect = [
        _result([ep1, ep2]),
        _result([SimpleNamespace(id=10, status="RESOLVED")]),
        _result([SimpleNamespace(id=11, status="ACKNOWLEDGED")]),
    ]

    closed = close_resolved_episodes(session)

    assert closed == 1
    assert ep1.status == "RESOLVED"
    assert ep2.status == "OPEN"
