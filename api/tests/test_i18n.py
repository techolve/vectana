from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.i18n import normalize, translate_error
from app.models.user import User
from tests.conftest import Org, auth


def test_normalize() -> None:
    assert normalize("en-US,en;q=0.9") == "en"
    assert normalize("ja") == "ja"
    assert normalize("fr") == "ja"
    assert normalize(None) == "ja"


def test_translate_patterns() -> None:
    assert translate_error("Project not found", "ja") == "プロジェクトが見つかりません"
    assert translate_error("Project not found", "en") == "Project not found"
    assert translate_error("Webhook failed: boom", "ja") == "Webhook の送信に失敗しました: boom"
    assert translate_error("something new", "ja") == "something new"


async def test_errors_follow_accept_language(client: AsyncClient, org: Org) -> None:
    body = {"email": "x@example.com", "password": "nope"}
    ja = await client.post("/api/auth/login", json=body, headers={"Accept-Language": "ja"})
    en = await client.post("/api/auth/login", json=body, headers={"Accept-Language": "en"})
    assert ja.json()["detail"] == "メールアドレスまたはパスワードが違います"
    assert en.json()["detail"] == "Invalid credentials"


async def test_validation_errors_are_one_line(client: AsyncClient, org: Org) -> None:
    r = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/packages",
        json={"ecosystem": "npm", "name": "", "version": "1"},
        headers={**auth(org.member), "Accept-Language": "ja"},
    )
    assert r.status_code == 422
    assert r.json()["detail"].startswith("入力内容が正しくありません (name:")


async def test_save_locale(client: AsyncClient, org: Org) -> None:
    h = auth(org.member)
    assert (await client.get("/api/auth/me", headers=h)).json()["locale"] == "ja"
    assert (
        await client.put("/api/auth/locale", json={"locale": "en"}, headers=h)
    ).status_code == 204
    assert (await client.get("/api/auth/me", headers=h)).json()["locale"] == "en"
    assert (
        await client.put("/api/auth/locale", json={"locale": "fr"}, headers=h)
    ).status_code == 422


async def test_invitation_locale(client: AsyncClient, session: AsyncSession, org: Org) -> None:
    r = await client.post(
        "/api/invitations",
        json={"email": "en@example.com", "company_id": str(org.parent.id)},
        headers={**auth(org.company_admin), "Accept-Language": "en"},
    )
    inv = r.json()
    assert inv["locale"] == "en"
    assert "/en/invite/?token=" in inv["accept_url"]
    token = inv["accept_url"].split("token=")[1]
    await client.post(
        "/api/auth/invitations/accept", json={"token": token, "password": "password123"}
    )
    user = (await session.exec(select(User).where(User.email == "en@example.com"))).one()
    assert user.locale == "en"
