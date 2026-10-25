"""Scanner + notifications against a fake OSV."""

import json
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationDelivery, NotificationPref
from app.models.package import Package, VulnMatch
from app.models.project import ProjectWebhook
from app.services import scanner
from app.services.notify import digest, notify_pending
from tests.conftest import Org, auth, make_project

LODASH_VULN = {
    "id": "GHSA-p6mc-m468-83gw",
    "summary": "Prototype Pollution in lodash",
    "aliases": ["CVE-2020-8203"],
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:H/A:H"}],
    "database_specific": {"severity": "HIGH"},
    "affected": [
        {
            "package": {"ecosystem": "npm", "name": "lodash"},
            "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.19"}]}],
        }
    ],
}


def fake_osv() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/querybatch":
            queries = json.loads(request.content)["queries"]
            results: list[dict[str, Any]] = []
            for q in queries:
                hit = q["package"]["name"] == "lodash" and q["version"] == "4.17.15"
                results.append({"vulns": [{"id": LODASH_VULN["id"]}]} if hit else {})
            return httpx.Response(200, json={"results": results})
        if request.url.path == f"/v1/vulns/{LODASH_VULN['id']}":
            return httpx.Response(200, json=LODASH_VULN)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    calls: list[tuple[str, str, int]] = []

    async def fake_send(channel: str, address: str, items: list[digest.Item]) -> None:
        calls.append((channel, address, len(items)))

    monkeypatch.setattr(digest, "send", fake_send)
    monkeypatch.setattr("app.services.notify.mail_enabled", lambda: True)
    return calls


