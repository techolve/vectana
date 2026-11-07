"""Security tasks: one task per package (or runtime) upgrade.

Every unresolved vulnerability of a package and every EOL finding of a package
or runtime links to the task that resolves it (``task_id``). ``sync`` runs
after each scan and EOL refresh, and after triage changes:

- unlinked items join the open security task of the same subject;
- with no such task, one is created automatically when a vulnerability is at or
  above the project's threshold, or the package / runtime has reached EOL.
  Everything else waits as a candidate until someone presses タスク化;
- an open security task whose linked items are all resolved (fixed by an
  upgrade, ignored, or no longer EOL) is completed.

The task's own assignee and due date are the plan for the upgrade. Linked
vulnerabilities keep their own triage; when the task has no due date, it is
due when the earliest linked vulnerability is (its own due date, else the SLA).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import utcnow
from app.models.eol import EolFinding, EolStatus
from app.models.package import (
    SEVERITY_RANK,
    MatchStatus,
    Package,
    Severity,
    VulnMatch,
    meets_threshold,
)
from app.models.project import Project
from app.models.task import SecuritySubject, Task, TaskKind, TaskStatus
from app.services import orgstats, upgrade
from app.services.osv import _version_key

UNRESOLVED = (MatchStatus.open, MatchStatus.ack)
# EOL states that still need an upgrade.
EOL_PENDING = (EolStatus.eol, EolStatus.approaching)
RUNTIME_ECOSYSTEM = "runtime"

# (project id, subject, ecosystem, name)
Key = tuple[UUID, str, str, str]


def task_key(t: Task) -> Key:
    return (t.project_id, t.subject or "", t.subject_ecosystem or "", t.subject_name or "")


async def next_number(session: AsyncSession, project_id: UUID) -> int:
    current = (
        await session.exec(select(func.max(Task.number)).where(Task.project_id == project_id))
    ).one()
    return int(current or 0) + 1


async def next_position(session: AsyncSession, project_id: UUID) -> float:
    current = (
        await session.exec(select(func.max(Task.position)).where(Task.project_id == project_id))
    ).one()
    return float(current or 0) + 1


@dataclass
class Item:
    """An unresolved vulnerability or pending EOL finding, with its subject."""

    key: Key
    label: str
    match: VulnMatch | None = None
    finding: EolFinding | None = None


@dataclass
class Pending:
    matches: list[VulnMatch] = field(default_factory=list)
    findings: list[EolFinding] = field(default_factory=list)
    label: str = ""


async def _pending_items(
    session: AsyncSession, project_ids: list[UUID] | None, unlinked_only: bool
) -> dict[Key, Pending]:
    match_q = (
        select(VulnMatch, Package)
        .join(Package, col(Package.id) == col(VulnMatch.package_id))
        .where(col(VulnMatch.status).in_(UNRESOLVED))
    )
    finding_q = select(EolFinding).where(col(EolFinding.status).in_(EOL_PENDING))
    if project_ids is not None:
        match_q = match_q.where(col(Package.project_id).in_(project_ids))
        finding_q = finding_q.where(col(EolFinding.project_id).in_(project_ids))
    if unlinked_only:
        match_q = match_q.where(col(VulnMatch.task_id).is_(None))
        finding_q = finding_q.where(col(EolFinding.task_id).is_(None))

    groups: dict[Key, Pending] = defaultdict(Pending)
    for match, pkg in (await session.exec(match_q)).all():
        key = (pkg.project_id, SecuritySubject.package.value, pkg.ecosystem, pkg.name)
        groups[key].matches.append(match)
        groups[key].label = pkg.name

    findings = list((await session.exec(finding_q)).all())
    pkg_ids = {f.package_id for f in findings if f.package_id}
    packages = (
        {
            p.id: p
            for p in (await session.exec(select(Package).where(col(Package.id).in_(pkg_ids)))).all()
        }
        if pkg_ids
        else {}
    )
    for f in findings:
        owner = packages.get(f.package_id) if f.package_id else None
        if owner is not None:
            key = (f.project_id, SecuritySubject.package.value, owner.ecosystem, owner.name)
            label = owner.name
        else:
            key = (f.project_id, SecuritySubject.runtime.value, RUNTIME_ECOSYSTEM, f.product)
            label = f.product_label
        groups[key].findings.append(f)
        groups[key].label = groups[key].label or label
    return groups


async def open_security_tasks(
    session: AsyncSession, project_ids: list[UUID] | None
) -> dict[Key, Task]:
    q = select(Task).where(
        Task.kind == TaskKind.security,
        Task.status != TaskStatus.done,
        col(Task.subject).is_not(None),
    )
    if project_ids is not None:
        q = q.where(col(Task.project_id).in_(project_ids))
    tasks: dict[Key, Task] = {}
    # Oldest first so a duplicate (made by hand) never steals new links.
    for t in (await session.exec(q.order_by(col(Task.created_at).desc()))).all():
        tasks[task_key(t)] = t
    return tasks


def _new_task(key: Key, label: str, number: int, position: float, auto: bool) -> Task:
    project_id, subject, ecosystem, name = key
    return Task(
        project_id=project_id,
        number=number,
        kind=TaskKind.security,
        title=label or name,
        subject=subject,
        subject_ecosystem=ecosystem,
        subject_name=name,
        auto_created=auto,
        position=position,
    )


def _link(task: Task, group: Pending, session: AsyncSession) -> None:
    for m in group.matches:
        m.task_id = task.id
        session.add(m)
    for f in group.findings:
        f.task_id = task.id
        session.add(f)


def _should_auto_create(group: Pending, threshold: str) -> bool:
    if any(meets_threshold(m.severity, threshold) for m in group.matches):
        return True
    return any(f.status == EolStatus.eol for f in group.findings)


async def sync(session: AsyncSession, project_ids: list[UUID] | None = None) -> int:
    """Link, create and complete security tasks. Returns how many were created.
    Commits."""
    projects = select(Project.id, Project.security_threshold)
    if project_ids is not None:
        if not project_ids:
            return 0
        projects = projects.where(col(Project.id).in_(project_ids))
    thresholds = {pid: th for pid, th in (await session.exec(projects)).all()}

    open_tasks = await open_security_tasks(session, project_ids)
    groups = await _pending_items(session, project_ids, unlinked_only=True)
    numbers: dict[UUID, int] = {}
    positions: dict[UUID, float] = {}
    created = 0
    changed: list[Task] = []  # created or completed: their issues follow
    for key in sorted(groups, key=lambda k: (str(k[0]), k[1], k[2], k[3])):
        group = groups[key]
        project_id = key[0]
        task = open_tasks.get(key)
        if task is None:
            threshold = thresholds.get(project_id, Severity.HIGH.value)
            if not _should_auto_create(group, threshold):
                continue
            if project_id not in numbers:
                numbers[project_id] = await next_number(session, project_id)
                positions[project_id] = await next_position(session, project_id)
            task = _new_task(key, group.label, numbers[project_id], positions[project_id], True)
            numbers[project_id] += 1
            positions[project_id] += 1
            session.add(task)
            # Insert before linking: there is no ORM relationship to order it.
            await session.flush()
            open_tasks[key] = task
            created += 1
            changed.append(task)
        _link(task, group, session)
    await session.flush()

    # Complete tasks with nothing left to fix.
    task_ids = [t.id for t in open_tasks.values()]
    if task_ids:
        busy = set(
            (
                await session.exec(
                    select(VulnMatch.task_id).where(
                        col(VulnMatch.task_id).in_(task_ids),
                        col(VulnMatch.status).in_(UNRESOLVED),
                    )
                )
            ).all()
        ) | set(
            (
                await session.exec(
                    select(EolFinding.task_id).where(
                        col(EolFinding.task_id).in_(task_ids),
                        col(EolFinding.status).in_(EOL_PENDING),
                    )
                )
            ).all()
        )
        now = utcnow()
        for t in open_tasks.values():
            if t.id not in busy:
                t.status = TaskStatus.done
                t.progress = 100
                t.completed_at = now
                t.updated_at = now
                session.add(t)
                changed.append(t)
    await session.commit()
    if changed:
        from app.services.repo import sync as repo_sync

        for t in changed:
            await repo_sync.push_task(session, t)
    return created


@dataclass
class Candidate:
    key: Key
    label: str
    matches: list[VulnMatch]
    findings: list[EolFinding]


async def candidates(session: AsyncSession, project_id: UUID) -> list[Candidate]:
    """Unlinked items that wait for タスク化 (below the threshold, or approaching EOL)."""
    groups = await _pending_items(session, [project_id], unlinked_only=True)
    return [
        Candidate(key=k, label=g.label, matches=g.matches, findings=g.findings)
        for k, g in sorted(groups.items(), key=lambda kv: _candidate_order(kv[1]))
    ]


def _candidate_order(group: Pending) -> tuple[int, str]:
    worst = max(
        (SEVERITY_RANK.get(Severity(m.severity), 0) for m in group.matches if m.severity),
        default=-1,
    )
    return (-worst, group.label.lower())


async def create_for_subject(
    session: AsyncSession, project_id: UUID, subject: str, ecosystem: str, name: str
) -> Task | None:
    """タスク化: link every unlinked item of the subject to its open task, or to a
    new one. None when the subject has nothing to fix."""
    key: Key = (project_id, subject, ecosystem, name)
    groups = await _pending_items(session, [project_id], unlinked_only=True)
    group = groups.get(key)
    if group is None:
        return None
    task = (await open_security_tasks(session, [project_id])).get(key)
    if task is None:
        task = _new_task(
            key,
            group.label,
            await next_number(session, project_id),
            await next_position(session, project_id),
            False,
        )
        session.add(task)
        await session.flush()
    _link(task, group, session)
    await session.commit()
    return task


# --- Read side ---------------------------------------------------------------


@dataclass
class SecurityInfo:
    vuln_count: int = 0
    max_severity: str | None = None
    eol_status: str | None = None
    eol_date: date | None = None
    installed: list[str] = field(default_factory=list)
    upgrade: upgrade.Upgrade | None = None
    latest: str | None = None  # latest release of the EOL product's cycle
    label: str | None = None  # EOL product label
    earliest_due: date | None = None


async def security_info(session: AsyncSession, tasks: list[Task]) -> dict[UUID, SecurityInfo]:
    ids = [t.id for t in tasks if t.kind == TaskKind.security]
    if not ids:
        return {}
    sla = await orgstats.sla_days(session)
    info: dict[UUID, SecurityInfo] = {i: SecurityInfo() for i in ids}
    rows = (
        await session.exec(
            select(VulnMatch, Package)
            .join(Package, col(Package.id) == col(VulnMatch.package_id))
            .where(col(VulnMatch.task_id).in_(ids), col(VulnMatch.status).in_(UNRESOLVED))
        )
    ).all()
    fixes: dict[UUID, list[str | None]] = defaultdict(list)
    versions: dict[UUID, set[str]] = defaultdict(set)
    for match, pkg in rows:
        assert match.task_id is not None
        i = info[match.task_id]
        i.vuln_count += 1
        if i.max_severity is None or _rank(match.severity) > _rank(i.max_severity):
            i.max_severity = match.severity
        due = orgstats.effective_due(match, sla)
        i.earliest_due = due if i.earliest_due is None else min(i.earliest_due, due)
        fixes[match.task_id].append(match.fixed_version)
        versions[match.task_id].add(pkg.version)

    findings = (
        await session.exec(
            select(EolFinding).where(
                col(EolFinding.task_id).in_(ids), col(EolFinding.status).in_(EOL_PENDING)
            )
        )
    ).all()
    for f in findings:
        assert f.task_id is not None
        i = info[f.task_id]
        if i.eol_status != EolStatus.eol:
            i.eol_status = f.status
        if f.eol_date is not None:
            i.eol_date = f.eol_date if i.eol_date is None else min(i.eol_date, f.eol_date)
        i.latest = i.latest or f.latest
        i.label = i.label or f.product_label
        versions[f.task_id].add(f.version)

    for task_id, i in info.items():
        i.installed = sorted(versions.get(task_id, set()))
        if fixes.get(task_id) and i.installed:
            lowest = min(i.installed, key=_version_key)
            i.upgrade = upgrade.recommend(lowest, fixes[task_id])
    return info


def _rank(severity: str) -> int:
    try:
        return SEVERITY_RANK[Severity(severity)]
    except ValueError:
        return 0


def effective_due(task: Task, info: SecurityInfo | None) -> date | None:
    """The task's own due date; for a security task without one, the earliest
    due date of its vulnerabilities, else the EOL date."""
    if task.due_date is not None:
        return task.due_date
    if info is None:
        return None
    return info.earliest_due or info.eol_date
