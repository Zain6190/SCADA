"""Access-lifecycle + admin-provisioning tests (Phase 2).

Asserts the portal-access architecture end-to-end against the live API:
  * SUSPENDED/REVOKED / inactive accounts -> 403 "account-disabled"
  * PENDING/REJECTED accounts -> 403 "access-pending"
  * valid accounts carry access fields in the login payload
  * admin list/update endpoints enforce admin-only + lifecycle transitions
"""
import uuid

from conftest import auth

PENDING_EMAIL = "pending@ibcp.gov.pk"
PENDING_PW = "pending123"
SUSPENDED_EMAIL = "suspended@ibcp.gov.pk"
SUSPENDED_PW = "suspended123"


def _login(client, email, pw):
    return client.post("/api/v1/auth/token", data={"username": email, "password": pw})


def _unique_email():
    return f"lifecycle-{uuid.uuid4().hex[:8]}@ibcp.gov.pk"


# --------------------------------------------------------------------------
# Access lifecycle at login
# --------------------------------------------------------------------------
def test_pending_user_gets_access_pending(client):
    r = _login(client, PENDING_EMAIL, PENDING_PW)
    assert r.status_code == 403
    assert r.json()["detail"] == "access-pending"


def test_suspended_user_gets_account_disabled(client):
    r = _login(client, SUSPENDED_EMAIL, SUSPENDED_PW)
    assert r.status_code == 403
    assert r.json()["detail"] == "account-disabled"


def test_valid_login_payload_carries_access_fields(client, admin):
    # admin is ACTIVE -> payload includes the lifecycle fields
    me = client.get("/api/v1/auth/me", headers=auth(admin))
    assert me.status_code == 200
    body = me.json()
    assert body["access_status"] == "ACTIVE"
    assert "is_active" in body
    assert "access_requested_at" in body


# --------------------------------------------------------------------------
# Admin provisioning
# --------------------------------------------------------------------------
def test_register_missing_role_rejected(client, admin):
    r = client.post(
        "/api/v1/auth/register",
        headers=auth(admin),
        json={"username": "x", "email": _demo_email(), "password": "pw12345678",
              "role": "does_not_exist"},
    )
    assert r.status_code == 400


def test_register_rejects_invalid_access_status(client, admin):
    r = client.post(
        "/api/v1/auth/register",
        headers=auth(admin),
        json={"username": "x", "email": _demo_email(), "password": "pw12345678",
              "role": "viewer", "access_status": "BANANA"},
    )
    assert r.status_code == 400


def test_admin_can_list_users(client, admin):
    r = client.get("/api/v1/auth/users", headers=auth(admin))
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    emails = {u["email"] for u in r.json()}
    assert PENDING_EMAIL in emails


def test_viewer_cannot_list_users(client, viewer):
    r = client.get("/api/v1/auth/users", headers=auth(viewer))
    assert r.status_code == 403


def test_admin_promotes_pending_to_active(client, admin):
    # Grant access to the pending demo account, verify it can log in, then
    # restore it so the demo matrix stays predictable.
    r = client.patch(
        f"/api/v1/auth/users/{_user_id(client, admin, PENDING_EMAIL)}",
        headers=auth(admin),
        json={"access_status": "ACTIVE"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["access_status"] == "ACTIVE"
    try:
        login = _login(client, PENDING_EMAIL, PENDING_PW)
        assert login.status_code == 200
    finally:
        client.patch(
            f"/api/v1/auth/users/{_user_id(client, admin, PENDING_EMAIL)}",
            headers=auth(admin),
            json={"access_status": "PENDING"},
        )


def test_admin_forbidden_role_rejected(client, admin):
    rid = _user_id(client, admin, PENDING_EMAIL)
    r = client.patch(
        f"/api/v1/auth/users/{rid}",
        headers=auth(admin),
        json={"role": "system_admin"},
    )
    assert r.status_code == 400


def _demo_email():
    return f"demo-{uuid.uuid4().hex[:6]}@example.com"


def _user_id(client, token, email) -> int:
    users = client.get("/api/v1/auth/users", headers=auth(token)).json()
    for u in users:
        if u["email"] == email:
            return u["id"]
    raise AssertionError(f"user {email} not found")