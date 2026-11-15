from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field


class OAuthClient(SQLModel, table=True):
    """An AI client registered by OAuth dynamic client registration (RFC 7591),
    such as a claude.ai connector. Only public clients (PKCE, no secret)."""

    __tablename__ = "oauth_clients"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    client_id: str = Field(max_length=64, unique=True, index=True)
    client_name: str = Field(default="", max_length=200)
    redirect_uris: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = created_at_field()


class OAuthCode(SQLModel, table=True):
    """A one-time authorization code, exchanged for a personal token at the
    token endpoint. Only the SHA-256 of the code is kept."""

    __tablename__ = "oauth_codes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code_hash: str = Field(max_length=64, unique=True, index=True)
    client_id: str = Field(max_length=64)
    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    redirect_uri: str = Field(max_length=2000)
    code_challenge: str = Field(max_length=128)
    scope: str = Field(max_length=10)
    expires_at: datetime | None = nullable_ts_field()
    created_at: datetime = created_at_field()
