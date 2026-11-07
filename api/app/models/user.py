from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class UserRole(StrEnum):
    """Global roles. A user holds any number of them; with none, a user only
    sees the projects they are assigned to (or, as a department head, those
    of their departments). New roles can be appended here."""

    group_admin = "group_admin"  # グループ全体の管理者
    company_admin = "company_admin"  # 自社の管理者
    sales = "sales"  # 営業: customers and estimates of their own company
    accounting = "accounting"  # 経理: billing and costs of their own company
    pmo = "pmo"  # PMO: every delivered project across the group, read only


ADMIN_ROLES = frozenset({UserRole.group_admin, UserRole.company_admin})


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True)
    hashed_password: str = Field(max_length=255)
    display_name: str | None = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    roles: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # Cost per person-day (人日単価, yen). Seen only by admins, sales and
    # accounting of the same company; used to cost estimates.
    unit_cost: int | None = Field(default=None)
    # Every user belongs to exactly one company. Only a bootstrap group admin
    # may have none.
    company_id: UUID | None = Field(
        default=None, foreign_key="companies.id", index=True, ondelete="RESTRICT"
    )
    # UI and email language ("ja" / "en").
    locale: str = Field(default="ja", max_length=5)
    created_at: datetime = created_at_field()

    def has_role(self, role: UserRole) -> bool:
        return role in (self.roles or [])
