"""Recommended upgrade version per vulnerable package."""

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.package import Package, VulnMatch
from app.services.upgrade import Bump, Upgrade, bump_kind, recommend
from tests.conftest import Org, auth
from tests.test_scanner import setup_project


@pytest.mark.parametrize(
    ("current", "target", "bump"),
    [
        ("4.17.15", "4.17.21", Bump.patch),
        ("4.17.15", "4.18.0", Bump.minor),
        ("4.17.15", "5.0.0", Bump.major),
        ("0.3.1", "0.3.4", Bump.patch),
        ("0.3.1", "0.4.0", Bump.major),  # 0.x minor releases are breaking
        ("v1.2.3", "v1.3.0", Bump.minor),  # Go
        ("2.0", "2.0.1", Bump.patch),
        ("abc", "def", Bump.unknown),
    ],
)
def test_bump_kind(current: str, target: str, bump: Bump) -> None:
    assert bump_kind(current, target) == bump


def test_recommend_takes_the_highest_fix() -> None:
    assert recommend("4.17.15", ["4.17.19", "4.17.21", "4.17.16"]) == Upgrade(
        version="4.17.21", bump=Bump.patch, unfixed=0
    )


def test_recommend_compares_versions_not_strings() -> None:
    assert recommend("1.9.0", ["1.10.0", "1.9.5"]) == Upgrade("1.10.0", Bump.minor, 0)


def test_recommend_counts_vulns_without_a_fix() -> None:
    assert recommend("1.0.0", ["1.0.2", None]) == Upgrade("1.0.2", Bump.patch, 1)
    assert recommend("1.0.0", [None, None]) == Upgrade(None, None, 2)


def test_recommend_ignores_fixes_not_above_current() -> None:
    # pick_fixed falls back to the highest fix when none is newer.
    assert recommend("3.0.0", ["2.9.9"]) == Upgrade(None, None, 1)


def test_recommend_none_without_vulns() -> None:
    assert recommend("1.0.0", []) is None


async def test_upgrade_in_package_and_match_lists(
    client: AsyncClient, session: AsyncSession, org: Org
) -> None:
    pid = await setup_project(client, session, org)
    lodash = (await session.exec(select(Package).where(Package.name == "lodash"))).one()
    session.add(VulnMatch(package_id=lodash.id, vuln_id="A", fixed_version="4.17.19"))
    session.add(VulnMatch(package_id=lodash.id, vuln_id="B", fixed_version="4.17.21"))
    session.add(VulnMatch(package_id=lodash.id, vuln_id="C", fixed_version=None, status="ack"))
    session.add(
        VulnMatch(package_id=lodash.id, vuln_id="D", fixed_version="5.0.0", status="ignored")
    )
    await session.commit()

    r = await client.get(f"/api/projects/{pid}/packages", headers=auth(org.member))
    by_name = {p["name"]: p for p in r.json()}
    assert by_name["lodash"]["upgrade"] == {"version": "4.17.21", "bump": "patch", "unfixed": 1}
    assert by_name["react"]["upgrade"] is None

    r = await client.get(f"/api/vulnerabilities?project_id={pid}", headers=auth(org.member))
    assert {m["vuln_id"]: m["upgrade"]["version"] for m in r.json()} == {
        "A": "4.17.21",
        "B": "4.17.21",
    }

    # Ignoring B lowers the recommendation to what A alone needs.
    b = next(m for m in r.json() if m["vuln_id"] == "B")
    r = await client.patch(
        f"/api/vulnerabilities/{b['id']}", json={"status": "ignored"}, headers=auth(org.member)
    )
    assert r.status_code == 200
    assert r.json()["upgrade"] == {"version": "4.17.19", "bump": "patch", "unfixed": 1}
