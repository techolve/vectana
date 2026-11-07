from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.token import PersonalToken
from tests.conftest import Org, auth, make_project


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def issue(client: AsyncClient, user: object, **body: object) -> dict:  # type: ignore[type-arg]
    r = await client.post(
        "/api/auth/tokens",
        json={"name": "Claude", **body},
        headers=auth(user),  # type: ignore[arg-type]
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_lifecycle(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    created = await issue(client, org.member)
    secret = created["token"]
    assert secret.startswith("vcu_") and created["prefix"] == secret[:12]
    assert created["scope"] == "read"
    row = (await session.exec(select(PersonalToken))).one()
    assert len(row.token_hash) == 64 and secret not in row.token_hash

    r = await client.get("/api/auth/me", headers=bearer(secret))
    assert r.status_code == 200 and r.json()["email"] == org.member.email

    listed = (await client.get("/api/auth/tokens", headers=auth(org.member))).json()
    assert [t["name"] for t in listed] == ["Claude"] and listed[0]["last_used_at"]
    assert "token" not in listed[0]
    # Other users don't see it and can't revoke it.
    assert (await client.get("/api/auth/tokens", headers=auth(org.bp))).json() == []
    r = await client.delete(f"/api/auth/tokens/{created['id']}", headers=auth(org.bp))
    assert r.status_code == 404

    r = await client.delete(f"/api/auth/tokens/{created['id']}", headers=auth(org.member))
    assert r.status_code == 204
    r = await client.get("/api/auth/me", headers=bearer(secret))
    assert r.status_code == 401


async def test_read_scope_blocks_writes(client: AsyncClient, org: Org) -> None:
    secret = (await issue(client, org.company_admin))["token"]
    assert (await client.get("/api/projects", headers=bearer(secret))).status_code == 200
    r = await client.post(
        "/api/projects",
        json={"name": "x"},
        headers=bearer(secret),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "このトークンは読み取り専用です"


async def test_write_scope_acts_as_user(client: AsyncClient, org: Org) -> None:
    project = await make_project(client, org.company_admin, "mine")
    secret = (await issue(client, org.member, scope="write"))["token"]
    # The member is not assigned, so the project stays hidden.
    r = await client.get(f"/api/projects/{project['id']}", headers=bearer(secret))
    assert r.status_code == 404
    admin = (await issue(client, org.company_admin, scope="write"))["token"]
    r = await client.post(
        f"/api/projects/{project['id']}/packages",
        json={"ecosystem": "npm", "name": "lodash", "version": "4.17.15"},
        headers=bearer(admin),
    )
    assert r.status_code in (200, 201), r.text


async def test_token_cannot_manage_tokens(client: AsyncClient, org: Org) -> None:
    secret = (await issue(client, org.member, scope="write"))["token"]
    for method, path in (("GET", "/api/auth/tokens"), ("POST", "/api/auth/tokens")):
        r = await client.request(method, path, json={"name": "x"}, headers=bearer(secret))
        assert r.status_code == 403, (method, r.text)


async def test_expired_and_disabled(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    secret = (await issue(client, org.member, expires_in_days=1))["token"]
    row = (await session.exec(select(PersonalToken))).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(row)
    await session.commit()
    r = await client.get("/api/auth/me", headers=bearer(secret))
    assert r.status_code == 401

    secret = (await issue(client, org.member))["token"]
    org.member.is_active = False
    session.add(org.member)
    await session.commit()
    assert (await client.get("/api/auth/me", headers=bearer(secret))).status_code == 403
