from httpx import AsyncClient

from tests.conftest import Org, auth


async def test_only_group_admin_creates_companies(client: AsyncClient, org: Org) -> None:
    body = {"name": "新会社", "type": "affiliate"}
    assert (
        await client.post("/api/companies", json=body, headers=auth(org.company_admin))
    ).status_code == 403
    assert (
        await client.post("/api/companies", json=body, headers=auth(org.group_admin))
    ).status_code == 201


async def test_company_admin_scoped_to_own_company(client: AsyncClient, org: Org) -> None:
    h = auth(org.company_admin)
    ok = await client.post(
        "/api/departments", json={"company_id": str(org.parent.id), "name": "総務部"}, headers=h
    )
    assert ok.status_code == 201
    other = await client.post(
        "/api/departments", json={"company_id": str(org.affiliate.id), "name": "総務部"}, headers=h
    )
    assert other.status_code == 403

    users = (await client.get("/api/users", headers=h)).json()
    assert {u["email"] for u in users} == {
        "ga@example.com",
        "ca@example.com",
        "head@example.com",
        "m@example.com",
    }


async def test_members_cannot_manage_org(client: AsyncClient, org: Org) -> None:
    for user in (org.member, org.head, org.bp):
        assert (await client.get("/api/users", headers=auth(user))).status_code == 403


async def test_department_cycle_rejected(client: AsyncClient, org: Org) -> None:
    r = await client.patch(
        f"/api/departments/{org.dev.id}",
        json={"parent_id": str(org.dev1.id)},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 422


async def test_department_with_children_not_deletable(client: AsyncClient, org: Org) -> None:
    r = await client.delete(f"/api/departments/{org.dev.id}", headers=auth(org.company_admin))
    assert r.status_code == 409


async def test_partner_users_are_members_only(client: AsyncClient, org: Org) -> None:
    r = await client.post(
        "/api/invitations",
        json={"email": "x@bp.example", "company_id": str(org.partner.id), "role": "company_admin"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 422


async def test_company_admin_cannot_grant_group_admin(client: AsyncClient, org: Org) -> None:
    r = await client.patch(
        f"/api/users/{org.member.id}", json={"role": "group_admin"}, headers=auth(org.company_admin)
    )
    assert r.status_code == 403


async def test_departments_must_match_company(client: AsyncClient, org: Org) -> None:
    r = await client.patch(
        f"/api/users/{org.bp.id}",
        json={"departments": [{"department_id": str(org.dev.id)}]},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 422


async def test_partner_cannot_browse_directory(client: AsyncClient, org: Org) -> None:
    assert (await client.get("/api/users/directory", headers=auth(org.bp))).status_code == 403
    r = await client.get("/api/users/directory?q=bp", headers=auth(org.member))
    assert [u["email"] for u in r.json()] == ["bp@example.com"]
