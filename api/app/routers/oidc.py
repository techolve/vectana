"""SSO sign-in with OpenID Connect (authorization code flow with PKCE).

The browser leaves the web app for /api/auth/oidc/login and comes back to
/{locale}/login/sso/ with the app's own tokens in the URL fragment, so they
never reach a server log. Only users who already exist (by email) can sign in.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import create_access_token, create_refresh_token
from app.core.config import settings
from app.core.database import get_session
from app.core.oidc import (
    OidcError,
    exchange_code,
    oidc_enabled,
    pkce_pair,
    provider,
    redirect_uri,
    verify_id_token,
)
from app.models.user import User

router = APIRouter(prefix="/api/auth/oidc", tags=["auth"])
logger = logging.getLogger(__name__)

Session = Annotated[AsyncSession, Depends(get_session)]

_COOKIE = "vectana_oidc"
_COOKIE_PATH = "/api/auth/oidc"
_FLOW_MINUTES = 10
_LOCALES = ("ja", "en")


class OidcConfig(BaseModel):
    enabled: bool
    provider_name: str


def _web(locale: str, path: str) -> str:
    return f"{settings.web_url.rstrip('/')}/{locale}/{path}"


def _fail(locale: str, reason: str) -> RedirectResponse:
    response = RedirectResponse(_web(locale, "login/?" + urlencode({"sso_error": reason})))
    response.delete_cookie(_COOKIE, path=_COOKIE_PATH)
    return response


@router.get("/config", response_model=OidcConfig, summary="SSO の設定")
async def config() -> OidcConfig:
    return OidcConfig(enabled=oidc_enabled(), provider_name=settings.oidc_provider_name)


@router.get("/login", summary="SSO ログインを開始", response_class=RedirectResponse)
async def login(locale: str = "ja") -> RedirectResponse:
    if not oidc_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SSO is not configured")
    locale = locale if locale in _LOCALES else "ja"
    try:
        p = await provider()
    except OidcError:
        logger.exception("OIDC discovery failed")
        return _fail(locale, "provider")
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": redirect_uri(),
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    # The flow state rides in a short-lived signed cookie instead of the database.
    flow = jwt.encode(
        {
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "locale": locale,
            "exp": datetime.now(UTC) + timedelta(minutes=_FLOW_MINUTES),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    response = RedirectResponse(f"{p.authorization_endpoint}?{query}")
    response.set_cookie(
        _COOKIE,
        flow,
        max_age=_FLOW_MINUTES * 60,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.web_url.startswith("https://"),
        samesite="lax",
    )
    return response


@router.get("/callback", summary="SSO ログインの戻り先", response_class=RedirectResponse)
async def callback(
    request: Request,
    session: Session,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    try:
        flow = jwt.decode(
            request.cookies.get(_COOKIE, ""), settings.secret_key, algorithms=[settings.algorithm]
        )
    except jwt.PyJWTError:
        return _fail("ja", "expired")
    locale = flow.get("locale", "ja")
    if error or not code:
        return _fail(locale, "denied")
    if not state or not secrets.compare_digest(state, flow.get("state", "")):
        return _fail(locale, "expired")

    try:
        id_token = await exchange_code(code, flow["verifier"])
        claims = await verify_id_token(id_token, flow["nonce"])
    except OidcError:
        logger.exception("OIDC sign-in failed")
        return _fail(locale, "provider")

    email = str(claims.get("email") or "").lower()
    if not email or claims.get("email_verified") is False:
        return _fail(locale, "no_email")
    user = (await session.exec(select(User).where(User.email == email))).first()
    if not user or not user.is_active:
        return _fail(locale, "not_registered")

    fragment = urlencode(
        {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
        }
    )
    response = RedirectResponse(_web(locale, f"login/sso/#{fragment}"))
    response.delete_cookie(_COOKIE, path=_COOKIE_PATH)
    return response
