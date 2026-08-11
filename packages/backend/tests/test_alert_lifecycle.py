"""#12 SCADA alarm lifecycle (ISA-18.2 mindset) - end-to-end tests.

Asserts against the live API:
  * acknowledgement captures responsibility but NEVER resolves the alert
  * the full canonical chain ack -> investigate -> respond -> verify -> resolve
  * verify=False sends the response back for rework (ACTION_REQUIRED)
  * require_verification=False allows a direct (procedure-allowed) clearance
  * operator CANNOT verify / resolve (separation of duties); supervisor CAN
  * viewer is denied every lifecycle action
  * illegal state-machine transitions return 409
  * out-of-scope regions are denied (403)
Each test creates a disposable alert in the operator's scope (district 10)
and cleans it up afterwards, so no live demo/operational records are touched.
"""
import datetime

from conftest import auth

from app.core.database import SessionLocal
from app.models import db as orm
from sqlalchemy import delete as sa_delete

SCOPE_REGION = 10  # Sukkur - inside operator scope (10, 11, 12)


def _create_alert(region_id=SCOPE_REGION):
    db = SessionLocal()
    try:
        alert = orm.WaterAlert(
            region_id=region_id, week_start_date="2026-08-03",
            alert_type="WAI_CRITICAL", severity="Critical", status="New",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert.id
    finally:
        db.close()


def _cleanup(alert_id):
    db = SessionLocal()
    try:
        db.execute(sa_delete(orm.WaterAlert).where(orm.WaterAlert.id == alert_id))
        db.commit()
    finally:
        db.close()


def _to_iso(dt: datetime.datetime) -> str:
    return dt.isoformat()


# --------------------------------------------------------------------------
# Acknowledge NEVER resolves
# --------------------------------------------------------------------------
def test_acknowledge_captures_responsibility_but_does_not_resolve(client, operator):
    alert_id = _create_alert()
    try:
        r = client.post(
            f"/api/v1/water/alerts/{alert_id}/acknowledge",
            headers=auth(operator),
            json={"initial_assessment": "WAI dropped sharply; verifying SCADA",
                  "estimated_response_time": _to_iso(datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)),
                  "notes": "acknowledged on shift"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ACKNOWLEDGED"
        assert body["acknowledged_at"] is not None
        assert body["acknowledged_by_user_id"] is not None
        assert body["initial_assessment"] == "WAI dropped sharply; verifying SCADA"
        assert body["resolved_at"] is None, "acknowledgement must never resolve"
    finally:
        _cleanup(alert_id)


def test_acknowledge_out_of_scope_denied(client, operator):
    alert_id = _create_alert(region_id=1)  # Punjab - outside operator scope
    try:
        r = client.post(
            f"/api/v1/water/alerts/{alert_id}/acknowledge",
            headers=auth(operator),
            json={"initial_assessment": "n/a"},
        )
        assert r.status_code == 403
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# Full lifecycle chain (operator + supervisor)
# --------------------------------------------------------------------------
def test_full_lifecycle_ack_investigate_respond_verify_resolve(client, operator, supervisor):
    alert_id = _create_alert()
    try:
        # acknowledge
        r = client.post(f"/api/v1/water/alerts/{alert_id}/acknowledge",
                        headers=auth(operator),
                        json={"initial_assessment": "drop confirmed"})
        assert r.status_code == 200 and r.json()["status"] == "ACKNOWLEDGED"

        # investigate
        r = client.post(f"/api/v1/water/alerts/{alert_id}/investigate",
                        headers=auth(operator),
                        json={"investigation_notes": "SCADA confirms sensor fault",
                              "status": None})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "INVESTIGATING"
        assert r.json()["investigation_notes"] == "SCADA confirms sensor fault"

        # respond -> awaits verification
        r = client.post(f"/api/v1/water/alerts/{alert_id}/respond",
                        headers=auth(operator),
                        json={"action_taken": "calibrated flow sensor",
                              "action_result": "WAI back in band",
                              "evidence_refs": ["logbook-192", "photo-77"],
                              "require_verification": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "WAITING_FOR_VERIFICATION"
        assert body["action_taken"] == "calibrated flow sensor"
        assert body["evidence_refs"] == ["logbook-192", "photo-77"]
        assert body["resolved_at"] is None, "no self-clearance of a critical response"

        # operator must NOT be able to verify their own response
        r = client.post(f"/api/v1/water/alerts/{alert_id}/verify",
                        headers=auth(operator), json={"verified": True})
        assert r.status_code == 403, "separation of duties: operator cannot verify"

        # supervisor verifies -> resolved
        r = client.post(f"/api/v1/water/alerts/{alert_id}/verify",
                        headers=auth(supervisor), json={"verified": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "RESOLVED"
        assert body["verified_at"] is not None
        assert body["resolved_at"] is not None
        assert body["resolved_by_user_id"] is not None
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# Verification rejection sends back for rework
# --------------------------------------------------------------------------
def test_verify_false_sends_back_for_rework(client, operator, supervisor):
    alert_id = _create_alert()
    try:
        client.post(f"/api/v1/water/alerts/{alert_id}/acknowledge",
                    headers=auth(operator), json={"initial_assessment": "x"})
        client.post(f"/api/v1/water/alerts/{alert_id}/respond",
                    headers=auth(operator),
                    json={"action_taken": "replaced valve",
                          "require_verification": True})
        r = client.post(f"/api/v1/water/alerts/{alert_id}/verify",
                        headers=auth(supervisor), json={"verified": False})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ACTION_REQUIRED"
        assert r.json()["resolved_at"] is None
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# Direct clearance when procedure allows (require_verification=False)
# --------------------------------------------------------------------------
def test_direct_clearance_without_verification(client, operator):
    alert_id = _create_alert()
    try:
        client.post(f"/api/v1/water/alerts/{alert_id}/acknowledge",
                    headers=auth(operator), json={"initial_assessment": "x"})
        r = client.post(f"/api/v1/water/alerts/{alert_id}/respond",
                        headers=auth(operator),
                        json={"action_taken": "minor adjustment",
                              "require_verification": False})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "RESPONSE_COMPLETED"
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# Escalation
# --------------------------------------------------------------------------
def test_escalate_records_authority(client, operator):
    alert_id = _create_alert()
    try:
        r = client.post(f"/api/v1/water/alerts/{alert_id}/escalate",
                        headers=auth(operator),
                        json={"escalated_to": "regional",
                              "reason": "beyond station authority"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ESCALATED"
        assert body["escalated_to"] == "regional"
        assert body["escalated_at"] is not None
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# Handover
# --------------------------------------------------------------------------
def test_handover_flags_for_next_shift(client, operator):
    alert_id = _create_alert()
    try:
        client.post(f"/api/v1/water/alerts/{alert_id}/acknowledge",
                    headers=auth(operator), json={"initial_assessment": "x"})
        r = client.post(f"/api/v1/water/alerts/{alert_id}/handover",
                        headers=auth(operator),
                        json={"notes": "pending the supervisor review"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "HANDOVER_REQUIRED"
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# Permission checks
# --------------------------------------------------------------------------
def test_viewer_denied_all_lifecycle_actions(client, viewer):
    alert_id = _create_alert()
    try:
        for path, payload in (
            (f"/api/v1/water/alerts/{alert_id}/acknowledge", {"initial_assessment": "x"}),
            (f"/api/v1/water/alerts/{alert_id}/investigate", {"investigation_notes": "x"}),
            (f"/api/v1/water/alerts/{alert_id}/respond", {"action_taken": "x"}),
            (f"/api/v1/water/alerts/{alert_id}/verify", {"verified": True}),
            (f"/api/v1/water/alerts/{alert_id}/resolve", {}),
            (f"/api/v1/water/alerts/{alert_id}/escalate", {"escalated_to": "regional"}),
            (f"/api/v1/water/alerts/{alert_id}/handover", {"notes": "x"}),
        ):
            r = client.post(path, headers=auth(viewer), json=payload) if payload else \
                client.post(path, headers=auth(viewer))
            assert r.status_code == 403, f"{path} should be 403 for viewer"
    finally:
        _cleanup(alert_id)


def test_resolve_requires_permission(client, operator):
    # Operator's role lacks AQUAVISION_RESOLVE_ALERT even though the state
    # machine would otherwise allow WAITING_FOR_VERIFICATION -> RESOLVED.
    alert_id = _create_alert()
    try:
        r = client.post(f"/api/v1/water/alerts/{alert_id}/resolve",
                        headers=auth(operator))
        assert r.status_code == 403
    finally:
        _cleanup(alert_id)


# --------------------------------------------------------------------------
# State machine legality (409)
# --------------------------------------------------------------------------
def test_illegal_transition_returns_409(client, operator, supervisor):
    alert_id = _create_alert()
    try:
        # Escalated -> Ack is not reachable; but the canonical case: an
        # ACTIVE alert cannot be verified (only WAITING_FOR_VERIFICATION may).
        r = client.post(f"/api/v1/water/alerts/{alert_id}/verify",
                        headers=auth(supervisor), json={"verified": True})
        assert r.status_code == 409, r.text
    finally:
        _cleanup(alert_id)


def test_resolve_actor_flow_legality(client, admin):
    # legacy PATCH status now flows through the state machine -> illegal
    # transition must surface as 409 rather than a silent overwrite.
    alert_id = _create_alert()
    try:
        r = client.patch(f"/api/v1/water/alerts/{alert_id}",
                         headers=auth(admin),
                         json={"status": "Resolved"})
        assert r.status_code == 409, \
            "resolving an ACTIVE alert via PATCH must be rejected (state machine)"
    finally:
        _cleanup(alert_id)


def test_read_returns_lifecycle_fields(client, operator):
    alert_id = _create_alert()
    try:
        client.post(f"/api/v1/water/alerts/{alert_id}/acknowledge",
                    headers=auth(operator), json={"initial_assessment": "drop"})
        r = client.get(f"/api/v1/water/alerts/{alert_id}", headers=auth(operator))
        assert r.status_code == 200, r.text
        body = r.json()
        for field in ("acknowledged_by_user_id", "initial_assessment",
                      "investigation_notes", "action_taken", "action_result",
                      "evidence_refs", "escalated_to", "verified_by_user_id",
                      "resolved_by_user_id"):
            assert field in body, f"lifecycle field {field} missing from alert response"
        assert body["initial_assessment"] == "drop"
    finally:
        _cleanup(alert_id)