from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class CompanyType(StrEnum):
    parent = "parent"  # 親会社
    affiliate = "affiliate"  # 関連会社
    partner = "partner"  # BP（協力会社）


class Company(SQLModel, table=True):
    """A company in the group, or an external partner (BP).

    The instance itself represents one group, so there is no group table: the
    group name lives in settings.
    """

    __tablename__ = "companies"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=200, unique=True)
    type: str = Field(default=CompanyType.affiliate, max_length=20)
    created_at: datetime = created_at_field()


class Department(SQLModel, table=True):
    """A department inside a company. Departments nest via ``parent_id``."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "parent_id", "name", postgresql_nulls_not_distinct=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True, ondelete="CASCADE")
    parent_id: UUID | None = Field(
        default=None, foreign_key="departments.id", index=True, ondelete="CASCADE"
    )
    name: str = Field(max_length=100)
    created_at: datetime = created_at_field()


class UserDepartment(SQLModel, table=True):
    """Department membership. A user may belong to several departments of their
    own company (兼務); one is primary. ``is_head`` marks the department head."""

    __tablename__ = "user_departments"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True, ondelete="CASCADE")
    department_id: UUID = Field(foreign_key="departments.id", primary_key=True, ondelete="CASCADE")
    is_primary: bool = Field(default=False)
    is_head: bool = Field(default=False)
