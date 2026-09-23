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
