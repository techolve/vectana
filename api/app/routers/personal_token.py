"""Personal tokens: act as the signed-in user, for scripts and AI clients
(the Vectana MCP server). Managing them needs a real sign-in, so a token can
never mint a broader one."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import PERSONAL_PREFIX, bearer, get_current_user, hash_secret
from app.core.database import get_session
from app.models.token import PersonalToken
from app.models.user import User
from app.schemas.auth import PersonalTokenBody, PersonalTokenCreated, PersonalTokenOut

router = APIRouter(prefix="/api/auth/tokens", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]

DISPLAY_CHARS = 12  # "vcu_" + 8


async def signed_in_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if credentials.credentials.startswith(PERSONAL_PREFIX):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Personal tokens cannot manage tokens")
    return user


SignedIn = Annotated[User, Depends(signed_in_user)]


def _out(t: PersonalToken) -> PersonalTokenOut:
    return PersonalTokenOut(
        id=t.id,
        name=t.name,
        scope=t.scope,
        prefix=t.prefix,
        expires_at=t.expires_at,
        last_used_at=t.last_used_at,
        created_at=t.created_at,
    )


@router.get("", response_model=list[PersonalTokenOut], summary="個人用トークン一覧")
async def list_tokens(user: SignedIn, session: Session) -> list[PersonalTokenOut]:
    rows = (
        await session.exec(
            select(PersonalToken)
            .where(PersonalToken.user_id == user.id)
            .order_by(col(PersonalToken.created_at))
        )
    ).all()
    return [_out(t) for t in rows]


@router.post(
    "",
    response_model=PersonalTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="個人用トークンの発行",
)
async def create_token(
    body: PersonalTokenBody, user: SignedIn, session: Session
) -> PersonalTokenCreated:
    secret = PERSONAL_PREFIX + secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    )
    token = PersonalToken(
        user_id=user.id,
        name=body.name,
        scope=body.scope,
        token_hash=hash_secret(secret),
        prefix=secret[:DISPLAY_CHARS],
        expires_at=expires_at,
    )
    session.add(token)
    await session.commit()
    return PersonalTokenCreated(**_out(token).model_dump(), token=secret)


@router.delete(
    "/{token_id}", status_code=status.HTTP_204_NO_CONTENT, summary="個人用トークンの失効"
)
async def revoke_token(token_id: UUID, user: SignedIn, session: Session) -> None:
    token = await session.get(PersonalToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    await session.delete(token)
    await session.commit()
