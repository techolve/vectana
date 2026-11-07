import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.models.token import PersonalToken, TokenScope
from app.models.user import User

bearer = HTTPBearer()

# Personal tokens act as their user: "vcu_" + 43 url-safe chars.
PERSONAL_PREFIX = "vcu_"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def create_access_token(user_id: UUID) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(user_id: UUID) -> str:
    """Create a long-lived JWT refresh token."""
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT, raising 401 on any failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return _decode_token(token, "access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    return _decode_token(token, "refresh")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """FastAPI dependency: resolve a Bearer token (session JWT or personal
    token) to a User model instance."""
    return await user_from_bearer(credentials.credentials, session, request.method)


async def user_from_bearer(secret: str, session: AsyncSession, method: str) -> User:
    if secret.startswith(PERSONAL_PREFIX):
        return await user_from_personal_token(secret, session, method)
    return await user_from_access_token(secret, session)


def _active(user: User | None) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


async def user_from_access_token(token: str, session: AsyncSession) -> User:
    payload = decode_access_token(token)
    return _active(await session.get(User, UUID(payload["sub"])))


def hash_secret(secret: str) -> str:
    # The secrets have 256 bits of entropy, so a slow hash adds nothing.
    return hashlib.sha256(secret.encode()).hexdigest()


async def user_from_personal_token(secret: str, session: AsyncSession, method: str) -> User:
    token = (
        await session.exec(
            select(PersonalToken).where(PersonalToken.token_hash == hash_secret(secret))
        )
    ).first()
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")
    now = datetime.now(UTC)
    expires_at = token.expires_at
    if expires_at is not None and expires_at.tzinfo is None:  # SQLite drops tzinfo
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at is not None and expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API token has expired")
    if token.scope != TokenScope.write and method.upper() not in SAFE_METHODS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This token is read-only")
    user = _active(await session.get(User, token.user_id))
    token.last_used_at = now
    session.add(token)
    await session.commit()
    return user
