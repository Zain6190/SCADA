# infrastructure/auth/schemas.py
# Auth endpoint schemas shared by the user-administration endpoints.
import re
from typing import Optional

from pydantic import BaseModel, Field

_PASSWORD_MIN = 8
_ACCESS_STATUSES = {"ACTIVE", "APPROVED", "PENDING", "SUSPENDED", "REVOKED", "REJECTED"}


def _validate_password(password: str) -> str:
    """Enforce minimum password strength."""
    if len(password) < _PASSWORD_MIN:
        raise ValueError(f"Password must be at least {_PASSWORD_MIN} characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    return password


class GeoScope(BaseModel):
    """Geographic scope for a user."""
    scope_type: str = Field(..., pattern="^(NATIONAL|PROVINCE|DISTRICT|ASSET)$")
    region_id: Optional[int] = None
    asset_id: Optional[int] = None
    expires_at: Optional[str] = None


class AdminCreateUserRequest(BaseModel):
    """POST /auth/admin/users — atomic user provisioning with scope & assets."""
    full_name: str = Field(..., min_length=1, max_length=128)
    email: str
    password: str = Field(..., min_length=_PASSWORD_MIN)
    role: str = Field(default="viewer", max_length=64)
    access_status: str = Field(default="ACTIVE")
    scope: Optional[GeoScope] = None
    asset_ids: Optional[list[int]] = None


class SupervisorCreateOperatorRequest(BaseModel):
    """POST /auth/operators — supervisor creates a delegated operator."""
    full_name: str = Field(..., min_length=1, max_length=128)
    email: str
    password: str = Field(..., min_length=_PASSWORD_MIN)
    role: str = Field(default="field_officer", max_length=64)
    access_status: str = Field(default="ACTIVE")
    region_id: int = Field(..., gt=0)
    expires_at: Optional[str] = None


class UserUpdateRequest(BaseModel):
    """PATCH /auth/users/{user_id} — admin updates a user."""
    role: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None
    access_status: Optional[str] = None
    scope: Optional[GeoScope] = None


class OperatorUpdateRequest(BaseModel):
    """PATCH /auth/operators/{user_id} — supervisor updates an operator."""
    role: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None
    access_status: Optional[str] = None
