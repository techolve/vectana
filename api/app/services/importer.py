"""Import a dependency file into a project: a lockfile or SBOM (packages), or
mise.toml / .tool-versions (runtimes). Used by the upload endpoint and by
repository imports.

Re-importing under the same source name replaces what that source previously
contributed; manual entries and other sources are untouched."""

from dataclasses import dataclass, field
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.eol import Runtime
from app.models.package import Package
from app.schemas.project import ImportResult, SkippedTool
from app.services import eol, lockfile, toolfile
from app.services import tasks as security_tasks

MAX_BYTES = 10 * 1024 * 1024


class ImportFailed(ValueError):
    """The file is not supported or could not be parsed."""


@dataclass
class Imported:
    result: ImportResult
    added_package_ids: list[UUID] = field(default_factory=list)
    runtimes_changed: bool = False
    # Packages the file lists, and the source they are recorded under.
    packages: set[tuple[str, str, str]] = field(default_factory=set)
    source_key: str | None = None


def is_supported(path: str) -> bool:
    """Files picked up by name (SBOMs, picked by content, are matched by the
    usual SBOM file names)."""
    base = path.rsplit("/", 1)[-1]
    if toolfile.is_tool_file(base) or lockfile._lockfile_parser(base) is not None:
        return True
    lower = base.lower()
    return lower.endswith((".cdx.json", ".cdx.xml", ".spdx.json", ".spdx")) or lower in {
        "bom.json",
        "bom.xml",
        "sbom.json",
    }


async def import_file(
    session: AsyncSession,
    project_id: UUID,
    filename: str,
    raw: bytes,
    source: str | None = None,
) -> Imported:
    """Commits. The caller schedules a scan of ``added_package_ids`` (or of
    the project's runtimes when ``runtimes_changed``)."""
    if toolfile.is_tool_file(filename):
        return await _import_tool_file(session, project_id, filename, raw, source)
    try:
        parsed = lockfile.parse(filename, raw.decode("utf-8"))
    except lockfile.UnsupportedLockfile as exc:
        raise ImportFailed(str(exc)) from exc
    except Exception as exc:
        raise ImportFailed(f"Could not parse {filename}: {exc}") from exc

    source_key = f"{parsed.kind}:{source or filename}"
    existing = list(
        (await session.exec(select(Package).where(Package.project_id == project_id))).all()
    )
    by_key = {(p.ecosystem, p.name, p.version): p for p in existing}
    wanted = set(parsed.packages)

    removed = 0
    for p in existing:
        if p.source == source_key and (p.ecosystem, p.name, p.version) not in wanted:
            await session.delete(p)
            removed += 1
    added: list[Package] = []
    for ecosystem, name, version in parsed.packages:
        if (ecosystem, name, version) in by_key:
            continue
        pkg = Package(
            project_id=project_id,
            ecosystem=ecosystem,
            name=name,
            version=version,
            source=source_key,
        )
        session.add(pkg)
        added.append(pkg)
    await session.commit()
    if removed:
        # Upgraded packages drop their old versions: complete what they fixed.
        await security_tasks.sync(session, [project_id])
    return Imported(
        result=ImportResult(
            filename=filename,
            format=parsed.format,
            ecosystem=", ".join(parsed.ecosystems) or parsed.format,
            added=len(added),
            removed=removed,
            total=len(wanted),
            unsupported=parsed.unsupported,
        ),
        added_package_ids=[p.id for p in added],
        packages=wanted,
        source_key=source_key,
    )


async def _import_tool_file(
    session: AsyncSession,
    project_id: UUID,
    filename: str,
    raw: bytes,
    source_name: str | None,
) -> Imported:
    try:
        entries = toolfile.parse(filename, raw.decode("utf-8"))
    except Exception as exc:
        raise ImportFailed(f"Could not parse {filename}: {exc}") from exc
    async with eol.make_client() as client:
        index = toolfile.product_index(await eol.list_products(client))
    known = set(index.values())

    wanted: set[tuple[str, str]] = set()
    skipped: list[SkippedTool] = []
    for entry in entries:
        res = toolfile.resolve(entry, index)
        if res.product is None or res.product not in known:
            reason = res.reason or "unsupported"
            skipped.append(SkippedTool(tool=res.tool, version=res.version, reason=reason))
        else:
            wanted.add((res.product, res.version))

    source = f"file:{source_name or filename}"
    existing = list(
        (await session.exec(select(Runtime).where(Runtime.project_id == project_id))).all()
    )
    have = {(r.product, r.version) for r in existing}
    removed = 0
    for r in existing:
        if r.source == source and (r.product, r.version) not in wanted:
            await session.delete(r)
            removed += 1
    added = 0
    for product, version in sorted(wanted - have):
        session.add(Runtime(project_id=project_id, product=product, version=version, source=source))
        added += 1
    await session.commit()
    return Imported(
        result=ImportResult(
            filename=filename,
            kind="runtimes",
            ecosystem="endoflife.date",
            added=added,
            removed=removed,
            total=len(wanted),
            skipped=skipped,
        ),
        runtimes_changed=bool(added or removed),
    )
