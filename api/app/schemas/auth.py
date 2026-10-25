from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


def _check_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: str
    company_id: UUID | None
    company_name: str | None
    is_partner: bool
    can_manage_org: bool
    managed_department_ids: list[UUID]
    group_name: str
    locale: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strength(cls, v: str) -> str:
        return _check_password(v)


class NotificationPrefsBody(BaseModel):
    email_enabled: bool
    min_severity: str


class AcceptInvitation(BaseModel):
    token: str
    password: str
    display_name: str | None = None

    @field_validator("password")
    @classmethod
    def strength(cls, v: str) -> str:
        return _check_password(v)


class LocaleBody(BaseModel):
    locale: Literal["ja", "en"]
