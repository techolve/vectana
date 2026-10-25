"""EOL matching, refresh against a fake endoflife.date, runtimes, notifications."""

from datetime import date
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.eol import EolFinding
from app.services import eol
from app.services.notify import digest, notify_pending
from tests.conftest import Org, auth, make_project

TODAY = date(2026, 10, 25)

PRODUCTS: dict[str, dict[str, Any]] = {
    "nextjs": {
        "name": "nextjs",
        "label": "Next.js",
        "releases": [
            {"name": "16", "isEol": False, "eolFrom": None, "latest": {"name": "16.4.3"}},
            {"name": "15", "isEol": True, "eolFrom": "2026-10-21", "latest": {"name": "15.5.28"}},
        ],
    },
    "python": {
        "name": "python",
        "label": "Python",
        "releases": [
            {"name": "3.14", "isEol": False, "eolFrom": "2030-10-31", "latest": {"name": "3.14.2"}},
            {
                "name": "3.10",
                "isEol": False,
                "eolFrom": "2026-12-31",
                "latest": {"name": "3.10.19"},
            },
            {"name": "3.1", "isEol": True, "eolFrom": "2012-04-09", "latest": {"name": "3.1.5"}},
        ],
    },
}


def fake_eol() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        if path == "/identifiers/purl":
            rows = [{"identifier": "pkg:npm/next", "product": {"name": "nextjs"}}]
            return httpx.Response(200, json={"result": rows})
        if path == "/products":
            return httpx.Response(
                200,
                json={"result": [{"name": n, "label": p["label"]} for n, p in PRODUCTS.items()]},
            )
        name = path.removeprefix("/products/")
        if name in PRODUCTS:
            return httpx.Response(200, json={"result": PRODUCTS[name]})
        return httpx.Response(404)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://endoflife.date/api/v1"
    )


@pytest.fixture(autouse=True)
def mock_eol(monkeypatch: pytest.MonkeyPatch) -> None:
    eol._cache.clear()
    monkeypatch.setattr(eol, "make_client", fake_eol)


def test_match_release_picks_longest_cycle() -> None:
    releases = PRODUCTS["python"]["releases"]
    assert eol.match_release(releases, "3.10.4")["name"] == "3.10"  # type: ignore[index]
    assert eol.match_release(releases, "3.1.2")["name"] == "3.1"  # type: ignore[index]
    assert eol.match_release(releases, "2.7.18") is None


def test_evaluate_statuses() -> None:
    py = PRODUCTS["python"]
    assert eol.evaluate(py, "3.14.2", 90, TODAY).status == "supported"
    assert eol.evaluate(py, "3.10.4", 90, TODAY).status == "approaching"  # 2026-12-31
    assert eol.evaluate(py, "3.10.4", 30, TODAY).status == "supported"
    assert eol.evaluate(py, "3.1.2", 90, TODAY).status == "eol"
    assert eol.evaluate(py, "2.7", 90, TODAY).status == "unknown"


def test_package_purl() -> None:
    assert eol.package_purl("npm", "@angular/core") == "pkg:npm/%40angular/core"
    assert eol.package_purl("PyPI", "Django") == "pkg:pypi/django"
    assert eol.package_purl("Maven", "org.springframework.boot:spring-boot") == (
        "pkg:maven/org.springframework.boot/spring-boot"
    )


async def _setup(client: AsyncClient, org: Org) -> str:
    project = await make_project(client, org.company_admin, "app")
    pid = project["id"]
    h = auth(org.company_admin)
    for name, version in [("next", "15.5.0"), ("lodash", "4.17.21")]:
        await client.post(
            f"/api/projects/{pid}/packages",
            json={"ecosystem": "npm", "name": name, "version": version},
            headers=h,
        )
    r = await client.post(
        f"/api/projects/{pid}/runtimes", json={"product": "python", "version": "3.10.4"}, headers=h
    )
    assert r.status_code == 201, r.text
    return str(pid)


