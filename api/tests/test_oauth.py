import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import Org, auth

REDIRECT = "https://claude.ai/api/mcp/auth_callback"


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


async def register(client: AsyncClient, **body: object) -> str:
    r = await client.post(
        "/api/oauth/register", json={"client_name": "Claude", "redirect_uris": [REDIRECT], **body}
    )
    assert r.status_code == 201, r.text
    assert r.json()["token_endpoint_auth_method"] == "none"
    return str(r.json()["client_id"])


async def approve(
    client: AsyncClient, org: Org, client_id: str, challenge: str, scope: str = "write"
) -> str:
    r = await client.post(
        "/api/oauth/authorize",
        json={
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "state": "st",
            "scope": scope,
        },
        headers=auth(org.member),
    )
    assert r.status_code == 200, r.text
    q = parse_qs(urlsplit(r.json()["redirect_to"]).query)
    assert q["state"] == ["st"]
    return q["code"][0]


async def exchange(client: AsyncClient, client_id: str, code: str, verifier: str) -> dict:  # type: ignore[type-arg]
    r = await client.post(
        "/api/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    return {"status": r.status_code, **r.json()}


async def test_discovery(client: AsyncClient) -> None:
    settings.web_url = "https://vectana.example.com/"
    try:
        pr = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
        assert pr["resource"] == "https://vectana.example.com/mcp"
        assert pr["authorization_servers"] == ["https://vectana.example.com"]
        meta = (await client.get("/.well-known/oauth-authorization-server")).json()
        assert meta["authorization_endpoint"] == "https://vectana.example.com/oauth/authorize"
        assert meta["code_challenge_methods_supported"] == ["S256"]
        r = await client.post("/mcp", json={})
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == (
            'Bearer resource_metadata="https://vectana.example.com'
            '/.well-known/oauth-protected-resource/mcp"'
        )
    finally:
        settings.web_url = "http://localhost:8000"


async def test_full_flow(client: AsyncClient, org: Org) -> None:
    client_id = await register(client)
    verifier, challenge = pkce()

    r = await client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st",
        },
        headers={"Accept-Language": "en"},
    )
    assert r.status_code == 302
    assert r.headers["location"].startswith("/en/oauth/authorize/?client_id=")

    info = (await client.get(f"/api/oauth/clients/{client_id}")).json()
    assert info == {"client_name": "Claude", "redirect_host": "claude.ai"}

    code = await approve(client, org, client_id, challenge)
    tok = await exchange(client, client_id, code, verifier)
    assert tok["status"] == 200 and tok["token_type"] == "Bearer" and tok["scope"] == "write"
    access = tok["access_token"]
    assert access.startswith("vcu_")

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.json()["email"] == org.member.email
    listed = (await client.get("/api/auth/tokens", headers=auth(org.member))).json()
    assert [t["name"] for t in listed] == ["Claude (OAuth)"]

    # Codes are single use.
    again = await exchange(client, client_id, code, verifier)
    assert again["status"] == 400 and again["error"] == "invalid_grant"

    # A valid token gets past the gate (the MCP process is not running in tests).
    r = await client.post("/mcp", json={}, headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 503


async def test_wrong_verifier(client: AsyncClient, org: Org) -> None:
    client_id = await register(client)
    _, challenge = pkce()
    code = await approve(client, org, client_id, challenge)
    tok = await exchange(client, client_id, code, "wrong-verifier")
    assert tok["status"] == 400 and tok["error"] == "invalid_grant"


async def test_deny(client: AsyncClient, org: Org) -> None:
    client_id = await register(client)
    _, challenge = pkce()
    r = await client.post(
        "/api/oauth/authorize",
        json={
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "state": "st",
            "approve": False,
        },
        headers=auth(org.member),
    )
    assert r.json()["redirect_to"] == f"{REDIRECT}?error=access_denied&state=st"


async def test_unregistered_redirect(client: AsyncClient, org: Org) -> None:
    client_id = await register(client)
    _, challenge = pkce()
    r = await client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://evil.example/cb",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert r.status_code == 400
    r = await client.post(
        "/api/oauth/authorize",
        json={
            "client_id": client_id,
            "redirect_uri": "https://evil.example/cb",
            "code_challenge": challenge,
        },
        headers=auth(org.member),
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "uri", ["http://example.com/cb", "javascript:alert(1)", "https://x.example/cb#frag"]
)
async def test_register_rejects_bad_redirects(client: AsyncClient, uri: str) -> None:
    r = await client.post("/api/oauth/register", json={"redirect_uris": [uri]})
    assert r.status_code == 400 and r.json()["error"] == "invalid_redirect_uri"


async def test_personal_token_cannot_approve(client: AsyncClient, org: Org) -> None:
    client_id = await register(client)
    verifier, challenge = pkce()
    code = await approve(client, org, client_id, challenge, scope="read")
    access = (await exchange(client, client_id, code, verifier))["access_token"]
    r = await client.post(
        "/api/oauth/authorize",
        json={"client_id": client_id, "redirect_uri": REDIRECT, "code_challenge": challenge},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 403
