# infrastructure/auth/models.py
# User and role models for authentication.
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    WATER_OPS = "WATER_OPS"
    CROP_ANALYST = "CROP_ANALYST"
    REMOTE_SENSING = "REMOTE_SENSING"
    VIEWER = "VIEWER"


class User(BaseModel):
    """Authenticated user context from JWT."""
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    roles: list[str]
    permissions: list[str]
    region_ids: list[int] = []
    is_active: bool = True


# ─── Static user store (demo) ──────────────────────────────────────────────
# In production, replace with database lookup.
DEMO_USERS = {
    "admin": {
        "id": "1",
        "username": "admin",
        "password_hash": "$demo$admin123",
        "email": "admin@ibcp.gov.pk",
        "full_name": "System Admin",
        "role": "SYSTEM_ADMIN",
        "roles": ["SYSTEM_ADMIN"],
        "permissions": ["*"],
        "region_ids": [],
        "is_active": True,
    },
    "water_ops": {
        "id": "2",
        "username": "water_ops",
        "password_hash": "$demo$water123",
        "email": "water.ops@ibcp.gov.pk",
        "full_name": "Water Operations",
        "role": "WATER_OPS",
        "roles": ["WATER_OPS"],
        "permissions": ["water:*"],
        "region_ids": [1, 2, 3],
        "is_active": True,
    },
    "crop_analyst": {
        "id": "3",
        "username": "crop_analyst",
        "password_hash": "$demo$crop123",
        "email": "crop@ibcp.gov.pk",
        "full_name": "Crop Analyst",
        "role": "CROP_ANALYST",
        "roles": ["CROP_ANALYST"],
        "permissions": ["crop:*"],
        "region_ids": [1, 2],
        "is_active": True,
    },
    "geo_analyst": {
        "id": "4",
        "username": "geo_analyst",
        "password_hash": "$demo$geo123",
        "email": "geo@ibcp.gov.pk",
        "full_name": "Geo Analyst",
        "role": "REMOTE_SENSING",
        "roles": ["REMOTE_SENSING"],
        "permissions": ["geo:*"],
        "region_ids": [1],
        "is_active": True,
    },
    "viewer": {
        "id": "5",
        "username": "viewer",
        "password_hash": "$demo$viewer123",
        "email": "viewer@ibcp.gov.pk",
        "full_name": "Read-only Viewer",
        "role": "VIEWER",
        "roles": ["VIEWER"],
        "permissions": [],
        "region_ids": [],
        "is_active": True,
    },
}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user. Returns user dict or None.
    
    Currently uses demo user store. In production, hash passwords with bcrypt
    and look up from database.
    """
    user = DEMO_USERS.get(username)
    if not user:
        return None
    # Demo mode: plain-text password check
    expected = user["password_hash"].replace("$demo$", "")
    if password != expected:
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}
