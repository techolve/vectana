"""End-of-life tracking via endoflife.date (https://endoflife.date/docs/api/v1/).

Packages are matched to products through the purl index (e.g. pkg:npm/next ->
nextjs), so no hand-written mapping is needed. Runtimes are registered by
product id directly. The version is matched to the longest release cycle it
belongs to ("16.4.3" -> "16", "3.14.2" -> "3.14").
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.eol import AppSettings, EolFinding, EolStatus, Runtime
from app.models.package import Package

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, Any]] = {}


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    now = time.monotonic()
    hit = _cache.get(path)
    if hit and now - hit[0] < settings.eol_cache_ttl_seconds:
        return hit[1]
    response = await client.get(f"{settings.eol_base_url}{path}")
    if response.status_code == 404:
        _cache[path] = (now, None)
        return None
    response.raise_for_status()
    data = response.json().get("result")
    _cache[path] = (now, data)
    return data


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.eol_timeout_seconds)


# --- Product catalog -----------------------------------------------------------


async def list_products(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    return list(await _get(client, "/products") or [])


async def get_product(client: httpx.AsyncClient, name: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await _get(client, f"/products/{quote(name)}")
    return result


async def purl_index(client: httpx.AsyncClient) -> dict[str, str]:
    """purl (without version) -> product name."""
    rows = await _get(client, "/identifiers/purl") or []
    return {row["identifier"].lower(): row["product"]["name"] for row in rows}


PURL_TYPES = {
    "npm": "npm",
    "PyPI": "pypi",
    "Pub": "pub",
    "Maven": "maven",
    "Go": "golang",
    "crates.io": "cargo",
    "RubyGems": "gem",
    "Packagist": "composer",
    "NuGet": "nuget",
}


def package_purl(ecosystem: str, name: str) -> str | None:
    kind = PURL_TYPES.get(ecosystem)
    if kind is None:
        return None
    if ecosystem == "npm":
        name = name.replace("@", "%40", 1) if name.startswith("@") else name
    elif ecosystem == "PyPI":
        name = name.lower().replace("_", "-").replace(".", "-")
    elif ecosystem == "Maven":
        name = name.replace(":", "/", 1)
    return f"pkg:{kind}/{name}".lower()


# --- Matching ------------------------------------------------------------------


@dataclass
class Evaluation:
    product: str
    label: str
    cycle: str | None
    eol_date: date | None
    latest: str | None
    status: str


def match_release(releases: list[dict[str, Any]], version: str) -> dict[str, Any] | None:
    """Release whose cycle name is the longest prefix of ``version``."""
    v = version.strip().lstrip("vV")
    best: dict[str, Any] | None = None
    for release in releases:
        name = str(release.get("name", ""))
        if name and (v == name or v.startswith(name + ".")):
            if best is None or len(name) > len(str(best["name"])):
                best = release
    return best


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def evaluate(product: dict[str, Any], version: str, warning_days: int, today: date) -> Evaluation:
    release = match_release(product.get("releases") or [], version)
    label = str(product.get("label") or product.get("name"))
    if release is None:
        return Evaluation(product["name"], label, None, None, None, EolStatus.unknown)
    eol_date = _parse_date(release.get("eolFrom"))
    if release.get("isEol") or (eol_date is not None and eol_date <= today):
        status = EolStatus.eol
    elif eol_date is not None and eol_date <= today + timedelta(days=warning_days):
        status = EolStatus.approaching
    else:
        status = EolStatus.supported
    latest = (release.get("latest") or {}).get("name")
    return Evaluation(product["name"], label, str(release["name"]), eol_date, latest, status)


async def warning_days(session: AsyncSession) -> int:
    row = await session.get(AppSettings, 1)
    return row.eol_warning_days if row else 90


# --- Recompute -----------------------------------------------------------------


async def refresh(
    session: AsyncSession,
    project_ids: list[UUID] | None = None,
    client: httpx.AsyncClient | None = None,
    today: date | None = None,
) -> int:
    """Recompute EOL findings for the given projects (all when None).
    Returns how many findings changed status."""
    today = today or datetime.now(UTC).date()
    days = await warning_days(session)
    own_client = client is None
    client = client or make_client()
    try:
        index = await purl_index(client)

        pkg_query = select(Package)
        rt_query = select(Runtime)
        old_query = select(EolFinding)
        if project_ids is not None:
            pkg_query = pkg_query.where(col(Package.project_id).in_(project_ids))
            rt_query = rt_query.where(col(Runtime.project_id).in_(project_ids))
            old_query = old_query.where(col(EolFinding.project_id).in_(project_ids))
        packages = list((await session.exec(pkg_query)).all())
        runtimes = list((await session.exec(rt_query)).all())
        existing: dict[tuple[UUID | None, str], EolFinding] = {
            (f.package_id or f.runtime_id, f.product): f
            for f in (await session.exec(old_query)).all()
        }

        # (source id, project id, package id, runtime id, product, version)
        targets: list[tuple[UUID, UUID, UUID | None, UUID | None, str, str]] = []
        for p in packages:
            purl = package_purl(p.ecosystem, p.name)
            product = index.get(purl) if purl else None
            if product:
                targets.append((p.id, p.project_id, p.id, None, product, p.version))
        for r in runtimes:
            targets.append((r.id, r.project_id, None, r.id, r.product, r.version))

        now = datetime.now(UTC)
        seen: set[tuple[UUID | None, str]] = set()
        changed = 0
        for source_id, project_id, package_id, runtime_id, product_name, version in targets:
            try:
                product_data = await get_product(client, product_name)
            except Exception:
                logger.exception("endoflife.date lookup failed for %s", product_name)
                seen |= {(source_id, product_name)}  # keep the previous result
                continue
            if product_data is None:
                continue
            result = evaluate(product_data, version, days, today)
            key = (source_id, result.product)
            seen.add(key)
            finding = existing.get(key) or EolFinding(
                project_id=project_id,
                package_id=package_id,
                runtime_id=runtime_id,
                product=result.product,
                product_label=result.label,
                version=version,
            )
            if finding.status != result.status:
                finding.status_changed_at = now
                changed += 1
            finding.product_label = result.label
            finding.version = version
            finding.cycle = result.cycle
            finding.eol_date = result.eol_date
            finding.latest = result.latest
            finding.status = result.status
            finding.checked_at = now
            session.add(finding)

        for old_key, stale in existing.items():
            if old_key not in seen:
                await session.delete(stale)
        await session.commit()
    finally:
        if own_client:
            await client.aclose()
    logger.info("EOL refreshed: %d target(s), %d status change(s)", len(targets), changed)
    return changed
