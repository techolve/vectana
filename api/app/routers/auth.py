from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, get_actor
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.core.config import settings
from app.core.database import get_session
from app.core.security import hash_password, verify_password
from app.models.invitation import Invitation, InvitationStatus
from app.models.notification import NotificationPref
from app.models.organization import Company, UserDepartment
from app.models.package import Severity
from app.models.user import User
from app.schemas.auth import (
    AcceptInvitation,
    LocaleBody,
    LoginRequest,
    MeResponse,
    NotificationPrefsBody,
    PasswordChange,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.org import InvitationPreview

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Used when the email is unknown so response time doesn't reveal it.
_DUMMY_HASH = "$2b$12$KixGMfOoVlgq0kO5ioNFoOdFlK1.bYX3KwbXHf8r4lP87OHlqEgfy"

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def _tokens(user_id: UUID) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/login", response_model=TokenResponse, summary="ログイン")
async def login(body: LoginRequest, session: Session) -> TokenResponse:
    email = body.email.lower()
    user = (await session.exec(select(User).where(User.email == email))).first()
    if not user:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    return _tokens(user.id)


@router.post("/refresh", response_model=TokenResponse, summary="トークン更新")
async def refresh(body: RefreshRequest, session: Session) -> TokenResponse:
    payload = decode_refresh_token(body.refresh_token)
    user = await session.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    return _tokens(user.id)


@router.get("/me", response_model=MeResponse, summary="ログイン中ユーザー")
async def me(actor: CurrentActor, session: Session) -> MeResponse:
    user = actor.user
    company = await session.get(Company, user.company_id) if user.company_id else None
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        company_id=user.company_id,
        company_name=company.name if company else None,
        is_partner=actor.is_partner,
        can_manage_org=actor.can_manage_org,
        managed_department_ids=sorted(actor.managed_department_ids, key=str),
        group_name=settings.group_name,
        locale=user.locale,
    )


@router.put("/locale", status_code=status.HTTP_204_NO_CONTENT, summary="表示言語の保存")
async def set_locale(body: LocaleBody, actor: CurrentActor, session: Session) -> None:
    """Saved language is used for emails; the web app also switches to it on login."""
    actor.user.locale = body.locale
    session.add(actor.user)
    await session.commit()


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, summary="パスワード変更")
async def change_password(body: PasswordChange, actor: CurrentActor, session: Session) -> None:
    user = actor.user
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    user.hashed_password = hash_password(body.new_password)
    session.add(user)
    await session.commit()


@router.get("/notifications", response_model=NotificationPrefsBody, summary="通知設定")
async def get_prefs(actor: CurrentActor, session: Session) -> NotificationPrefsBody:
    pref = await session.get(NotificationPref, actor.user.id)
    if pref is None:
        return NotificationPrefsBody(email_enabled=True, min_severity=Severity.LOW)
    return NotificationPrefsBody(email_enabled=pref.email_enabled, min_severity=pref.min_severity)


@router.put("/notifications", response_model=NotificationPrefsBody, summary="通知設定の更新")
async def put_prefs(
    body: NotificationPrefsBody, actor: CurrentActor, session: Session
) -> NotificationPrefsBody:
    if body.min_severity not in Severity.__members__:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown severity")
    pref = await session.get(NotificationPref, actor.user.id) or NotificationPref(
        user_id=actor.user.id
    )
    pref.email_enabled = body.email_enabled
    pref.min_severity = body.min_severity
    session.add(pref)
    await session.commit()
    return body


async def _pending_invitation(token: str, session: AsyncSession) -> Invitation:
    invitation = (await session.exec(select(Invitation).where(Invitation.token == token))).first()
    if invitation is None or invitation.status != InvitationStatus.pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:  # SQLite drops tzinfo
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "Invitation has expired")
    return invitation


@router.get("/invitations/{token}", response_model=InvitationPreview, summary="招待内容の確認")
async def preview_invitation(token: str, session: Session) -> InvitationPreview:
    invitation = await _pending_invitation(token, session)
    company = await session.get(Company, invitation.company_id)
    return InvitationPreview(
        locale=invitation.locale,
        email=invitation.email,
        display_name=invitation.display_name,
        company_name=company.name if company else "",
    )


@router.post("/invitations/accept", response_model=TokenResponse, summary="招待の受諾")
async def accept_invitation(body: AcceptInvitation, session: Session) -> TokenResponse:
    invitation = await _pending_invitation(body.token, session)
    existing = (await session.exec(select(User).where(User.email == invitation.email))).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=invitation.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name or invitation.display_name,
        role=invitation.role,
        company_id=invitation.company_id,
        locale=invitation.locale,
    )
    session.add(user)
    await session.flush()
    for entry in invitation.department_ids:
        session.add(
            UserDepartment(
                user_id=user.id,
                department_id=UUID(entry["department_id"]),
                is_primary=bool(entry.get("is_primary")),
                is_head=bool(entry.get("is_head")),
            )
        )
    invitation.status = InvitationStatus.accepted
    invitation.accepted_at = datetime.now(UTC)
    session.add(invitation)
    await session.commit()
    return _tokens(user.id)
