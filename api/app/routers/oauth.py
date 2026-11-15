"""OAuth 2.1 for remote MCP clients (claude.ai connectors and the like).

A client registers itself (RFC 7591), sends the user to /oauth/authorize,
the user approves on the web app's consent page, and the client swaps the
code (with PKCE) for an access token. The access token is a personal token
(vcu_), so it shows up and can be revoked under Account settings → Personal
tokens, and works anywhere a personal token does.
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import PERSONAL_PREFIX, hash_secret
from app.core.config import settings
from app.core.database import get_session
from app.i18n import request_locale
from app.models.oauth import OAuthClient, OAuthCode
from app.models.token import PersonalToken, TokenScope
from app.models.user import User
from app.routers.personal_token import DISPLAY_CHARS, signed_in_user

router = APIRouter(tags=["oauth"])

Session = Annotated[AsyncSession, Depends(get_session)]

CODE_TTL = timedelta(minutes=10)
SCOPES = ("read", "write")
MAX_REDIRECT_URIS = 10


def base_url() -> str:
    return settings.web_url.rstrip("/")


def mcp_url() -> str:
    return f"{base_url()}/mcp"


def resource_metadata_url() -> str:
    return f"{base_url()}/.well-known/oauth-protected-resource/mcp"


# --- Discovery -----------------------------------------------------------------


@router.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
async def protected_resource() -> dict[str, Any]:
    """RFC 9728: where the MCP endpoint's tokens come from."""
    return {
        "resource": mcp_url(),
        "authorization_servers": [base_url()],
        "scopes_supported": list(SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_name": settings.app_name,
    }


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
async def authorization_server() -> dict[str, Any]:
    """RFC 8414 authorization server metadata."""
    base = base_url()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/api/oauth/token",
        "registration_endpoint": f"{base}/api/oauth/register",
        "scopes_supported": list(SCOPES),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }


# --- Registration (RFC 7591) ---------------------------------------------------


def _allowed_redirect(uri: str) -> bool:
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False
    if parts.fragment or not parts.netloc:
        return False
    if parts.scheme == "https":
        return True
    # Desktop clients listen on the loopback interface.
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def _oauth_error(error: str, description: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=code)


class RegisterBody(BaseModel):
    redirect_uris: list[str] = Field(min_length=1, max_length=MAX_REDIRECT_URIS)
    client_name: str = Field(default="", max_length=200)
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = ["authorization_code"]
    response_types: list[str] = ["code"]


@router.post("/api/oauth/register", status_code=201, summary="OAuth クライアント登録")
async def register(body: RegisterBody, session: Session) -> JSONResponse:
    bad = [u for u in body.redirect_uris if len(u) > 2000 or not _allowed_redirect(u)]
    if bad:
        return _oauth_error("invalid_redirect_uri", f"Redirect URI not allowed: {bad[0]}")
    client = OAuthClient(
        client_id=secrets.token_urlsafe(24),
        client_name=body.client_name.strip(),
        redirect_uris=body.redirect_uris,
    )
    session.add(client)
    await session.commit()
    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_id_issued_at": int(client.created_at.timestamp()),
            "client_name": client.client_name,
            "redirect_uris": client.redirect_uris,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        },
        status_code=201,
    )


async def _client(client_id: str, session: AsyncSession) -> OAuthClient | None:
    return (
        await session.exec(select(OAuthClient).where(OAuthClient.client_id == client_id))
    ).first()


# --- Authorization ------------------------------------------------------------


def _with_query(uri: str, params: dict[str, str]) -> str:
    sep = "&" if urlsplit(uri).query else "?"
    return uri + sep + urlencode({k: v for k, v in params.items() if v})


@router.get("/oauth/authorize", include_in_schema=False)
async def authorize(request: Request, session: Session) -> RedirectResponse:
    """Check the request, then hand over to the web app's consent page, which
    signs the user in if needed and asks them to approve."""
    q = request.query_params
    client = await _client(q.get("client_id", ""), session)
    redirect_uri = q.get("redirect_uri", "")
    if client is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown OAuth client")
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Redirect URI not registered")
    state = q.get("state", "")
    if q.get("response_type") != "code":
        return RedirectResponse(
            _with_query(redirect_uri, {"error": "unsupported_response_type", "state": state}),
            status_code=302,
        )
    if not q.get("code_challenge") or q.get("code_challenge_method") != "S256":
        return RedirectResponse(
            _with_query(
                redirect_uri,
                {
                    "error": "invalid_request",
                    "error_description": "PKCE with S256 is required",
                    "state": state,
                },
            ),
            status_code=302,
        )
    return RedirectResponse(
        f"/{request_locale(request)}/oauth/authorize/?{request.url.query}", status_code=302
    )


