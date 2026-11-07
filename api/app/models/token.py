from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field


class ApiToken(SQLModel, table=True):
    """A project-scoped token for CI. It may only import dependency files and
    trigger a scan for its own project. Only the SHA-256 of the secret is kept."""

    __tablename__ = "api_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=100)
    token_hash: str = Field(max_length=64, unique=True, index=True)
    # The first characters of the token, so people can tell tokens apart.
    prefix: str = Field(max_length=16)
    created_by: UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="SET NULL"
    )
    expires_at: datetime | None = nullable_ts_field()
    last_used_at: datetime | None = nullable_ts_field()
    created_at: datetime = created_at_field()


class TokenScope(StrEnum):
    read = "read"  # GET only
    write = "write"  # everything the user may do, except managing personal tokens


class PersonalToken(SQLModel, table=True):
    """A token that acts as its user, for scripts and AI clients (MCP).
    It has the user's permissions, or only read access with the read scope.
    Only the SHA-256 of the secret is kept."""

    __tablename__ = "personal_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=100)
    scope: str = Field(default=TokenScope.read, max_length=10)
    token_hash: str = Field(max_length=64, unique=True, index=True)
    prefix: str = Field(max_length=16)
    expires_at: datetime | None = nullable_ts_field()
    last_used_at: datetime | None = nullable_ts_field()
    created_at: datetime = created_at_field()
