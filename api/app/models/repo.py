"""Links between a project and a GitHub / GitLab repository.

A link imports the repository's lockfiles and SBOMs (on push to the default
branch, and once a day), and keeps issues and milestones in step with the
project's tasks and sprints in both directions."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field


class RepoProvider(StrEnum):
    github = "github"
    gitlab = "gitlab"


class RepoLink(SQLModel, table=True):
    __tablename__ = "repo_links"
    __table_args__ = (UniqueConstraint("project_id", "provider", "base_url", "repo"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    provider: str = Field(max_length=10)  # RepoProvider
    # API root: https://api.github.com, https://gitlab.com or a self-hosted GitLab.
    base_url: str = Field(max_length=300)
    repo: str = Field(max_length=300)  # owner/name, or group/subgroup/project
    # Access token, encrypted with the server's SECRET_KEY.
    token_encrypted: str = Field(max_length=2000)
    # Verifies webhook deliveries (GitHub HMAC signature / GitLab token).
    webhook_secret: str = Field(max_length=100)
    webhook_id: str | None = Field(default=None, max_length=50)  # when we registered it
    default_branch: str = Field(default="main", max_length=200)
    # Keep issues <-> tasks and milestones <-> sprints in step.
    sync_issues: bool = Field(default=True)
    # Open an issue for each security task created automatically.
    security_issues: bool = Field(default=True)
    # Glob patterns of paths to import from ("" / none = everywhere).
    import_paths: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    last_import_at: datetime | None = nullable_ts_field()
    last_import_sha: str | None = Field(default=None, max_length=64)
    last_event_at: datetime | None = nullable_ts_field()
    last_error: str | None = Field(default=None, max_length=1000)
    last_error_at: datetime | None = nullable_ts_field()
    created_by: UUID | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
