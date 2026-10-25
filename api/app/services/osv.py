"""OSV.dev API client (https://google.github.io/osv.dev/api/)."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from cvss import CVSS3, CVSS4
from packaging.version import InvalidVersion, Version

from app.core.config import settings
from app.models.package import Severity

logger = logging.getLogger(__name__)

BATCH_LIMIT = 1000


@dataclass(frozen=True)
class Query:
    ecosystem: str
    name: str
    version: str


@dataclass
class VulnDetail:
    id: str
    summary: str | None
    aliases: list[str] = field(default_factory=list)
    severity: str = Severity.UNKNOWN
    cvss_score: float | None = None
    fixed_versions: dict[tuple[str, str], list[str]] = field(default_factory=dict)


async def _request(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> Any:
    delay = 1.0
    for attempt in range(settings.osv_max_retries + 1):
        try:
            response = await client.request(method, f"{settings.osv_base_url}{path}", **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"OSV returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                exc.response.status_code == 429 or exc.response.status_code >= 500
            )
            if not retryable or attempt == settings.osv_max_retries:
                raise
            logger.warning("OSV %s %s failed (%s); retrying", method, path, exc)
            await asyncio.sleep(delay)
            delay *= 2


async def query_batch(client: httpx.AsyncClient, queries: list[Query]) -> list[list[str]]:
    """Return, for each query, the ids of vulnerabilities affecting that version."""
    results: list[list[str]] = []
    for start in range(0, len(queries), BATCH_LIMIT):
        chunk = queries[start : start + BATCH_LIMIT]
        body = {
            "queries": [
                {
                    "package": {"ecosystem": q.ecosystem, "name": q.name},
                    "version": q.version,
                }
                for q in chunk
            ]
        }
        data = await _request(client, "POST", "/v1/querybatch", json=body)
        for item in data.get("results", []):
            ids = [v["id"] for v in item.get("vulns", []) or []]
            if item.get("next_page_token"):
                logger.warning("OSV result truncated (more than one page of vulns)")
            results.append(ids)
    return results


def _score_from_vector(vector: str) -> float | None:
    try:
        if vector.startswith("CVSS:4"):
            return float(CVSS4(vector).base_score)
        if vector.startswith("CVSS:3"):
            return float(CVSS3(vector).scores()[0])
    except Exception:
        logger.debug("Could not parse CVSS vector %r", vector)
    return None


def _severity_from_score(score: float) -> str:
    if score >= 9.0:
        return Severity.CRITICAL
    if score >= 7.0:
        return Severity.HIGH
    if score >= 4.0:
        return Severity.MEDIUM
    if score > 0:
        return Severity.LOW
    return Severity.UNKNOWN


def parse_vuln(data: dict[str, Any]) -> VulnDetail:
    detail = VulnDetail(
        id=data["id"],
        summary=data.get("summary") or (data.get("details") or "")[:300] or None,
        aliases=list(data.get("aliases") or []),
    )

    scores = [
        s
        for s in (_score_from_vector(sev.get("score", "")) for sev in data.get("severity") or [])
        if s is not None
    ]
    if scores:
        detail.cvss_score = max(scores)
        detail.severity = _severity_from_score(detail.cvss_score)

    # GHSA advisories carry a textual severity; prefer it when present.
    textual = str((data.get("database_specific") or {}).get("severity") or "").upper()
    if textual == "MODERATE":
        textual = Severity.MEDIUM
    if textual in Severity.__members__ and textual != Severity.UNKNOWN:
        detail.severity = textual

    for affected in data.get("affected") or []:
        pkg = affected.get("package") or {}
        key = (pkg.get("ecosystem", ""), pkg.get("name", ""))
        fixed = [
            event["fixed"]
            for r in affected.get("ranges") or []
            for event in r.get("events") or []
            if "fixed" in event
        ]
        if fixed:
            detail.fixed_versions.setdefault(key, []).extend(fixed)
    return detail


async def get_vuln(client: httpx.AsyncClient, vuln_id: str) -> VulnDetail:
    return parse_vuln(await _request(client, "GET", f"/v1/vulns/{vuln_id}"))


def _version_key(v: str) -> tuple[int, Version | str]:
    try:
        return (1, Version(v))
    except InvalidVersion:
        return (0, v)


def pick_fixed(candidates: list[str], current: str) -> str | None:
    """The smallest fixed version above ``current`` (fixes exist per release line)."""
    if not candidates:
        return None
    ordered = sorted(set(candidates), key=_version_key)
    cur = _version_key(current)
    for c in ordered:
        key = _version_key(c)
        if key[0] == cur[0] == 1 and key > cur:
            return c
    return ordered[-1]


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.osv_timeout_seconds)
