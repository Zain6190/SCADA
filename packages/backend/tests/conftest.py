import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app

USERS = {
    "admin": ("admin@ibcp.gov.pk", "admin123"),
    "operator": ("operator@ibcp.gov.pk", "operator123"),
    "viewer": ("viewer@ibcp.gov.pk", "viewer123"),
    "st4": ("st4@ibcp.gov.pk", "st4pass"),
    "supervisor": ("supervisor@ibcp.gov.pk", "supervisor123"),
}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin")


@pytest.fixture(scope="session")
def operator(client):
    return login(client, "operator")


@pytest.fixture(scope="session")
def viewer(client):
    return login(client, "viewer")


@pytest.fixture(scope="session")
def st4(client):
    return login(client, "st4")


@pytest.fixture(scope="session")
def supervisor(client):
    return login(client, "supervisor")


def login(client, key: str) -> str:
    email, pw = USERS[key]
    r = client.post("/api/v1/auth/token", data={"username": email, "password": pw})
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}