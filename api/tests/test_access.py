"""Who can see which project."""

import pytest
from httpx import AsyncClient

from tests.conftest import Org, auth, make_project


@pytest.fixture
async def projects(client: AsyncClient, org: Org) -> dict[str, dict]:  # type: ignore[type-arg]
    return {
        # Created by group admin in 第1開発部 (under 開発本部)
        "dev1": await make_project(client, org.group_admin, "dev1", org.dev1.id),
        # Parent company, 営業部
        "sales": await make_project(client, org.group_admin, "sales", org.sales.id),
        # Affiliate company project
        "aff": await make_project(client, org.affiliate_admin, "aff"),
    }


async def visible(client: AsyncClient, user) -> set[str]:  # type: ignore[no-untyped-def]
    r = await client.get("/api/projects", headers=auth(user))
    return {p["name"] for p in r.json()}


async def test_visibility_matrix(client: AsyncClient, org: Org, projects: dict) -> None:  # type: ignore[type-arg]
    assert await visible(client, org.group_admin) == {"dev1", "sales", "aff"}
    assert await visible(client, org.company_admin) == {"dev1", "sales"}
    assert await visible(client, org.affiliate_admin) == {"aff"}
    assert await visible(client, org.head) == {"dev1"}  # sub-department included
    assert await visible(client, org.member) == set()
    assert await visible(client, org.bp) == set()


async def test_assignment_grants_access(client: AsyncClient, org: Org, projects: dict) -> None:  # type: ignore[type-arg]
    pid = projects["sales"]["id"]
    r = await client.post(
        f"/api/projects/{pid}/members",
        json={"user_id": str(org.bp.id), "role": "member"},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201
    assert await visible(client, org.bp) == {"sales"}
    # BP got write but not manage.
    pkg = await client.post(
        f"/api/projects/{pid}/packages",
        json={"ecosystem": "npm", "name": "lodash", "version": "4.17.15"},
        headers=auth(org.bp),
    )
    assert pkg.status_code == 201
    hooks = await client.get(f"/api/projects/{pid}/webhooks", headers=auth(org.bp))
    assert hooks.status_code == 403


async def test_hidden_project_is_404(client: AsyncClient, org: Org, projects: dict) -> None:  # type: ignore[type-arg]
    r = await client.get(f"/api/projects/{projects['aff']['id']}", headers=auth(org.company_admin))
    assert r.status_code == 404


async def test_viewer_is_read_only(client: AsyncClient, org: Org, projects: dict) -> None:  # type: ignore[type-arg]
    pid = projects["sales"]["id"]
    await client.post(
        f"/api/projects/{pid}/members",
        json={"user_id": str(org.member.id), "role": "viewer"},
        headers=auth(org.group_admin),
    )
    assert (await client.get(f"/api/projects/{pid}", headers=auth(org.member))).status_code == 200
    r = await client.post(
        f"/api/projects/{pid}/packages",
        json={"ecosystem": "npm", "name": "a", "version": "1.0.0"},
        headers=auth(org.member),
    )
    assert r.status_code == 403


async def test_partner_cannot_own_or_create(client: AsyncClient, org: Org, projects: dict) -> None:  # type: ignore[type-arg]
    r = await client.post(
        f"/api/projects/{projects['sales']['id']}/members",
        json={"user_id": str(org.bp.id), "role": "owner"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 422
    assert (
        await client.post("/api/projects", json={"name": "x"}, headers=auth(org.bp))
    ).status_code == 403


async def test_head_can_assign_in_managed_department(
    client: AsyncClient,
    org: Org,
    projects: dict,  # type: ignore[type-arg]
) -> None:
    ok = await client.post(
        f"/api/projects/{projects['dev1']['id']}/members",
        json={"user_id": str(org.member.id)},
        headers=auth(org.head),
    )
    assert ok.status_code == 201
    hidden = await client.post(
        f"/api/projects/{projects['sales']['id']}/members",
        json={"user_id": str(org.member.id)},
        headers=auth(org.head),
    )
    assert hidden.status_code == 404


async def test_member_creates_own_project(client: AsyncClient, org: Org) -> None:
    await make_project(client, org.member, "mine")
    assert await visible(client, org.member) == {"mine"}


async def test_vulnerabilities_respect_visibility(
    client: AsyncClient,
    org: Org,
    projects: dict,  # type: ignore[type-arg]
) -> None:
    r = await client.get("/api/vulnerabilities", headers=auth(org.member))
    assert r.status_code == 200 and r.json() == []
