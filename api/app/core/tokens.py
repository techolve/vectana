"""Project API tokens for CI.

A token looks like ``vct_<43 url-safe chars>``. Only its SHA-256 is stored:
the secret has 256 bits of entropy, so a slow hash adds nothing.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, Level, accessible_project, load_actor
from app.core.auth import bearer, user_from_access_token
from app.core.database import get_session
from app.models.project import Project
from app.models.token import ApiToken

TOKEN_PREFIX = "vct_"
DISPLAY_CHARS = 12  # "vct_" + 8


def generate() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    # SQLite hands timestamps back naive; Postgres keeps the zone.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def token_from_secret(secret: str, session: AsyncSession) -> ApiToken:
    token = (
        await session.exec(select(ApiToken).where(ApiToken.token_hash == hash_token(secret)))
    ).first()
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")
    now = datetime.now(UTC)
    if token.expires_at is not None and _aware(token.expires_at) <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API token has expired")
    token.last_used_at = now
    session.add(token)
    await session.commit()
    return token


@dataclass
class Caller:
    """Either a signed-in user or a project API token."""

    actor: Actor | None = None
    token: ApiToken | None = None


async def get_caller(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Caller:
    secret = credentials.credentials
    if secret.startswith(TOKEN_PREFIX):
        return Caller(token=await token_from_secret(secret, session))
    user = await user_from_access_token(secret, session)
    return Caller(actor=await load_actor(user, session))


async def caller_project(
    project_id: UUID, caller: Caller, session: AsyncSession, level: Level
) -> Project:
    """The project, if the caller may act on it at ``level``. A token only
    ever reaches its own project, and is treated as write access."""
    if caller.actor is not None:
        return await accessible_project(project_id, caller.actor, session, level)
    assert caller.token is not None
    project = await session.get(Project, project_id)
    if project is None or caller.token.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if level > Level.write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
    return project
