"""Recommend the version a vulnerable package should be upgraded to.

For each package we take the fixed version of every unresolved vulnerability
(``fixed_version`` is already the smallest fix above the installed version, see
``osv.pick_fixed``) and recommend the highest of them: the lowest version that
fixes all of them at once. This is a guide, not a guarantee: advisories only
list where each fix landed, not every later version that still carries it.
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.package import MatchStatus, VulnMatch
from app.services.osv import _version_key


class Bump(StrEnum):
    patch = "patch"
    minor = "minor"
    major = "major"
    unknown = "unknown"  # versions we cannot split into numbers


@dataclass(frozen=True)
class Upgrade:
    # None when no unresolved vulnerability has a known fix.
    version: str | None
    bump: Bump | None
    # Unresolved vulnerabilities this upgrade does not fix (no fix published).
    unfixed: int


_NUMERIC = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parts(version: str) -> tuple[int, int, int] | None:
    m = _NUMERIC.match(version.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def bump_kind(current: str, target: str) -> Bump:
    """How big the jump is. Below 1.0 a minor bump counts as major: npm, Cargo
    and most semver tooling treat 0.x minor releases as breaking."""
    cur, new = _parts(current), _parts(target)
    if cur is None or new is None:
        return Bump.unknown
    if new[0] != cur[0] or (cur[0] == 0 and new[1] != cur[1]):
        return Bump.major
    if new[1] != cur[1]:
        return Bump.minor
    return Bump.patch


def _newer(candidate: str, current: str) -> bool:
    a, b = _version_key(candidate), _version_key(current)
    if a[0] == b[0] == 1:
        return a > b
    pa, pb = _parts(candidate), _parts(current)
    if pa is not None and pb is not None:
        return pa > pb
    return candidate != current


def recommend(current: str, fixed_versions: Iterable[str | None]) -> Upgrade | None:
    """``fixed_versions`` holds one entry per unresolved vulnerability."""
    fixes = list(fixed_versions)
    if not fixes:
        return None
    usable = [f for f in fixes if f and _newer(f, current)]
    unfixed = len(fixes) - len(usable)
    if not usable:
        return Upgrade(version=None, bump=None, unfixed=unfixed)
    target = max(usable, key=lambda v: (_version_key(v), _parts(v) or (0, 0, 0)))
    return Upgrade(version=target, bump=bump_kind(current, target), unfixed=unfixed)


async def for_packages(session: AsyncSession, versions: dict[UUID, str]) -> dict[UUID, Upgrade]:
    """Upgrades for packages (id -> installed version). Ignored vulnerabilities
    do not count; open and acknowledged ones do."""
    if not versions:
        return {}
    rows = (
        await session.exec(
            select(VulnMatch.package_id, VulnMatch.fixed_version).where(
                col(VulnMatch.package_id).in_(list(versions)),
                VulnMatch.status != MatchStatus.ignored,
            )
        )
    ).all()
    fixes: dict[UUID, list[str | None]] = defaultdict(list)
    for package_id, fixed in rows:
        fixes[package_id].append(fixed)
    result: dict[UUID, Upgrade] = {}
    for package_id, fixed_list in fixes.items():
        upgrade = recommend(versions[package_id], fixed_list)
        if upgrade is not None:
            result[package_id] = upgrade
    return result
