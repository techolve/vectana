from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient

from app.core import oidc
from app.core.auth import decode_access_token
from app.core.config import settings
from tests.conftest import Org

ISSUER = "https://idp.example.com"
JWKS_URI = f"{ISSUER}/jwks"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class _SigningKey:
    key: Any


class _FakeJwks:
    def get_signing_key_from_jwt(self, _token: str) -> _SigningKey:
        return _SigningKey(_KEY.public_key())


@pytest.fixture(autouse=True)
def provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", "vectana")
    monkeypatch.setattr(settings, "oidc_client_secret", "secret")
    monkeypatch.setattr(settings, "web_url", "https://vectana.test")
    p = oidc.Provider(
        issuer=ISSUER,
        authorization_endpoint=f"{ISSUER}/authorize",
        token_endpoint=f"{ISSUER}/token",
        jwks_uri=JWKS_URI,
    )
    monkeypatch.setattr(oidc, "_provider", (float("inf"), p))
    monkeypatch.setitem(oidc._jwks, JWKS_URI, _FakeJwks())
    yield


def _id_token(email: str, nonce: str, **extra: Any) -> str:
    claims = {
        "iss": ISSUER,
        "aud": "vectana",
        "sub": "user-1",
        "email": email,
        "nonce": nonce,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        **extra,
    }
    return jwt.encode(claims, _KEY, algorithm="RS256")


async def _start(client: AsyncClient, locale: str = "ja") -> dict[str, str]:
    r = await client.get("/api/auth/oidc/login", params={"locale": locale})
    assert r.status_code == 307
    query = parse_qs(urlparse(r.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://vectana.test/api/auth/oidc/callback"]
    flow = jwt.decode(r.cookies["vectana_oidc"], settings.secret_key, algorithms=["HS256"])
    client.cookies.set("vectana_oidc", r.cookies["vectana_oidc"])
    return {"state": query["state"][0], "nonce": flow["nonce"]}


def _fake_exchange(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    async def exchange(_code: str, _verifier: str) -> str:
        return token

    monkeypatch.setattr("app.routers.oidc.exchange_code", exchange)


async def test_config(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (await client.get("/api/auth/oidc/config")).json()["enabled"] is True
    monkeypatch.setattr(settings, "oidc_client_secret", "")
    assert (await client.get("/api/auth/oidc/config")).json()["enabled"] is False
    assert (await client.get("/api/auth/oidc/login")).status_code == 404


async def test_sign_in_existing_user(
    client: AsyncClient, org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = await _start(client, "en")
    _fake_exchange(monkeypatch, _id_token(org.head.email.upper(), flow["nonce"]))
    r = await client.get("/api/auth/oidc/callback", params={"code": "c", "state": flow["state"]})
    location = urlparse(r.headers["location"])
    assert location.path == "/en/login/sso/"
    tokens = parse_qs(location.fragment)
    assert decode_access_token(tokens["access_token"][0])["sub"] == str(org.head.id)
    assert "refresh_token" in tokens


async def test_unknown_email_is_rejected(
    client: AsyncClient, org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = await _start(client)
    _fake_exchange(monkeypatch, _id_token("stranger@example.com", flow["nonce"]))
    r = await client.get("/api/auth/oidc/callback", params={"code": "c", "state": flow["state"]})
    assert r.headers["location"] == "https://vectana.test/ja/login/?sso_error=not_registered"


async def test_state_mismatch(client: AsyncClient, org: Org) -> None:
    await _start(client)
    r = await client.get("/api/auth/oidc/callback", params={"code": "c", "state": "forged"})
    assert r.headers["location"].endswith("sso_error=expired")


async def test_missing_cookie(client: AsyncClient) -> None:
    r = await client.get("/api/auth/oidc/callback", params={"code": "c", "state": "s"})
    assert r.headers["location"].endswith("sso_error=expired")


async def test_nonce_mismatch(
    client: AsyncClient, org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = await _start(client)
    _fake_exchange(monkeypatch, _id_token(org.head.email, "other-nonce"))
    r = await client.get("/api/auth/oidc/callback", params={"code": "c", "state": flow["state"]})
    assert r.headers["location"].endswith("sso_error=provider")


async def test_wrong_audience(
    client: AsyncClient, org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = await _start(client)
    _fake_exchange(monkeypatch, _id_token(org.head.email, flow["nonce"], aud="someone-else"))
    r = await client.get("/api/auth/oidc/callback", params={"code": "c", "state": flow["state"]})
    assert r.headers["location"].endswith("sso_error=provider")
