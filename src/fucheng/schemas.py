from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Diet = Literal["unset", "omnivore", "vegetarian"]


class PublicMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    distinguishing_note: str | None
    level: int
    diet: Diet


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class AuthResponse(BaseModel):
    username: str
    csrf_token: str


class MemberInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    distinguishing_note: str | None = Field(default=None, max_length=100)
    legacy_number: str | None = Field(default=None, max_length=50)
    level: int = Field(ge=1, le=10)
    diet: Diet = "omnivore"
    is_active: bool = True

    @field_validator("name", "distinguishing_note", "legacy_number")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str | None) -> str:
        if not value:
            raise ValueError("姓名不可空白")
        return value


class MemberCreate(MemberInput):
    pass


class MemberUpdate(MemberInput):
    version: int = Field(ge=1)


class AdminMember(MemberInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    created_at: datetime
    updated_at: datetime


class AuditEntry(BaseModel):
    id: str
    action: str
    changes: dict[str, dict[str, object]]
    admin_username: str
    created_at: datetime
