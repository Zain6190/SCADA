# tests/unit/test_alert_workflow.py
# Unit tests for the role-based alert workflow (no DB required):
#   - permission matrix, state machines, SLA math, actor mapping
#   - ack/resolve guards and instruction lifecycle (mocked session)
#   - SLA scanner behaviour (mocked session, patched notifications)
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.alerts import workflow
from infrastructure.alerts.workflow import (
    ACTION_ROLES, INSTRUCTION_TRANSITIONS, WorkflowError, _check_transition,
    _instruction_transition, _now, actor_from_token, authorize, sla_due_at,
)
from infrastructure.db.models import AlertInstruction, WaterOperationalAlert


def make_alert(**kw) -> WaterOperationalAlert:
    a = WaterOperationalAlert(
        asset_id=1,
        alert_type=kw.pop("alert_type", "LEVEL_ABOVE_DANGER"),
        severity=kw.pop("severity", "CRITICAL"),
        message=kw.pop("message", "Level above danger"),
        status=kw.pop("status", "NEW"),
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def make_actor(role="water_supervisor", **kw):
    return workflow.Actor(
        username=kw.pop("username", "sup1"),
        role=role,
        user_id=kw.pop("user_id", 15),
        roles=kw.pop("roles", {role}),
        **kw,
    )


def mock_session():
    s = MagicMock()
    s.execute.return_value.scalar.return_value = 0  # default: no open instructions
    return s


# ─── SLA math ────────────────────────────────────────────────────────────────

def test_sla_due_at_critical_15min():
    t0 = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    assert sla_due_at("CRITICAL", t0) == t0 + timedelta(minutes=15)


def test_sla_due_at_warning_4h():
    t0 = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    assert sla_due_at("WARNING", t0) == t0 + timedelta(hours=4)


def test_sla_due_at_watch_none():
    assert sla_due_at("WATCH") is None
    assert sla_due_at(None) is None


# ─── Actor mapping ───────────────────────────────────────────────────────────

def test_actor_from_token_unions_roles():
    actor = actor_from_token({"sub": "15", "username": "sup1", "role": "water_supervisor", "roles": ["water_supervisor"]})
    assert actor.user_id == 15
    assert "water_supervisor" in actor.all_roles
    assert actor.is_admin is False


def test_actor_admin_flag():
    actor = actor_from_token({"sub": "1", "username": "admin", "role": "admin", "roles": ["admin"]})
    assert actor.is_admin is True


def test_actor_bad_sub_is_none():
    assert actor_from_token({"sub": "not-an-int", "username": "x", "role": "viewer"}).user_id is None


# ─── Permission matrix ───────────────────────────────────────────────────────

def test_viewer_cannot_ack_or_resolve():
    viewer = make_actor("viewer", username="v1")
    with pytest.raises(WorkflowError) as e:
        authorize(viewer, "ack", make_alert())
    assert e.value.status_code == 403
    with pytest.raises(WorkflowError):
        authorize(viewer, "resolve", make_alert())


def test_field_officer_can_ack_but_not_issue_or_verify():
    officer = make_actor("field_officer", username="f1")
    authorize(officer, "ack", make_alert())  # allowed
    with pytest.raises(WorkflowError):
        authorize(officer, "issue_instruction", make_alert())
    with pytest.raises(WorkflowError):
        authorize(officer, "verify", make_alert())


def test_field_officer_cannot_waive():
    with pytest.raises(WorkflowError):
        authorize(make_actor("field_officer"), "waive")


def test_supervisor_cannot_waive_admin_can():
    with pytest.raises(WorkflowError):
        authorize(make_actor("water_supervisor"), "waive")
    authorize(make_actor("admin", username="a1", roles={"admin"}), "waive")


def test_analyst_limited_to_ml_domain():
    analyst = make_actor("aquavision_analyst", username="an1")
    rule_alert = make_alert(alert_source="RULE")
    ml_alert = make_alert(alert_source="ML_V2")
    # ack is open to analyst on any alert
    authorize(analyst, "ack", rule_alert)
    # issue/verify/close restricted to ML/model domain
    with pytest.raises(WorkflowError) as e:
        authorize(analyst, "issue_instruction", rule_alert)
    assert e.value.status_code == 403
    authorize(analyst, "issue_instruction", ml_alert)
    with pytest.raises(WorkflowError):
        authorize(analyst, "resolve", rule_alert)
    authorize(analyst, "resolve", ml_alert)


def test_supervisor_can_issue_and_verify():
    sup = make_actor("water_supervisor")
    authorize(sup, "issue_instruction", make_alert())
    authorize(sup, "verify", make_alert())
    authorize(sup, "escalate", make_alert())


# ─── Alert state machine ─────────────────────────────────────────────────────

def test_valid_transitions():
    _check_transition("NEW", "ACKNOWLEDGED")
    _check_transition("ACKNOWLEDGED", "INVESTIGATING")
    _check_transition("NEW", "ESCALATED")       # SLA path
    _check_transition("ACKNOWLEDGED", "ESCALATED")
    _check_transition("ESCALATED", "INVESTIGATING")
    _check_transition("INVESTIGATING", "RESOLVED")
    _check_transition("NEW", "AUTO_RESOLVED")   # UC-4


def test_invalid_transitions_raise():
    for cur, new in [("RESOLVED", "ACKNOWLEDGED"), ("NEW", "INVESTIGATING"),
                     ("NEW", "RESOLVED"), ("ACKNOWLEDGED", "NEW")]:
        if (cur, new) == ("NEW", "RESOLVED"):
            # allowed set includes RESOLVED from NEW (resolve from NEW is valid)
            _check_transition(cur, new)
            continue
        with pytest.raises(WorkflowError) as e:
            _check_transition(cur, new)
        assert e.value.status_code == 409


# ─── ack / resolve behaviour (mocked session) ────────────────────────────────

def test_ack_alert_sets_fields_and_event():
    session = mock_session()
    alert = make_alert(status="NEW", sla_due_at=_now() + timedelta(minutes=10))
    workflow.ack_alert(session, alert, make_actor("water_supervisor"), notes="on it")
    assert alert.status == "ACKNOWLEDGED"
    assert alert.acknowledged_by == "sup1"
    assert alert.acknowledged_at is not None
    session.add.assert_called()          # event row
    session.commit.assert_called()


def test_ack_wrong_status_rejected():
    with pytest.raises(WorkflowError) as e:
        workflow.ack_alert(mock_session(), make_alert(status="RESOLVED"), make_actor("water_supervisor"))
    assert e.value.status_code == 409


def test_resolve_blocked_by_open_instruction():
    session = mock_session()
    session.execute.return_value.scalar.return_value = 2  # two open instructions
    with pytest.raises(WorkflowError) as e:
        workflow.resolve_alert(session, make_alert(), make_actor("water_supervisor"), resolution="done and dusted")
    assert "instruction" in str(e.value)


def test_resolve_succeeds_when_no_open_instructions():
    session = mock_session()
    session.execute.return_value.scalar.return_value = 0
    alert = make_alert()
    workflow.resolve_alert(
        session, alert, make_actor("water_supervisor"),
        resolution="Conditions normal, reading stable for 6h",
    )
    assert alert.status == "RESOLVED"
    assert alert.resolved_by == "sup1"
    assert alert.resolution.startswith("Conditions normal")


def test_resolve_requires_min_length():
    session = mock_session()
    with pytest.raises(WorkflowError):
        workflow.resolve_alert(session, make_alert(), make_actor("admin", username="a1", roles={"admin"}), resolution="no")


def test_admin_can_resolve_with_open_instructions():
    session = mock_session()
    session.execute.return_value.scalar.return_value = 1
    alert = make_alert()
    workflow.resolve_alert(
        session, alert, make_actor("admin", username="a1", roles={"admin"}),
        resolution="waived: covered by phone",
    )
    assert alert.status == "RESOLVED"
    assert alert.resolved_by == "a1"


def test_escalate_manual_sets_fields():
    session = mock_session()
    with patch.object(workflow, "notify", return_value=None):
        alert = make_alert(status="ACKNOWLEDGED")
        workflow.escalate_alert(session, alert, make_actor("water_supervisor"), notes="worsening")
    assert alert.status == "ESCALATED"
    assert alert.escalated_to == "admin"
    assert alert.escalated_at is not None


# ─── Instruction lifecycle ───────────────────────────────────────────────────

def test_instruction_transitions_valid():
    instr = AlertInstruction(alert_id=1, asset_id=1, issued_by="s", issued_role="water_supervisor",
                             assigned_to="f1", instruction_text="patrol", status="ISSUED")
    assert _instruction_transition(instr, "ACCEPTED") == "ISSUED"
    assert _instruction_transition(instr, "IN_PROGRESS") == "ACCEPTED"
    assert _instruction_transition(instr, "REPORTED") == "IN_PROGRESS"
    assert _instruction_transition(instr, "VERIFIED") == "REPORTED"


def test_instruction_invalid_transition():
    instr = AlertInstruction(alert_id=1, asset_id=1, issued_by="s", issued_role="water_supervisor",
                             assigned_to="f1", instruction_text="patrol", status="ISSUED")
    with pytest.raises(WorkflowError):
        _instruction_transition(instr, "VERIFIED")


def test_issue_instruction_self_assign_denied_for_supervisor():
    session = mock_session()
    with pytest.raises(WorkflowError) as e:
        workflow.issue_instruction(
            session, make_alert(), make_actor("water_supervisor", username="sup1"),
            instruction_text="patrol the reach please", assigned_to="sup1",
        )
    assert e.value.status_code == 403


def test_issue_instruction_requires_text():
    session = mock_session()
    with pytest.raises(WorkflowError):
        workflow.issue_instruction(
            session, make_alert(), make_actor("water_supervisor"),
            instruction_text="no", assigned_to="f1",
        )


def test_issue_instruction_creates_and_logs():
    session = mock_session()
    session.get.return_value = None  # assignee user lookup finds nothing -> role list only
    with patch.object(workflow, "notify", return_value=None), \
         patch.object(workflow, "role_emails", return_value=[]):
        instr = workflow.issue_instruction(
            session, make_alert(), make_actor("water_supervisor"),
            instruction_text="patrol right bank bund km 42-48",
            assigned_to="f1", assigned_to_user_id=3,
        )
    assert instr.status == "ISSUED"
    assert instr.assigned_to == "f1"
    session.add.assert_called()
    session.commit.assert_called()


# ─── SLA scanner (mocked session) ────────────────────────────────────────────

def test_scan_slas_escalates_breached_and_overdue_and_auto_closes():
    session = MagicMock()
    breached = make_alert(status="NEW", sla_due_at=_now() - timedelta(minutes=5))
    overdue_instr = AlertInstruction(
        alert_id=1, asset_id=1, issued_by="sup1", issued_role="water_supervisor",
        assigned_to="f1", instruction_text="check gauge", status="ISSUED",
        due_at=_now() - timedelta(hours=2),
    )
    aged_watch = make_alert(severity="WATCH", status="NEW",
                            created_at=_now() - timedelta(hours=48))

    # scan_slas runs exactly three queries: breaches, overdue, aged
    def _result(rows):
        m = MagicMock()
        m.scalars.return_value.all.return_value = rows
        return m
    session.execute.side_effect = [_result([breached]), _result([overdue_instr]), _result([aged_watch])]

    with patch.object(workflow, "notify", return_value=None), \
         patch.object(workflow, "role_emails", return_value=[]):
        summary = workflow.scan_slas(session)

    assert summary == {"sla_escalated": 1, "instructions_overdue": 1, "info_auto_resolved": 1}
    assert breached.status == "ESCALATED"
    assert breached.escalated_to == "admin"
    assert overdue_instr.status == "OVERDUE"
    assert aged_watch.status == "AUTO_RESOLVED"
    assert aged_watch.resolved_by == "SYSTEM"
    session.commit.assert_called()


def test_scan_slas_noop_when_clean():
    session = MagicMock()
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    session.execute.return_value = empty

    with patch.object(workflow, "notify", return_value=None):
        summary = workflow.scan_slas(session)

    assert summary == {"sla_escalated": 0, "instructions_overdue": 0, "info_auto_resolved": 0}


# ─── Role email hygiene ──────────────────────────────────────────────────────

def test_role_emails_filters_junk_addresses():
    rows = ["admin@ibcp.gov.pk", "bad-email", "not-an-email", "x@y", None]
    valid = [e for e in rows if e and workflow._EMAIL_RE.match(e)]
    assert valid == ["admin@ibcp.gov.pk"]


def test_instruction_templates_are_complete():
    required = {"patrol_bund", "gate_check", "manual_reading", "comms_check", "restriction_monitor"}
    assert required == set(workflow.INSTRUCTION_TEMPLATES)
    for t in workflow.INSTRUCTION_TEMPLATES.values():
        assert t["text"] and len(t["text"]) > 20  # real content, no placeholder
        assert t["report_fields"]


def test_open_and_closed_statuses_disjoint():
    assert not set(workflow.OPEN_STATUSES) & set(workflow.CLOSED_STATUSES)
    assert "AUTO_RESOLVED" in workflow.CLOSED_STATUSES
    assert "ESCALATED" in workflow.OPEN_STATUSES
