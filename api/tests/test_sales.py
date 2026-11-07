"""Customers, deals, estimates, multiple roles and who sees money."""

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.user import User
from tests.conftest import Org, auth, make_project


async def _customer(client: AsyncClient, user: User, name: str = "東和フーズ") -> dict:  # type: ignore[type-arg]
    r = await client.post("/api/customers", json={"name": name}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def _deal(client: AsyncClient, user: User, customer_id: str | None = None) -> dict:  # type: ignore[type-arg]
    body: dict[str, object] = {
        "name": "物流管理システム刷新",
        "status": "inquiry",
        "probability": 20,
    }
    if customer_id:
        body["customer_id"] = customer_id
    r = await client.post("/api/projects", json=body, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def visible(client: AsyncClient, user: User) -> set[str]:
    r = await client.get("/api/projects", headers=auth(user))
    return {p["name"] for p in r.json()}


async def test_sales_manage_own_company_customers(client: AsyncClient, org: Org) -> None:
    c = await _customer(client, org.seller)
    assert c["company_id"] == str(org.parent.id) and c["can_edit"]
    # Another company's admin, members and BP users cannot see it.
    assert (await client.get("/api/customers", headers=auth(org.affiliate_admin))).json() == []
    assert (await client.get("/api/customers", headers=auth(org.member))).status_code == 403
    assert (await client.get("/api/customers", headers=auth(org.bp))).status_code == 403
    r = await client.get(f"/api/customers/{c['id']}", headers=auth(org.affiliate_admin))
    assert r.status_code == 404
    # Accounting reads, PMO reads across companies, neither edits.
    for user in (org.accounting, org.pmo):
        r = await client.get(f"/api/customers/{c['id']}", headers=auth(user))
        assert r.status_code == 200 and not r.json()["can_edit"]
        r = await client.patch(f"/api/customers/{c['id']}", json={"name": "x"}, headers=auth(user))
        assert r.status_code == 403
    # Sales cannot create customers for another company.
    r = await client.post(
        "/api/customers",
        json={"name": "x", "company_id": str(org.affiliate.id)},
        headers=auth(org.seller),
    )
    assert r.status_code == 403


async def test_contacts_have_one_primary(client: AsyncClient, org: Org) -> None:
    c = await _customer(client, org.seller)
    base = f"/api/customers/{c['id']}/contacts"
    a = await client.post(base, json={"name": "山田", "is_primary": True}, headers=auth(org.seller))
    await client.post(base, json={"name": "木村", "is_primary": True}, headers=auth(org.seller))
    detail = (await client.get(f"/api/customers/{c['id']}", headers=auth(org.seller))).json()
    assert [(x["name"], x["is_primary"]) for x in detail["contacts"]] == [
        ("木村", True),
        ("山田", False),
    ]
    assert detail["primary_contact"] == "木村"
    r = await client.delete(f"{base}/{a.json()['id']}", headers=auth(org.seller))
    assert r.status_code == 204


async def test_deals_are_hidden_until_ordered(client: AsyncClient, org: Org) -> None:
    deal = await _deal(client, org.seller)
    assert deal["is_deal"] and deal["status"] == "inquiry" and deal["ordered_on"] is None
    # Members and heads of other projects, accounting and PMO do not see deals.
    for user in (org.head, org.member, org.accounting, org.pmo, org.bp, org.affiliate_admin):
        assert "物流管理システム刷新" not in await visible(client, user), user.email
    assert "物流管理システム刷新" in await visible(client, org.company_admin)
    # Once won, PMO and accounting see it read-only.
    r = await client.patch(
        f"/api/projects/{deal['id']}", json={"status": "won"}, headers=auth(org.seller)
    )
    assert r.status_code == 200 and r.json()["ordered_on"] is not None
    for user in (org.accounting, org.pmo):
        r = await client.get(f"/api/projects/{deal['id']}", headers=auth(user))
        assert r.json()["my_level"] == "read"
    # After the order, sales keep read access but not project settings.
    r = await client.get(f"/api/projects/{deal['id']}", headers=auth(org.seller))
    assert r.json()["my_level"] == "manage"  # the creator is the owner


async def test_only_sellers_create_deals(client: AsyncClient, org: Org) -> None:
    r = await client.post(
        "/api/projects", json={"name": "x", "status": "inquiry"}, headers=auth(org.member)
    )
    assert r.status_code == 403
    r = await client.post(
        "/api/projects", json={"name": "x", "expected_amount": 100}, headers=auth(org.member)
    )
    assert r.status_code == 403
    # An internal project may start in development without sales.
    r = await client.post("/api/projects", json={"name": "社内勤怠"}, headers=auth(org.member))
    assert r.status_code == 201 and r.json()["ordered_on"] is not None


async def test_customer_must_be_same_company(client: AsyncClient, org: Org) -> None:
    c = await _customer(client, org.affiliate_admin, "他社の顧客")
    r = await client.post(
        "/api/projects",
        json={"name": "x", "status": "inquiry", "customer_id": c["id"]},
        headers=auth(org.seller),
    )
    assert r.status_code == 422


async def test_status_changes_need_sales_except_delivery(client: AsyncClient, org: Org) -> None:
    p = await make_project(client, org.group_admin, "保守移行")
    await client.post(
        f"/api/projects/{p['id']}/members",
        json={"user_id": str(org.member.id), "role": "owner"},
        headers=auth(org.group_admin),
    )
    # A project owner moves development -> maintenance...
    r = await client.patch(
        f"/api/projects/{p['id']}", json={"status": "maintenance"}, headers=auth(org.member)
    )
    assert r.status_code == 200 and r.json()["status"] == "maintenance"
    # ...but cannot mark it lost or touch deal fields.
    for body in ({"status": "lost"}, {"probability": 50}):
        r = await client.patch(f"/api/projects/{p['id']}", json=body, headers=auth(org.member))
        assert r.status_code == 403, body
    r = await client.patch(
        f"/api/projects/{p['id']}",
        json={"status": "lost", "lost_reason": "先方内製"},
        headers=auth(org.seller),
    )
    assert r.json()["archived"] and r.json()["lost_reason"] == "先方内製"


async def test_estimates_and_money_visibility(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    org.member.unit_cost = 40000
    session.add(org.member)
    await session.commit()
    c = await _customer(client, org.seller)
    deal = await _deal(client, org.seller, c["id"])
    for user, role in ((org.member, "member"), (org.bp, "member")):
        await client.post(
            f"/api/projects/{deal['id']}/members",
            json={"user_id": str(user.id), "role": role},
            headers=auth(org.seller),
        )
    r = await client.post(
        f"/api/projects/{deal['id']}/estimates",
        json={
            "title": "初回開発",
            "amount": 1_000_000,
            "status": "submitted",
            "lines": [
                {"label": "開発", "user_id": str(org.member.id), "days": 10},
                {"label": "PM", "days": 5, "unit_cost": 60000},
            ],
        },
        headers=auth(org.seller),
    )
    assert r.status_code == 201, r.text
    est = r.json()
    assert est["effort_days"] == 15
    assert est["cost"] == 700_000 and est["margin"] == 0.3
    assert [line["unit_cost"] for line in est["lines"]] == [40000, 60000]

    # Proper members see amount, effort and margin but not unit costs.
    r = await client.get(f"/api/projects/{deal['id']}/estimates", headers=auth(org.member))
    seen = r.json()[0]
    assert seen["amount"] == 1_000_000 and seen["margin"] == 0.3 and seen["cost"] is None
    assert [line["unit_cost"] for line in seen["lines"]] == [None, None]
    # BP users see nothing about money.
    r = await client.get(f"/api/projects/{deal['id']}/estimates", headers=auth(org.bp))
    assert r.status_code == 403
    p = (await client.get(f"/api/projects/{deal['id']}", headers=auth(org.bp))).json()
    assert p["customer"] is None and p["status"] is None and p["won_amount"] is None
    # Members cannot edit estimates.
    r = await client.patch(
        f"/api/estimates/{est['id']}", json={"amount": 1}, headers=auth(org.member)
    )
    assert r.status_code == 403

    # Totals on the project.
    p = (await client.get(f"/api/projects/{deal['id']}", headers=auth(org.member))).json()
    assert p["open_estimate_amount"] == 1_000_000 and p["won_amount"] == 0
    assert p["customer"]["name"] == "東和フーズ"

    # Winning the estimate orders the deal.
    r = await client.patch(
        f"/api/estimates/{est['id']}", json={"status": "won"}, headers=auth(org.seller)
    )
    assert r.json()["decided_on"] is not None
    p = (await client.get(f"/api/projects/{deal['id']}", headers=auth(org.seller))).json()
    assert p["status"] == "won" and p["won_amount"] == 1_000_000 and not p["is_deal"]

    # A later rate change does not rewrite the estimate.
    org.member.unit_cost = 99999
    session.add(org.member)
    await session.commit()
    r = await client.get(f"/api/estimates/{est['id']}", headers=auth(org.accounting))
    assert r.json()["lines"][0]["unit_cost"] == 40000

    # Customer list sums live estimates.
    rows = (await client.get("/api/customers", headers=auth(org.seller))).json()
    assert rows[0]["project_count"] == 1 and rows[0]["pipeline_amount"] == 1_000_000


async def test_monthly_maintenance_estimate(client: AsyncClient, org: Org) -> None:
    p = await make_project(client, org.company_admin, "予約アプリ")
    for amount, decided in ((180_000, "2026-01-10"), (280_000, "2026-11-01")):
        r = await client.post(
            f"/api/projects/{p['id']}/estimates",
            json={
                "title": "保守",
                "kind": "maintenance",
                "billing": "monthly",
                "amount": amount,
                "status": "won",
                "decided_on": decided,
            },
            headers=auth(org.company_admin),
        )
        assert r.status_code == 201
    row = (await client.get(f"/api/projects/{p['id']}", headers=auth(org.company_admin))).json()
    assert row["monthly_amount"] == 280_000 and row["won_amount"] == 0
    assert row["status"] == "development"  # already delivering: status unchanged


async def test_multiple_roles(client: AsyncClient, org: Org) -> None:
    r = await client.patch(
        f"/api/users/{org.member.id}",
        json={"roles": ["sales", "pmo", "sales"], "unit_cost": 45000},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 200
    assert r.json()["roles"] == ["sales", "pmo"] and r.json()["unit_cost"] == 45000
    me = (await client.get("/api/auth/me", headers=auth(org.member))).json()
    assert me["roles"] == ["sales", "pmo"] and me["can_sell"] and me["can_see_customers"]
    # BP users get no role, sales included.
    r = await client.patch(
        f"/api/users/{org.bp.id}", json={"roles": ["sales"]}, headers=auth(org.group_admin)
    )
    assert r.status_code == 422
    # A company admin cannot take group admin away either.
    r = await client.patch(
        f"/api/users/{org.group_admin.id}", json={"roles": []}, headers=auth(org.company_admin)
    )
    assert r.status_code == 403
    r = await client.post(
        "/api/invitations",
        json={
            "email": "new@example.com",
            "company_id": str(org.parent.id),
            "roles": ["accounting"],
        },
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201 and r.json()["roles"] == ["accounting"]


async def test_unit_cost_hidden_from_other_company_admin(client: AsyncClient, org: Org) -> None:
    await client.patch(
        f"/api/users/{org.member.id}", json={"unit_cost": 40000}, headers=auth(org.company_admin)
    )
    rows = (
        await client.get(f"/api/users?company_id={org.parent.id}", headers=auth(org.group_admin))
    ).json()
    assert next(u for u in rows if u["email"] == "m@example.com")["unit_cost"] == 40000
