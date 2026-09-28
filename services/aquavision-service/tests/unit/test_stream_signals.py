# tests/unit/test_stream_signals.py
# Change-detection logic behind GET /water/stream (SSE refresh hints).
from presentation.http.routers.stream import SIGNAL_EVENTS, changed_events

BASE = {
    "observations": "13952|2026-09-27 19:29:12+00",
    "alerts": "5|2026-09-27 10:00:00+00|-",
    "ot_commands": "2|2026-09-27 12:00:00+00",
    "ffd": "40|2026-09-27 06:00:00+00",
}


def test_no_change_yields_no_events():
    assert changed_events(BASE, dict(BASE)) == set()


def test_observations_change_refreshes_overview_and_territory():
    curr = dict(BASE, observations="13953|2026-09-27 20:00:00+00")
    assert changed_events(BASE, curr) == {"overview", "territory"}


def test_alert_change_refreshes_overview_only():
    curr = dict(BASE, alerts="6|2026-09-27 20:00:00+00|-")
    assert changed_events(BASE, curr) == {"overview"}


def test_ot_command_change_refreshes_territory_only():
    curr = dict(BASE, ot_commands="3|2026-09-27 20:00:00+00")
    assert changed_events(BASE, curr) == {"territory"}


def test_ffd_change_refreshes_overview_only():
    curr = dict(BASE, ffd="41|2026-09-27 20:00:00+00")
    assert changed_events(BASE, curr) == {"overview"}


def test_unreadable_signal_equal_to_unreadable_is_silent():
    prev = dict(BASE, ffd=None)
    curr = dict(BASE, ffd=None)
    assert changed_events(prev, curr) == set()


def test_recovered_signal_emits_once():
    prev = dict(BASE, ot_commands=None)
    curr = dict(BASE, ot_commands="3|2026-09-27 20:00:00+00")
    assert changed_events(prev, curr) == {"territory"}


def test_multiple_signals_merge_event_kinds():
    curr = dict(
        BASE,
        observations="13953|2026-09-27 20:00:00+00",
        ot_commands="3|2026-09-27 20:00:00+00",
    )
    assert changed_events(BASE, curr) == {"overview", "territory"}


def test_signal_event_coverage_matches_client_queries():
    kinds = {k for kinds in SIGNAL_EVENTS.values() for k in kinds}
    assert kinds == {"overview", "territory"}
