# packages/backend/app/models/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import UTC, datetime
import re


class User(BaseModel):
    id: Optional[str] = None
    username: str
    email: EmailStr
    full_name: str
    hashed_password: str
    role: str  # admin, user, viewer
    team: Optional[str] = None  # geovision, flood, soil
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str
    role: str = "user"
    team: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: str
    team: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Auth endpoint schemas (replace raw dict payloads with validation)
# ---------------------------------------------------------------------------

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


class RegisterRequest(BaseModel):
    """POST /auth/register — admin creates a single user."""
    username: str = Field(..., min_length=2, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=_PASSWORD_MIN)
    full_name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(default="viewer", max_length=64)
    access_status: str = Field(default="ACTIVE")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "jdoe",
                "email": "jdoe@example.com",
                "password": "SecurePass1",
                "full_name": "John Doe",
                "role": "viewer",
                "access_status": "ACTIVE",
            }
        }


class AdminCreateUserRequest(BaseModel):
    """POST /auth/admin/users — atomic user provisioning with scope & assets."""
    full_name: str = Field(..., min_length=1, max_length=128)
    email: EmailStr
    password: str = Field(..., min_length=_PASSWORD_MIN)
    role: str = Field(default="viewer", max_length=64)
    access_status: str = Field(default="ACTIVE")
    scope: Optional[GeoScope] = None
    asset_ids: Optional[list[int]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Jane Smith",
                "email": "jane@example.com",
                "password": "SecurePass1",
                "role": "aquavision_analyst",
                "access_status": "ACTIVE",
                "scope": {"scope_type": "NATIONAL"},
            }
        }


class SupervisorCreateOperatorRequest(BaseModel):
    """POST /auth/operators — supervisor creates a delegated operator."""
    full_name: str = Field(..., min_length=1, max_length=128)
    email: EmailStr
    password: str = Field(..., min_length=_PASSWORD_MIN)
    role: str = Field(default="field_officer", max_length=64)
    access_status: str = Field(default="ACTIVE")
    region_id: int = Field(..., gt=0)
    expires_at: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Ali Khan",
                "email": "ali@example.com",
                "password": "SecurePass1",
                "role": "field_officer",
                "access_status": "ACTIVE",
                "region_id": 1,
            }
        }


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