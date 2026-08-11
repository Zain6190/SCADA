"""Supervisor delegation tests (MANAGE_OPERATORS, Phase 4).

End-to-end against the live API:
  * /auth/operator-roles exposes ONLY delegable roles (never admin/supervisor)
  * a supervisor can create an operator scoped to their own region
  * privileged roles are rejected on delegated create
  * a DISTRICT-scoped supervisor is forbidden from creating outside their region
  * team list reflects the supervisor's operators; PENDING -> ACTIVE approval
  * users without MANAGE_OPERATORS are rejected with 403
"""
import uuid

from conftest import auth


def _unique_email(prefix="op"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@ibcp.gov.pk"


def _first_district(client, token) -> dict:
    regions = client.get("/api/v1/water/regions?region_type=district", headers=auth(token)).json()
    assert regions, "no districts exist in DB"
    return regions[0]


# --------------------------------------------------------------------------
# operator-roles surface
# --------------------------------------------------------------------------
def test_supervisor_can_list_operator_roles(client, supervisor):
    r = client.get("/api/v1/auth/operator-roles", headers=auth(supervisor))
    assert r.status_code == 200
    names = {role["name"] for role in r.json()}
    assert "field_officer" in names
    assert "admin" not in names
    assert "water_supervisor" not in names
    assert "system_admin" not in names


def test_viewer_cannot_list_operator_roles(client, viewer):
    r = client.get("/api/v1/auth/operator-roles", headers=auth(viewer))
    assert r.status_code == 403


# --------------------------------------------------------------------------
# supervisor create / list / approve (NATIONAL supervisor)
# --------------------------------------------------------------------------
def test_supervisor_creates_operator_in_district(client, supervisor):
    district = _first_district(client, supervisor)
    email = _unique_email()
    r = client.post(
        "/api/v1/auth/operators",
        headers=auth(supervisor),
        json={
            "full_name": "Riaz Ahmed",
            "email": email,
            "password": "riaz12345",
            "role": "field_officer",
            "access_status": "ACTIVE",
            "region_id": district["id"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()["user"]
    assert body["role"] == "field_officer"
    assert body["region_scope"]["scope_type"] == "DISTRICT"
    assert body["region_ids"] == [district["id"]]


def test_supervisor_cannot_delegate_privileged_role(client, supervisor):
    district = _first_district(client, supervisor)
    r = client.post(
        "/api/v1/auth/operators",
        headers=auth(supervisor),
        json={
            "full_name": "Bad Attempt",
            "email": _unique_email(),
            "password": "pw12345678",
            "role": "water_supervisor",
            "access_status": "ACTIVE",
            "region_id": district["id"],
        },
    )
    assert r.status_code == 400


def test_supervisor_rejects_unknown_region(client, supervisor):
    r = client.post(
        "/api/v1/auth/operators",
        headers=auth(supervisor),
        json={
            "full_name": "Noman Malik",
            "email": _unique_email(),
            "password": "pw12345678",
            "role": "field_officer",
            "access_status": "ACTIVE",
            "region_id": 999999,
        },
    )
    assert r.status_code == 400


def test_supervisor_sees_created_operator_in_team(client, supervisor):
    district = _first_district(client, supervisor)
    email = _unique_email("team")
    r = client.post(
        "/api/v1/auth/operators",
        headers=auth(supervisor),
        json={
            "full_name": "Team Member",
            "email": email,
            "password": "tm1234567",
            "role": "viewer",
            "access_status": "PENDING",
            "region_id": district["id"],
        },
    )
    assert r.status_code == 201, r.text
    uid = r.json()["user"]["id"]

    team = client.get("/api/v1/auth/operators", headers=auth(supervisor)).json()
    assert any(u["id"] == uid and u["access_status"] == "PENDING" for u in team)

    approve = client.patch(
        f"/api/v1/auth/operators/{uid}",
        headers=auth(supervisor),
        json={"access_status": "ACTIVE"},
    )
    assert approve.status_code == 200
    assert approve.json()["user"]["access_status"] == "ACTIVE"


def test_viewer_cannot_create_in_district(client, viewer):
    r = client.post(
        "/api/v1/auth/operators",
        headers=auth(viewer),
        json={
            "full_name": "Spoof",
            "email": _unique_email(),
            "password": "pw12345678",
            "role": "field_officer",
            "access_status": "ACTIVE",
            "region_id": 1,
        },
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------
# DISTRICT-scoped supervisor cannot create outside their own region
# --------------------------------------------------------------------------
def test_district_supervisor_cannot_create_out_of_scope(client, admin):
    districts = client.get("/api/v1/water/regions?region_type=district", headers=auth(admin)).json()
    assert len(districts) >= 2, "need >=2 districts for the out-of-scope test"
    d1, d2 = districts[0], districts[1]

    email = _unique_email("sup")
    r = client.post(
        "/api/v1/auth/admin/users",
        headers=auth(admin),
        json={
            "full_name": "District Supervisor",
            "email": email,
            "password": "sup123456",
            "role": "water_supervisor",
            "access_status": "ACTIVE",
            "scope": {"scope_type": "DISTRICT", "region_id": d1["id"]},
        },
    )
    assert r.status_code == 201, r.text

    login = client.post("/api/v1/auth/token", data={"username": email, "password": "sup123456"})
    assert login.status_code == 200
    sup_token = login.json()["access_token"]

    inside = client.post(
        "/api/v1/auth/operators",
        headers=auth(sup_token),
        json={
            "full_name": "In Scope",
            "email": _unique_email("in"),
            "password": "pw12345678",
            "role": "field_officer",
            "access_status": "ACTIVE",
            "region_id": d1["id"],
        },
    )
    assert inside.status_code == 201, inside.text

    outside = client.post(
        "/api/v1/auth/operators",
        headers=auth(sup_token),
        json={
            "full_name": "Out of Scope",
            "email": _unique_email("out"),
            "password": "pw12345678",
            "role": "field_officer",
            "access_status": "ACTIVE",
            "region_id": d2["id"],
        },
    )
    assert outside.status_code == 403