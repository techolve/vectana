"""Match registered packages against OSV and record new vulnerabilities.

Idempotent: a (package, vulnerability) pair is inserted at most once
(``vuln_matches`` unique constraint), so re-running a scan never duplicates
matches or notifications.
"""

import asyncio
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.package import Package, VulnMatch
from app.services import osv

logger = logging.getLogger(__name__)

_DETAIL_CONCURRENCY = 8


def _norm(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


async def scan(
    session: AsyncSession,
    package_ids: Iterable[UUID] | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[UUID]:
    """Scan packages (all when ``package_ids`` is None). Returns new match ids."""
    query = select(Package)
    if package_ids is not None:
        ids = list(package_ids)
        if not ids:
            return []
        query = query.where(col(Package.id).in_(ids))
    packages = list((await session.exec(query)).all())
    if not packages:
        return []

    own_client = client is None
    client = client or osv.make_client()
    try:
        results = await osv.query_batch(
            client, [osv.Query(p.ecosystem, p.name, p.version) for p in packages]
        )
        existing = {
            (m.package_id, m.vuln_id)
            for m in (
                await session.exec(
                    select(VulnMatch).where(col(VulnMatch.package_id).in_([p.id for p in packages]))
                )
            ).all()
        }
        pending = [
            (pkg, vuln_id)
            for pkg, vuln_ids in zip(packages, results, strict=True)
            for vuln_id in vuln_ids
            if (pkg.id, vuln_id) not in existing
        ]

        semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

        async def fetch(vuln_id: str) -> osv.VulnDetail | None:
            async with semaphore:
                try:
                    return await osv.get_vuln(client, vuln_id)
                except Exception:
                    logger.exception("Failed to fetch OSV detail for %s", vuln_id)
                    return None

        unique_ids = sorted({v for _, v in pending})
        details = dict(
            zip(
                unique_ids,
                await asyncio.gather(*(fetch(v) for v in unique_ids)),
                strict=True,
            )
        )
    finally:
        if own_client:
            await client.aclose()

    new_ids: list[UUID] = []
    for pkg, vuln_id in pending:
        detail = details.get(vuln_id)
        if detail is None:
            continue  # retried on the next scan
        fixed = None
        for (eco, name), versions in detail.fixed_versions.items():
            if eco == pkg.ecosystem and _norm(name) == _norm(pkg.name):
                fixed = osv.pick_fixed(versions, pkg.version)
                break
        match = VulnMatch(
            package_id=pkg.id,
            vuln_id=vuln_id,
            aliases=detail.aliases,
            summary=detail.summary,
            severity=detail.severity,
            cvss_score=detail.cvss_score,
            fixed_version=fixed,
        )
        session.add(match)
        new_ids.append(match.id)

    now = datetime.now(UTC)
    for pkg in packages:
        pkg.last_scanned_at = now
        session.add(pkg)
    await session.commit()
    logger.info("Scanned %d package(s): %d new match(es)", len(packages), len(new_ids))
    return new_ids


async def scan_and_notify(
    package_ids: Iterable[UUID] | None = None,
    project_ids: Iterable[UUID] | None = None,
) -> int:
    """Entry point for the worker and for on-change scans. Uses its own session.

    With no arguments everything is scanned. ``package_ids`` scans those packages
    (and refreshes EOL for their projects); ``project_ids`` refreshes EOL only.
    """
    from app.services import eol
    from app.services.notify import notify_pending

    pkg_list = list(package_ids) if package_ids is not None else None
    proj_list = list(project_ids) if project_ids is not None else None
    async with AsyncSessionLocal() as session:
        if pkg_list is not None or proj_list is None:
            try:
                await scan(session, pkg_list)
            except Exception:
                logger.exception("Scan failed")
                await session.rollback()

        eol_projects: list[UUID] | None = None
        if pkg_list is not None or proj_list is not None:
            ids = set(proj_list or [])
            if pkg_list:
                ids |= set(
                    (
                        await session.exec(
                            select(Package.project_id).where(col(Package.id).in_(pkg_list))
                        )
                    ).all()
                )
            eol_projects = list(ids)
        if eol_projects is None or eol_projects:
            try:
                await eol.refresh(session, eol_projects)
            except Exception:
                logger.exception("EOL refresh failed")
                await session.rollback()
        return await notify_pending(session)
