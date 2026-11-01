"""OpenID Connect client: discovery, code exchange and ID token verification."""

import asyncio
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.core.config import settings

_DISCOVERY_TTL_SECONDS = 3600


class OidcError(Exception):
    pass


@dataclass
class Provider:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


_provider: tuple[float, Provider] | None = None
_jwks: dict[str, jwt.PyJWKClient] = {}


def oidc_enabled() -> bool:
    return bool(settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret)


def redirect_uri() -> str:
    return f"{settings.web_url.rstrip('/')}/api/auth/oidc/callback"


async def provider() -> Provider:
    global _provider
    if _provider and time.monotonic() - _provider[0] < _DISCOVERY_TTL_SECONDS:
        return _provider[1]
    url = f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise OidcError(f"Discovery failed: {response.status_code}")
    doc = response.json()
    p = Provider(
        issuer=doc["issuer"],
        authorization_endpoint=doc["authorization_endpoint"],
        token_endpoint=doc["token_endpoint"],
        jwks_uri=doc["jwks_uri"],
    )
    _provider = (time.monotonic(), p)
    return p


def pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge)."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def exchange_code(code: str, verifier: str) -> str:
    """Trade the authorization code for an ID token."""
    p = await provider()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            p.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
                "code_verifier": verifier,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200:
        raise OidcError(f"Token exchange failed: {response.status_code}")
    id_token = response.json().get("id_token")
    if not id_token:
        raise OidcError("No id_token in token response")
    return str(id_token)


async def verify_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    p = await provider()
    client = _jwks.setdefault(p.jwks_uri, jwt.PyJWKClient(p.jwks_uri))
    try:
        # PyJWKClient fetches over blocking HTTP.
        key = await asyncio.to_thread(client.get_signing_key_from_jwt, id_token)
        claims: dict[str, Any] = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_client_id,
            issuer=p.issuer,
        )
    except jwt.PyJWTError as exc:
        raise OidcError(f"Invalid id_token: {exc}") from exc
    if claims.get("nonce") != nonce:
        raise OidcError("Nonce mismatch")
    return claims