async def setup_project(client: AsyncClient, session: AsyncSession, org: Org) -> str:
    project = await make_project(client, org.company_admin, "web")
    pid = project["id"]
    for name, version in [("lodash", "4.17.15"), ("react", "19.2.4")]:
        r = await client.post(
            f"/api/projects/{pid}/packages",
            json={"ecosystem": "npm", "name": name, "version": version},
            headers=auth(org.company_admin),
        )
        assert r.status_code == 201
    await client.post(
        f"/api/projects/{pid}/members",
        json={"user_id": str(org.member.id)},
        headers=auth(org.company_admin),
    )
    r = await client.post(
        f"/api/projects/{pid}/webhooks",
        json={"type": "discord", "url": "https://discord.example/hook"},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201
    return str(pid)


async def test_scan_records_match_with_details(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    await setup_project(client, session, org)
    async with fake_osv() as osv_client:
        new = await scanner.scan(session, client=osv_client)
    assert len(new) == 1
    match = (await session.exec(select(VulnMatch))).one()
    assert match.severity == "HIGH"
    assert match.fixed_version == "4.17.19"
    assert match.aliases == ["CVE-2020-8203"]
    assert match.cvss_score == pytest.approx(7.4)
    pkgs = (await session.exec(select(Package))).all()
    assert all(p.last_scanned_at is not None for p in pkgs)

    async with fake_osv() as osv_client:
        assert await scanner.scan(session, client=osv_client) == []


async def test_notify_digest_and_dedup(
    client: AsyncClient, session: AsyncSession, org: Org, sent: list[tuple[str, str, int]]
) -> None:
    await setup_project(client, session, org)
    async with fake_osv() as osv_client:
        await scanner.scan(session, client=osv_client)

    assert await notify_pending(session) == 3
    assert sorted(sent) == [
        ("discord", "https://discord.example/hook", 1),
        ("email", "ca@example.com", 1),  # creator is owner
        ("email", "m@example.com", 1),
    ]
    assert len((await session.exec(select(NotificationDelivery))).all()) == 3

    sent.clear()
    assert await notify_pending(session) == 0
    assert sent == []


async def test_notify_respects_prefs_and_thresholds(
    client: AsyncClient, session: AsyncSession, org: Org, sent: list[tuple[str, str, int]]
) -> None:
    await setup_project(client, session, org)
    session.add(NotificationPref(user_id=org.member.id, email_enabled=False))
    session.add(NotificationPref(user_id=org.company_admin.id, min_severity="CRITICAL"))
    hook = (await session.exec(select(ProjectWebhook))).one()
    hook.enabled = False
    session.add(hook)
    await session.commit()
    async with fake_osv() as osv_client:
        await scanner.scan(session, client=osv_client)
    assert await notify_pending(session) == 0


async def test_failed_send_is_retried(
    client: AsyncClient, session: AsyncSession, org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    await setup_project(client, session, org)
    async with fake_osv() as osv_client:
        await scanner.scan(session, client=osv_client)

    async def boom(channel: str, address: str, items: list[digest.Item]) -> None:
        raise RuntimeError("down")

    monkeypatch.setattr(digest, "send", boom)
    monkeypatch.setattr("app.services.notify.mail_enabled", lambda: True)
    assert await notify_pending(session) == 0

    async def ok(channel: str, address: str, items: list[digest.Item]) -> None:
        return None

    monkeypatch.setattr(digest, "send", ok)
    assert await notify_pending(session) == 3


async def test_ignored_matches_are_not_notified(
    client: AsyncClient, session: AsyncSession, org: Org, sent: list[tuple[str, str, int]]
) -> None:
    await setup_project(client, session, org)
    async with fake_osv() as osv_client:
        await scanner.scan(session, client=osv_client)
    match_id = (await session.exec(select(VulnMatch))).one().id
    r = await client.patch(
        f"/api/vulnerabilities/{match_id}", json={"status": "ignored"}, headers=auth(org.member)
    )
    assert r.status_code == 200
    assert await notify_pending(session) == 0


async def test_dashboard_counts(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    await setup_project(client, session, org)
    async with fake_osv() as osv_client:
        await scanner.scan(session, client=osv_client)
    d = (await client.get("/api/dashboard", headers=auth(org.member))).json()
    assert d["project_count"] == 1
    assert d["package_count"] == 2
    assert d["open_counts"]["HIGH"] == 1
    assert d["recent"][0]["vuln_id"] == LODASH_VULN["id"]
    assert (await client.get("/api/dashboard", headers=auth(org.bp))).json()["project_count"] == 0


async def test_lockfile_import_syncs(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    project = await make_project(client, org.company_admin, "imp")
    url = f"/api/projects/{project['id']}/packages/import"
    h = auth(org.company_admin)

    def lock(pkgs: dict[str, str]) -> bytes:
        return json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {f"node_modules/{n}": {"version": v} for n, v in pkgs.items()},
            }
        ).encode()

    r = await client.post(
        url, files={"file": ("package-lock.json", lock({"a": "1.0.0", "b": "1.0.0"}))}, headers=h
    )
    assert r.json() == {
        "filename": "package-lock.json",
        "ecosystem": "npm",
        "added": 2,
        "removed": 0,
        "total": 2,
    }
    r = await client.post(
        url, files={"file": ("package-lock.json", lock({"a": "1.0.1", "b": "1.0.0"}))}, headers=h
    )
    assert r.json()["added"] == 1 and r.json()["removed"] == 1
    bad = await client.post(url, files={"file": ("Gemfile.lock", b"x")}, headers=h)
    assert bad.status_code == 422


async def test_list_orders_by_severity_before_limit(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    pid = await setup_project(client, session, org)
    pkg = (await session.exec(select(Package).where(Package.name == "react"))).one()
    session.add(VulnMatch(package_id=pkg.id, vuln_id="NEW-LOW", severity="LOW"))
    await session.commit()
    lodash = (await session.exec(select(Package).where(Package.name == "lodash"))).one()
    session.add(VulnMatch(package_id=lodash.id, vuln_id="OLD-CRIT", severity="CRITICAL"))
    await session.commit()
    r = await client.get(f"/api/vulnerabilities?project_id={pid}&limit=1", headers=auth(org.member))
    assert [m["vuln_id"] for m in r.json()] == ["OLD-CRIT"]
