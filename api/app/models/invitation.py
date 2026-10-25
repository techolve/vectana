from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field


class InvitationStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


class Invitation(SQLModel, table=True):
    """An admin-issued account invitation. Accepting it creates the user with
    the company, role and departments chosen here."""

    __tablename__ = "invitations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(max_length=255, index=True)
    display_name: str | None = Field(default=None, max_length=100)
    company_id: UUID = Field(foreign_key="companies.id", index=True, ondelete="CASCADE")
    role: str = Field(max_length=20)
    department_ids: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    primary_department_id: UUID | None = Field(default=None)
    token: str = Field(max_length=64, unique=True, index=True)
    status: str = Field(default=InvitationStatus.pending, max_length=20)
    invited_by: UUID | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    accepted_at: datetime | None = nullable_ts_field()
