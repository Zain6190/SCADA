# packages/backend/app/models/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import UTC, datetime

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