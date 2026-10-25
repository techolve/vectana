from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class UserRole(StrEnum):
    group_admin = "group_admin"  # グループ全体の管理者
    company_admin = "company_admin"  # 自社の管理者
    member = "member"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True)
    hashed_password: str = Field(max_length=255)
    display_name: str | None = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    role: str = Field(default=UserRole.member, max_length=20)
    # Every user belongs to exactly one company. Only a bootstrap group admin
    # may have none.
    company_id: UUID | None = Field(
        default=None, foreign_key="companies.id", index=True, ondelete="RESTRICT"
    )
    # UI and email language ("ja" / "en").
    locale: str = Field(default="ja", max_length=5)
    created_at: datetime = created_at_field()
