from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.invitation import Invitation
from app.models.organization import UserDepartment
from app.models.user import User
from tests.conftest import Org, auth


async def test_login_and_me(client: AsyncClient, org: Org) -> None:
    r = await client.post(
        "/api/auth/login", json={"email": "HEAD@example.com", "password": "password123"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    body = me.json()
    assert body["company_name"] == "親会社"
    assert body["can_manage_org"] is False
    # Head of 開発本部 manages it and its sub-department.
    assert set(body["managed_department_ids"]) == {str(org.dev.id), str(org.dev1.id)}


async def test_login_wrong_password(client: AsyncClient, org: Org) -> None:
    r = await client.post("/api/auth/login", json={"email": "m@example.com", "password": "nope"})
    assert r.status_code == 401


async def test_bp_me_is_partner(client: AsyncClient, org: Org) -> None:
    me = (await client.get("/api/auth/me", headers=auth(org.bp))).json()
    assert me["is_partner"] is True


async def test_invitation_flow(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    r = await client.post(
        "/api/invitations",
        json={
            "email": "New@Example.com",
            "company_id": str(org.parent.id),
            "role": "member",
            "departments": [
                {"department_id": str(org.dev1.id), "is_primary": True},
                {"department_id": str(org.sales.id), "is_head": True},
            ],
        },
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201, r.text
    url = r.json()["accept_url"]
    token = url.split("token=")[1]

    preview = await client.get(f"/api/auth/invitations/{token}")
    assert preview.json() == {
        "locale": "ja",
        "email": "new@example.com",
        "display_name": None,
        "company_name": "親会社",
    }

    r = await client.post(
        "/api/auth/invitations/accept",
        json={"token": token, "password": "password123", "display_name": "新人"},
    )
    assert r.status_code == 200
    user = (await session.exec(select(User).where(User.email == "new@example.com"))).one()
    assert user.company_id == org.parent.id
    links = (
        await session.exec(select(UserDepartment).where(UserDepartment.user_id == user.id))
    ).all()
    assert {(link.department_id, link.is_primary, link.is_head) for link in links} == {
        (org.dev1.id, True, False),
        (org.sales.id, False, True),
    }

    # Single use.
    again = await client.post(
        "/api/auth/invitations/accept", json={"token": token, "password": "password123"}
    )
    assert again.status_code == 404


async def test_invitation_expired(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    session.add(
        Invitation(
            email="late@example.com",
            company_id=org.parent.id,
            role="member",
            token="expired-token",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await session.commit()
    r = await client.get("/api/auth/invitations/expired-token")
    assert r.status_code == 410


async def test_notification_prefs(client: AsyncClient, org: Org) -> None:
    h = auth(org.member)
    assert (await client.get("/api/auth/notifications", headers=h)).json() == {
        "email_enabled": True,
        "min_severity": "LOW",
    }
    r = await client.put(
        "/api/auth/notifications",
        json={"email_enabled": False, "min_severity": "HIGH"},
        headers=h,
    )
    assert r.status_code == 200
    assert (await client.get("/api/auth/notifications", headers=h)).json()["min_severity"] == "HIGH"


async def test_health_reports_version(client: AsyncClient) -> None:
    from app import __version__

    assert (await client.get("/api/health")).json() == {"status": "ok", "version": __version__}
