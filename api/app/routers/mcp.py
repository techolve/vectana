"""Remote MCP endpoint (Streamable HTTP, stateless).

The API checks the bearer token, answering 401 with a pointer to the OAuth
metadata so clients such as claude.ai can sign the user in, then passes the
request on to the MCP server process (see app.core.mcp_process), which calls
this API back with the same token.
"""

from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import mcp_process
from app.core.auth import PERSONAL_PREFIX, hash_secret
from app.core.config import settings
from app.core.database import get_session
from app.models.token import PersonalToken, TokenScope
from app.models.user import User
from app.routers.oauth import resource_metadata_url

router = APIRouter(tags=["mcp"])

Session = Annotated[AsyncSession, Depends(get_session)]

FORWARD_REQUEST = ("content-type", "accept", "accept-language", "mcp-protocol-version")
FORWARD_RESPONSE = ("content-type", "mcp-protocol-version")


def _unauthorized(error: str | None = None) -> JSONResponse:
    challenge = f'Bearer resource_metadata="{resource_metadata_url()}"'
    if error:
        challenge += f', error="{error}"'
    return JSONResponse(
        {"error": error or "unauthorized", "error_description": "Sign in to Vectana"},
        status_code=401,
        headers={"WWW-Authenticate": challenge},
    )


async def _personal_token(request: Request, session: AsyncSession) -> PersonalToken | None:
    header = request.headers.get("authorization", "")
    scheme, _, secret = header.partition(" ")
    secret = secret.strip()
    if scheme.lower() != "bearer" or not secret.startswith(PERSONAL_PREFIX):
        return None
    token = (
        await session.exec(
            select(PersonalToken).where(PersonalToken.token_hash == hash_secret(secret))
        )
    ).first()
    if token is None:
        return None
    if token.expires_at is not None:
        expires = (
            token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=UTC)
        )
        if expires <= datetime.now(UTC):
            return None
    user = await session.get(User, token.user_id)
    return token if user is not None and user.is_active else None


_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))
    return _client


@router.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def mcp(request: Request, session: Session) -> Response:
    if not request.headers.get("authorization"):
        return _unauthorized()
    token = await _personal_token(request, session)
    if token is None:
        return _unauthorized("invalid_token")
    if request.method != "POST":
        # Stateless server: no SSE stream to resume and no session to end.
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Method not allowed"}},
            status_code=405,
            headers={"Allow": "POST"},
        )
    if not mcp_process.enabled():
        return JSONResponse({"detail": "The MCP server is not enabled"}, status_code=503)

    headers = {k: v for k in FORWARD_REQUEST if (v := request.headers.get(k))}
    headers["authorization"] = request.headers["authorization"]
    if token.scope != TokenScope.write:
        headers["x-vectana-read-only"] = "1"
    try:
        upstream = await _http().post(
            f"http://127.0.0.1:{settings.mcp_port}/mcp",
            content=await request.body(),
            headers=headers,
        )
    except httpx.HTTPError:
        return JSONResponse({"detail": "The MCP server is starting; try again"}, status_code=503)
    out = {k: v for k in FORWARD_RESPONSE if (v := upstream.headers.get(k))}
    return Response(upstream.content, status_code=upstream.status_code, headers=out)
