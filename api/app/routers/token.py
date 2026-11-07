"""Project API tokens (for CI). Managing them needs manage access."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import tokens
from app.core.access import Actor, Level, accessible_project, get_actor
from app.core.database import get_session
from app.models.token import ApiToken
from app.models.user import User
from app.schemas.project import TokenBody, TokenCreated, TokenOut

router = APIRouter(prefix="/api", tags=["projects"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def _out(t: ApiToken, email: str | None) -> TokenOut:
    return TokenOut(
        id=t.id,
        name=t.name,
        prefix=t.prefix,
        created_by_email=email,
        expires_at=t.expires_at,
        last_used_at=t.last_used_at,
        created_at=t.created_at,
    )


@router.get(
    "/projects/{project_id}/tokens", response_model=list[TokenOut], summary="APIトークン一覧"
)
async def list_tokens(project_id: UUID, actor: CurrentActor, session: Session) -> list[TokenOut]:
    await accessible_project(project_id, actor, session, Level.manage)
    rows = (
        await session.exec(
            select(ApiToken, User.email)
            .join(User, col(User.id) == col(ApiToken.created_by), isouter=True)
            .where(ApiToken.project_id == project_id)
            .order_by(col(ApiToken.created_at))
        )
    ).all()
    return [_out(t, email) for t, email in rows]


@router.post(
    "/projects/{project_id}/tokens",
    response_model=TokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="APIトークンの発行",
)
async def create_token(
    project_id: UUID, body: TokenBody, actor: CurrentActor, session: Session
) -> TokenCreated:
    await accessible_project(project_id, actor, session, Level.manage)
    secret = tokens.generate()
    expires_at = (
        datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    )
    token = ApiToken(
        project_id=project_id,
        name=body.name,
        token_hash=tokens.hash_token(secret),
        prefix=secret[: tokens.DISPLAY_CHARS],
        created_by=actor.user.id,
        expires_at=expires_at,
    )
    session.add(token)
    await session.commit()
    return TokenCreated(**_out(token, actor.user.email).model_dump(), token=secret)


@router.delete(
    "/projects/{project_id}/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="APIトークンの失効",
)
async def revoke_token(
    project_id: UUID, token_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.manage)
    token = await session.get(ApiToken, token_id)
    if token is None or token.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    await session.delete(token)
    await session.commit()
