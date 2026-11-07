from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    roles: list[str]
    company_id: UUID | None
    company_name: str | None
    is_partner: bool
    can_manage_org: bool
    can_sell: bool  # create customers and estimates
    can_see_customers: bool
    can_see_invoices: bool  # the billing page (accounting and admins)
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


class PersonalTokenBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # read: GET only. write: everything the user may do.
    scope: Literal["read", "write"] = "read"
    # None = never expires.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class PersonalTokenOut(BaseModel):
    id: UUID
    name: str
    scope: str
    prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class PersonalTokenCreated(PersonalTokenOut):
    # The secret. Shown once: only its hash is stored.
    token: str