async def test_refresh_creates_findings(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    pid = await _setup(client, org)
    async with fake_eol() as c:
        await eol.refresh(session, client=c, today=TODAY)
    findings = {f.product: f for f in (await session.exec(select(EolFinding))).all()}
    assert set(findings) == {"nextjs", "python"}  # lodash has no EOL product
    assert findings["nextjs"].status == "eol" and findings["nextjs"].cycle == "15"
    assert findings["python"].status == "approaching"

    r = await client.get(f"/api/eol?project_id={pid}", headers=auth(org.company_admin))
    assert [f["product"] for f in r.json()] == ["nextjs", "python"]  # EOL before approaching
    d = (await client.get("/api/dashboard", headers=auth(org.company_admin))).json()
    assert d["eol_counts"] == {"eol": 1, "approaching": 1}
    assert d["projects"][0]["eol_counts"] == {"eol": 1, "approaching": 1}
    assert (await client.get("/api/dashboard", headers=auth(org.bp))).json()["eol"] == []


async def test_unknown_runtime_product_rejected(client: AsyncClient, org: Org) -> None:
    project = await make_project(client, org.company_admin, "x")
    r = await client.post(
        f"/api/projects/{project['id']}/runtimes",
        json={"product": "nope", "version": "1"},
        headers={**auth(org.company_admin), "Accept-Language": "ja"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "endoflife.date に登録されていない製品です"


async def test_removed_runtime_drops_finding(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    pid = await _setup(client, org)
    async with fake_eol() as c:
        await eol.refresh(session, client=c, today=TODAY)
    h = auth(org.company_admin)
    rt = (await client.get(f"/api/projects/{pid}/runtimes", headers=h)).json()[0]
    await client.delete(f"/api/projects/{pid}/runtimes/{rt['id']}", headers=h)
    products = {f.product for f in (await session.exec(select(EolFinding))).all()}
    assert products == {"nextjs"}


async def test_eol_notified_once_per_stage(
    client: AsyncClient, session: AsyncSession, org: Org, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_send(channel: str, address: str, d: digest.Digest, locale: str) -> None:
        calls.append((address, len(d.eol), locale))

    monkeypatch.setattr(digest, "send", fake_send)
    monkeypatch.setattr("app.services.notify.mail_enabled", lambda: True)
    await _setup(client, org)
    await client.put("/api/auth/locale", json={"locale": "en"}, headers=auth(org.company_admin))
    async with fake_eol() as c:
        await eol.refresh(session, client=c, today=TODAY)
    await notify_pending(session)
    assert calls == [("ca@example.com", 2, "en")]

    calls.clear()
    await notify_pending(session)
    assert calls == []

    # Moving from "approaching" to "eol" is a new stage and is notified again.
    async with fake_eol() as c:
        await eol.refresh(session, client=c, today=date(2027, 1, 5))
    await notify_pending(session)
    assert calls == [("ca@example.com", 1, "en")]


async def test_settings_require_group_admin(client: AsyncClient, org: Org) -> None:
    assert (await client.get("/api/settings", headers=auth(org.member))).json() == {
        "eol_warning_days": 90
    }
    body = {"eol_warning_days": 30}
    assert (
        await client.put("/api/settings", json=body, headers=auth(org.company_admin))
    ).status_code == 403
    assert (
        await client.put("/api/settings", json=body, headers=auth(org.group_admin))
    ).status_code == 200
    assert (await client.get("/api/settings", headers=auth(org.member))).json() == body


def test_digest_renders_both_languages() -> None:
    from app.models.project import Project

    project = Project(company_id=org_id(), name="app")
    finding = EolFinding(
        project_id=project.id,
        product="nextjs",
        product_label="Next.js",
        version="15.5.0",
        cycle="15",
        eol_date=date(2026, 10, 21),
        status="eol",
    )
    d = digest.Digest(eol=[digest.EolItem(finding=finding, project=project)])
    assert "サポート終了" in digest.render_text(d, "ja")
    assert "ended on 2026-10-21" in digest.render_text(d, "en")
    assert digest.subject(d, "en") == "[Vectana] 1 items need your attention"


def org_id():  # type: ignore[no-untyped-def]
    from uuid import uuid4

    return uuid4()
