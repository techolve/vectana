from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class ProjectRole(StrEnum):
    owner = "owner"  # manage settings, members, webhooks
    member = "member"  # edit packages, triage vulnerabilities
    viewer = "viewer"  # read only


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True, ondelete="RESTRICT")
    department_id: UUID | None = Field(
        default=None, foreign_key="departments.id", index=True, ondelete="SET NULL"
    )
    name: str = Field(max_length=200)
    description: str | None = Field(default=None)
    created_at: datetime = created_at_field()


class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    role: str = Field(default=ProjectRole.member, max_length=20)
    created_at: datetime = created_at_field()


class WebhookType(StrEnum):
    discord = "discord"
    slack = "slack"


class ProjectWebhook(SQLModel, table=True):
    __tablename__ = "project_webhooks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    type: str = Field(max_length=20)
    url: str = Field(max_length=1000)
    min_severity: str = Field(default="LOW", max_length=20)
    enabled: bool = Field(default=True)
    created_at: datetime = created_at_field()
