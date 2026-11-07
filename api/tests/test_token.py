import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.package import Package
from app.models.token import ApiToken
from tests.conftest import Org, auth, make_project

BOM = json.dumps(
    {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "components": [
            {"purl": "pkg:npm/lodash@4.17.15"},
            {"purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"},
            {"purl": "pkg:deb/debian/openssl@3.0.11"},
        ],
    }
).encode()


@pytest.fixture(autouse=True)
def no_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(*_args: object) -> None:
        return None

    monkeypatch.setattr("app.routers.project.scan_and_notify", fake)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def issue(client: AsyncClient, org: Org, project_id: str, **body: object) -> dict:  # type: ignore[type-arg]
    r = await client.post(
        f"/api/projects/{project_id}/tokens",
        json={"name": "GitHub Actions", **body},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_token_lifecycle(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    project = await make_project(client, org.company_admin, "ci")
    created = await issue(client, org, project["id"])
    secret = created["token"]
    assert secret.startswith("vct_") and created["prefix"] == secret[:12]
    assert created["created_by_email"] == "ca@example.com"

    # Only the hash is stored.
    row = (await session.exec(select(ApiToken))).one()
    assert secret not in (row.token_hash, row.prefix + "x")
    assert len(row.token_hash) == 64

    listed = (
        await client.get(f"/api/projects/{project['id']}/tokens", headers=auth(org.company_admin))
    ).json()
    assert [t["name"] for t in listed] == ["GitHub Actions"]
    assert "token" not in listed[0] and listed[0]["last_used_at"] is None

    url = f"/api/projects/{project['id']}/packages/import"
    r = await client.post(url, files={"file": ("bom.json", BOM)}, headers=bearer(secret))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "CycloneDX"
    assert body["ecosystem"] == "Maven, npm"
    assert body["added"] == 2 and body["unsupported"] == {"deb": 1}
    sources = {p.source for p in (await session.exec(select(Package))).all()}
    assert sources == {"sbom:bom.json"}

    r = await client.post(f"/api/projects/{project['id']}/scan", headers=bearer(secret))
    assert r.status_code == 202 and r.json() == {"packages": 2}

    listed = (
        await client.get(f"/api/projects/{project['id']}/tokens", headers=auth(org.company_admin))
    ).json()
    assert listed[0]["last_used_at"] is not None

    r = await client.delete(
        f"/api/projects/{project['id']}/tokens/{created['id']}", headers=auth(org.company_admin)
    )
    assert r.status_code == 204
    r = await client.post(url, files={"file": ("bom.json", BOM)}, headers=bearer(secret))
    assert r.status_code == 401


async def test_token_is_confined_to_its_project(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    mine = await make_project(client, org.company_admin, "mine")
    other = await make_project(client, org.company_admin, "other")
    secret = (await issue(client, org, mine["id"]))["token"]
    h = bearer(secret)

    r = await client.post(
        f"/api/projects/{other['id']}/packages/import", files={"file": ("bom.json", BOM)}, headers=h
    )
    assert r.status_code == 404
    # Nothing beyond import and scan: no reading, no managing.
    assert (await client.get(f"/api/projects/{mine['id']}", headers=h)).status_code == 401
    assert (await client.get(f"/api/projects/{mine['id']}/tokens", headers=h)).status_code == 401
    assert (await client.get("/api/projects", headers=h)).status_code == 401
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401


async def test_expired_and_unknown_tokens(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    project = await make_project(client, org.company_admin, "exp")
    created = await issue(client, org, project["id"], expires_in_days=30)
    assert created["expires_at"] is not None
    url = f"/api/projects/{project['id']}/scan"

    assert (await client.post(url, headers=bearer(created["token"]))).status_code == 202
    row = (await session.exec(select(ApiToken))).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(row)
    await session.commit()
    r = await client.post(url, headers=bearer(created["token"]))
    assert r.status_code == 401 and r.json()["detail"] == "APIトークンの有効期限が切れています"
    assert (await client.post(url, headers=bearer("vct_nope"))).status_code == 401


async def test_only_managers_handle_tokens(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    project = await make_project(client, org.company_admin, "perm")
    r = await client.post(
        f"/api/projects/{project['id']}/members",
        json={"user_id": str(org.member.id), "role": "member"},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201, r.text
    tokens_url = f"/api/projects/{project['id']}/tokens"
    assert (await client.get(tokens_url, headers=auth(org.member))).status_code == 403
    r = await client.post(tokens_url, json={"name": "x"}, headers=auth(org.member))
    assert r.status_code == 403
    # Hidden project: 404, not 403.
    assert (await client.get(tokens_url, headers=auth(org.bp))).status_code == 404
    r = await client.post(tokens_url, json={"name": " "}, headers=auth(org.company_admin))
    assert r.status_code == 422


async def test_source_name_separates_sboms(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    project = await make_project(client, org.company_admin, "mono")
    url = f"/api/projects/{project['id']}/packages/import"
    h = auth(org.company_admin)

    def bom(*purls: str) -> bytes:
        return json.dumps(
            {"bomFormat": "CycloneDX", "components": [{"purl": p} for p in purls]}
        ).encode()

    r = await client.post(
        url,
        files={"file": ("bom.json", bom("pkg:npm/a@1.0.0"))},
        data={"source": "frontend"},
        headers=h,
    )
    assert r.json()["added"] == 1
    r = await client.post(
        url,
        files={"file": ("bom.json", bom("pkg:pypi/b@2.0.0"))},
        data={"source": "backend"},
        headers=h,
    )
    assert r.json()["added"] == 1 and r.json()["removed"] == 0
    # Re-sending frontend replaces only frontend's packages.
    r = await client.post(
        url,
        files={"file": ("bom.json", bom("pkg:npm/a@1.0.1"))},
        data={"source": "frontend"},
        headers=h,
    )
    assert r.json()["added"] == 1 and r.json()["removed"] == 1
    pkgs = {(p.name, p.version, p.source) for p in (await session.exec(select(Package))).all()}
    assert pkgs == {("a", "1.0.1", "sbom:frontend"), ("b", "2.0.0", "sbom:backend")}

    r = await client.post(
        url, files={"file": ("bom.json", bom())}, data={"source": "bad name!"}, headers=h
    )
    assert r.status_code == 422