class ClientInfo(BaseModel):
    client_name: str
    redirect_host: str


@router.get(
    "/api/oauth/clients/{client_id}", response_model=ClientInfo, summary="OAuth クライアント情報"
)
async def client_info(client_id: str, session: Session) -> ClientInfo:
    client = await _client(client_id, session)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown OAuth client")
    host = urlsplit(client.redirect_uris[0]).hostname or ""
    return ClientInfo(client_name=client.client_name, redirect_host=host)


class ApproveBody(BaseModel):
    client_id: str
    redirect_uri: str
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: Literal["S256"] = "S256"
    state: str = ""
    scope: Literal["read", "write"] = "read"
    approve: bool = True


class ApproveOut(BaseModel):
    redirect_to: str


@router.post("/api/oauth/authorize", response_model=ApproveOut, summary="OAuth 認可（同意）")
async def approve(
    body: ApproveBody, user: Annotated[User, Depends(signed_in_user)], session: Session
) -> ApproveOut:
    """Called by the consent page with the user's sign-in. Personal tokens
    can't approve, so a token can never mint another one."""
    client = await _client(body.client_id, session)
    if client is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown OAuth client")
    if body.redirect_uri not in client.redirect_uris:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Redirect URI not registered")
    if not body.approve:
        return ApproveOut(
            redirect_to=_with_query(
                body.redirect_uri, {"error": "access_denied", "state": body.state}
            )
        )
    code = secrets.token_urlsafe(32)
    session.add(
        OAuthCode(
            code_hash=hash_secret(code),
            client_id=client.client_id,
            user_id=user.id,
            redirect_uri=body.redirect_uri,
            code_challenge=body.code_challenge,
            scope=body.scope,
            expires_at=datetime.now(UTC) + CODE_TTL,
        )
    )
    await session.commit()
    return ApproveOut(
        redirect_to=_with_query(
            body.redirect_uri, {"code": code, "state": body.state, "iss": base_url()}
        )
    )


# --- Token ---------------------------------------------------------------------


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.post("/api/oauth/token", summary="OAuth トークン発行")
async def token(
    session: Session,
    grant_type: Annotated[str, Form()],
    code: Annotated[str, Form()] = "",
    redirect_uri: Annotated[str, Form()] = "",
    client_id: Annotated[str, Form()] = "",
    code_verifier: Annotated[str, Form()] = "",
) -> JSONResponse:
    if grant_type != "authorization_code":
        return _oauth_error("unsupported_grant_type", "Only authorization_code is supported")
    row = (
        await session.exec(select(OAuthCode).where(OAuthCode.code_hash == hash_secret(code)))
    ).first()
    if row is None:
        return _oauth_error("invalid_grant", "Unknown or used authorization code")
    # A code is good for one try, right or wrong.
    await session.delete(row)
    await session.commit()
    if row.expires_at is None or _aware(row.expires_at) <= datetime.now(UTC):
        return _oauth_error("invalid_grant", "Authorization code has expired")
    if row.client_id != client_id or row.redirect_uri != redirect_uri:
        return _oauth_error("invalid_grant", "Client or redirect URI does not match")
    if not code_verifier or not secrets.compare_digest(_s256(code_verifier), row.code_challenge):
        return _oauth_error("invalid_grant", "PKCE verification failed")
    client = await _client(client_id, session)
    user = await session.get(User, row.user_id)
    if client is None or user is None or not user.is_active:
        return _oauth_error("invalid_grant", "The client or user no longer exists")

    secret = PERSONAL_PREFIX + secrets.token_urlsafe(32)
    session.add(
        PersonalToken(
            user_id=user.id,
            name=f"{client.client_name or 'OAuth client'} (OAuth)"[:100],
            scope=TokenScope(row.scope),
            token_hash=hash_secret(secret),
            prefix=secret[:DISPLAY_CHARS],
        )
    )
    await session.commit()
    return JSONResponse(
        {"access_token": secret, "token_type": "Bearer", "scope": row.scope},
        headers={"Cache-Control": "no-store"},
    )
