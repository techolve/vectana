from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.organization import CompanyType
from app.models.user import UserRole


class CompanyBody(BaseModel):
    name: str
    type: CompanyType


class CompanyOut(BaseModel):
    id: UUID
    name: str
    type: str


class DepartmentBody(BaseModel):
    company_id: UUID
    name: str
    parent_id: UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None


class DepartmentOut(BaseModel):
    id: UUID
    company_id: UUID
    parent_id: UUID | None
    name: str


class UserDepartmentIn(BaseModel):
    department_id: UUID
    is_primary: bool = False
    is_head: bool = False


class UserDepartmentOut(UserDepartmentIn):
    pass


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: str
    is_active: bool
    company_id: UUID | None
    departments: list[UserDepartmentOut]


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    departments: list[UserDepartmentIn] | None = None


class UserBrief(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    company_id: UUID | None


class InvitationBody(BaseModel):
    email: EmailStr
    display_name: str | None = None
    company_id: UUID
    role: UserRole = UserRole.member
    departments: list[UserDepartmentIn] = []


class InvitationOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    company_id: UUID
    role: str
    status: str
    created_at: datetime
    expires_at: datetime
    email_sent: bool | None = None
    # Only returned right after creation, so the admin can share it if email fails.
    accept_url: str | None = None


class InvitationPreview(BaseModel):
    email: str
    display_name: str | None
    company_name: str
