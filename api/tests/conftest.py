"""Fixtures: in-memory SQLite (FKs enforced) + ASGI client sharing one session."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.models  # noqa: F401
from app.core.auth import create_access_token
from app.core.config import settings
from app.core.database import get_session
from app.core.security import hash_password
from app.main import app
from app.models.organization import Company, CompanyType, Department, UserDepartment
from app.models.user import User, UserRole

settings.scan_on_change = False
settings.secret_key = "test-secret-key-that-is-long-enough-for-hs256"
settings.mail_backend = "none"


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_conn: object, _record: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def override() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@dataclass
class Org:
    parent: Company
    affiliate: Company
    partner: Company
    dev: Department  # parent > 開発本部
    dev1: Department  # parent > 開発本部 > 第1開発部
    sales: Department  # parent > 営業部
    group_admin: User
    company_admin: User  # parent company admin
    affiliate_admin: User
    head: User  # head of 開発本部
    member: User  # parent member in 第1開発部
    bp: User  # partner user


MakeUser = Callable[..., Awaitable[User]]


@pytest.fixture
def make_user(session: AsyncSession) -> MakeUser:
    async def _make(
        email: str,
        company: Company | None,
        role: UserRole = UserRole.member,
        departments: list[tuple[Department, bool]] | None = None,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hash_password("password123"),
            role=role,
            company_id=company.id if company else None,
        )
        session.add(user)
        await session.flush()
        for i, (dept, is_head) in enumerate(departments or []):
            session.add(
                UserDepartment(
                    user_id=user.id, department_id=dept.id, is_primary=i == 0, is_head=is_head
                )
            )
        await session.commit()
        return user

    return _make


@pytest.fixture
async def org(session: AsyncSession, make_user: MakeUser) -> Org:
    parent = Company(name="親会社", type=CompanyType.parent)
    affiliate = Company(name="関連会社", type=CompanyType.affiliate)
    partner = Company(name="BP社", type=CompanyType.partner)
    session.add_all([parent, affiliate, partner])
    await session.flush()
    dev = Department(company_id=parent.id, name="開発本部")
    sales = Department(company_id=parent.id, name="営業部")
    session.add_all([dev, sales])
    await session.flush()
    dev1 = Department(company_id=parent.id, parent_id=dev.id, name="第1開発部")
    session.add(dev1)
    await session.commit()
    return Org(
        parent=parent,
        affiliate=affiliate,
        partner=partner,
        dev=dev,
        dev1=dev1,
        sales=sales,
        group_admin=await make_user("ga@example.com", parent, UserRole.group_admin),
        company_admin=await make_user("ca@example.com", parent, UserRole.company_admin),
        affiliate_admin=await make_user("aa@example.com", affiliate, UserRole.company_admin),
        head=await make_user("head@example.com", parent, departments=[(dev, True)]),
        member=await make_user("m@example.com", parent, departments=[(dev1, False)]),
        bp=await make_user("bp@example.com", partner),
    )


async def make_project(
    client: AsyncClient, user: User, name: str = "P", department_id: UUID | None = None
) -> dict:  # type: ignore[type-arg]
    body: dict[str, object] = {"name": name}
    if department_id:
        body["department_id"] = str(department_id)
    r = await client.post("/api/projects", json=body, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]
