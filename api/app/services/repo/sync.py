"""Keep tasks and issues, sprints and milestones in step, and import the
repository's dependency files.

Outbound (Vectana -> provider) runs right after a change is saved; inbound
(provider -> Vectana) runs from webhooks. Each side only writes fields that
differ, so a change echoed back by the other side's webhook does nothing.
Provider errors never fail the Vectana request: they are recorded on the link
and shown in the project's settings."""

import fnmatch
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.i18n import DEFAULT_LOCALE, t
from app.models.base import utcnow
from app.models.eol import Runtime
from app.models.package import Package
from app.models.repo import RepoLink, RepoProvider
from app.models.task import Sprint, SprintStatus, Task, TaskKind, TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.project import ImportResult
from app.services import importer
from app.services.repo.client import (
    Issue,
    IssueChange,
    Milestone,
    RepoClient,
    RepoError,
    make_client,
)

logger = logging.getLogger("vectana.repo")

KIND_LABELS = {TaskKind.security: "security", TaskKind.other: "other"}
PRIORITY_RE = re.compile(r"^priority\s*[:/]\s*(high|medium|low)$", re.IGNORECASE)
MARKER = "<!-- vectana:task:{id} -->"
MARKER_RE = re.compile(r"<!-- vectana:task:([0-9a-f-]{36}) -->")
CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)", re.IGNORECASE)
SKIP_DIRS = ("node_modules/", "vendor/", ".git/", "bower_components/")
MAX_IMPORT_FILES = 50


def login_column(provider: str):  # type: ignore[no-untyped-def]
    return col(User.github_login) if provider == RepoProvider.github else col(User.gitlab_username)


def login_in(provider: str, logins: list[str]):  # type: ignore[no-untyped-def]
    """Account names compare case-insensitively, as on GitHub and GitLab."""
    return func.lower(login_column(provider)).in_([lg.lower() for lg in logins])


def user_login(user: User, provider: str) -> str | None:
    return user.github_login if provider == RepoProvider.github else user.gitlab_username


def priority_label(priority: str) -> str:
    return f"priority: {priority}"


def is_mapped_label(label: str) -> bool:
    return label.lower() in KIND_LABELS.values() or bool(PRIORITY_RE.match(label))


def _aware(dt: datetime) -> datetime:
    # SQLite hands timestamps back naive; Postgres keeps the zone.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def record_error(session: AsyncSession, link: RepoLink, exc: Exception) -> None:
    logger.warning("Repository %s: %s", link.repo, exc)
    link.last_error = str(exc)[:1000]
    link.last_error_at = utcnow()
    session.add(link)
    await session.commit()


async def _clear_error(session: AsyncSession, link: RepoLink) -> None:
    if link.last_error:
        link.last_error = None
        link.last_error_at = None
        session.add(link)


# --- Outbound: tasks -> issues ----------------------------------------------------


async def issue_link(session: AsyncSession, task: Task) -> RepoLink | None:
    """The link the task's issue lives in, or where a new one should go:
    the project's first link that syncs issues (or, for security tasks made
    automatically, that opens security issues). Only tasks created after the
    link get an issue, so linking a repository does not flood it."""
    if task.repo_link_id is not None:
        return await session.get(RepoLink, task.repo_link_id)
    if task.status == TaskStatus.done:
        return None
    links = (
        await session.exec(
            select(RepoLink)
            .where(RepoLink.project_id == task.project_id)
            .order_by(col(RepoLink.created_at))
        )
    ).all()
    for link in links:
        wanted = link.security_issues if task.auto_created else link.sync_issues
        if wanted and _aware(task.created_at) >= _aware(link.created_at):
            return link
    return None


async def _locale(session: AsyncSession, link: RepoLink) -> str:
    """Issues are written in the language of the person who linked the repository."""
    user = await session.get(User, link.created_by) if link.created_by else None
    return user.locale if user and user.locale else DEFAULT_LOCALE


async def _issue_title(session: AsyncSession, task: Task, link: RepoLink) -> str:
    if task.kind != TaskKind.security or not task.subject_name:
        return task.title
    from app.services import tasks as security_tasks

    info = (await security_tasks.security_info(session, [task])).get(task.id)
    if task.title not in {task.subject_name, info.label if info else None}:
        return task.title  # renamed by someone: keep their title
    if info and info.upgrade and info.upgrade.version:
        return t(
            await _locale(session, link),
            "repo.issue.upgradeTo",
            name=task.title,
            version=info.upgrade.version,
        )
    return t(await _locale(session, link), "repo.issue.upgrade", name=task.title)


def _task_url(task: Task) -> str:
    return f"{settings.web_url.rstrip('/')}/projects/detail/?id={task.project_id}&task={task.id}"


def _issue_body(task: Task, locale: str) -> str:
    parts = [task.description.strip()] if task.description else []
    parts.append(t(locale, "repo.issue.footer", url=_task_url(task)))
    parts.append(MARKER.format(id=task.id))
    return "\n\n".join(parts)


async def _wanted_assignees(
    session: AsyncSession, task: Task, link: RepoLink, current: list[str]
) -> list[str] | None:
    """None leaves the issue's assignees alone."""
    if task.assignee_id is not None:
        user = await session.get(User, task.assignee_id)
        login = user_login(user, link.provider) if user else None
        return [login] if login else None
    if not current:
        return None
    # Unassign only people Vectana knows: others were never mapped in.
    known = (await session.exec(select(User.id).where(login_in(link.provider, current)))).first()
    return [] if known else None


async def _wanted_milestone(
    session: AsyncSession, client: RepoClient, task: Task, link: RepoLink
) -> int | None:
    if task.sprint_id is None:
        return None
    sprint = await session.get(Sprint, task.sprint_id)
    if sprint is None:
        return None
    if sprint.repo_link_id != link.id or sprint.milestone_number is None:
        await _push_sprint_with(session, client, sprint, link)
    return sprint.milestone_number


def _wanted_labels(task: Task) -> list[str]:
    labels = [KIND_LABELS[TaskKind(task.kind)]] if task.kind in KIND_LABELS else []
    if task.priority:
        labels.append(priority_label(task.priority))
    return labels


async def push_task(session: AsyncSession, task: Task) -> None:
    """Create or update the task's issue. Commits."""
    link = await issue_link(session, task)
    if link is None:
        return
    try:
        client = make_client(link)
        try:
            await _push_task_with(session, client, task, link)
        finally:
            await client.aclose()
        await _clear_error(session, link)
        await session.commit()
    except RepoError as exc:
        await record_error(session, link, exc)


async def _push_task_with(
    session: AsyncSession, client: RepoClient, task: Task, link: RepoLink
) -> None:
    title = await _issue_title(session, task, link)
    state = "closed" if task.status == TaskStatus.done else "open"
    milestone = await _wanted_milestone(session, client, task, link)
    if task.issue_number is None:
        assignees = await _wanted_assignees(session, task, link, [])
        issue = await client.create_issue(
            IssueChange(
                title=title,
                body=_issue_body(task, await _locale(session, link)),
                state=state,
                labels=_wanted_labels(task),
                assignees=assignees,
                milestone=milestone,
            )
        )
        task.repo_link_id = link.id
        task.issue_number = issue.number
        task.issue_url = issue.url
        session.add(task)
        return

    current = await client.get_issue(task.issue_number)
    labels = [lb for lb in current.labels if not is_mapped_label(lb)] + _wanted_labels(task)
    assignees = await _wanted_assignees(session, task, link, current.assignees)
    change = IssueChange(
        title=title if title != current.title else None,
        state=state if state != current.state else None,
        labels=labels if sorted(labels) != sorted(current.labels) else None,
        assignees=assignees
        if assignees is not None and sorted(assignees) != sorted(current.assignees)
        else None,
        milestone=milestone if milestone is not None and milestone != current.milestone else None,
        clear_milestone=milestone is None
        and current.milestone is not None
        and await _sprint_for(session, link, current.milestone) is not None,
    )
    if any(
        v is not None for v in (change.title, change.state, change.labels, change.assignees)
    ) or (change.milestone is not None or change.clear_milestone):
        await client.update_issue(task.issue_number, change)
    if task.issue_url != current.url and current.url:
        task.issue_url = current.url
        session.add(task)


# --- Outbound: sprints -> milestones ----------------------------------------------


async def push_sprint(session: AsyncSession, sprint: Sprint) -> None:
    link: RepoLink | None
    if sprint.repo_link_id is not None:
        link = await session.get(RepoLink, sprint.repo_link_id)
    else:
        link = (
            await session.exec(
                select(RepoLink)
                .where(RepoLink.project_id == sprint.project_id, col(RepoLink.sync_issues))
                .order_by(col(RepoLink.created_at))
            )
        ).first()
    if link is None or not link.sync_issues:
        return
    try:
        client = make_client(link)
        try:
            await _push_sprint_with(session, client, sprint, link)
        finally:
            await client.aclose()
        await _clear_error(session, link)
        await session.commit()
    except RepoError as exc:
        await record_error(session, link, exc)


async def _push_sprint_with(
    session: AsyncSession, client: RepoClient, sprint: Sprint, link: RepoLink
) -> None:
    wanted = Milestone(
        number=sprint.milestone_number or 0,
        title=sprint.name,
        state="closed" if sprint.status == SprintStatus.closed else "open",
        due_on=sprint.ends_on,
        description=sprint.goal,
    )
    if sprint.repo_link_id == link.id and sprint.milestone_number is not None:
        current = await client.get_milestone(sprint.milestone_number)
        if (current.title, current.state, current.due_on, current.description or None) != (
            wanted.title,
            wanted.state,
            wanted.due_on,
            wanted.description or None,
        ):
            await client.update_milestone(wanted)
        return
    # Reuse a milestone of the same name rather than making a second one.
    existing = next((m for m in await client.list_milestones() if m.title == sprint.name), None)
    if existing is None:
        existing = await client.create_milestone(wanted)
    sprint.repo_link_id = link.id
    sprint.milestone_number = existing.number
    session.add(sprint)
    await session.flush()


# --- Inbound: issues -> tasks ------------------------------------------------------


async def _sprint_for(session: AsyncSession, link: RepoLink, number: int) -> Sprint | None:
    return (
        await session.exec(
            select(Sprint).where(Sprint.repo_link_id == link.id, Sprint.milestone_number == number)
        )
    ).first()


async def apply_milestone(session: AsyncSession, link: RepoLink, m: Milestone) -> Sprint:
    """Find or make the sprint for a milestone and take its name and due date.
    Closing a sprint stays a Vectana action (it freezes points and returns
    unfinished tasks to the backlog), which then closes the milestone."""
    sprint = await _sprint_for(session, link, m.number)
    if sprint is None:
        sprint = (
            await session.exec(
                select(Sprint).where(
                    Sprint.project_id == link.project_id,
                    Sprint.name == m.title[:100],
                    col(Sprint.milestone_number).is_(None),
                )
            )
        ).first()
    if sprint is None:
        today = utcnow().date()
        sprint = Sprint(
            project_id=link.project_id,
            name=m.title[:100],
            goal=m.description or None,
            starts_on=today,
            ends_on=m.due_on or today + timedelta(days=13),
            status=SprintStatus.planned,
        )
    else:
        clash = (
            await session.exec(
                select(Sprint.id).where(
                    Sprint.project_id == link.project_id,
                    Sprint.name == m.title[:100],
                    Sprint.id != sprint.id,
                )
            )
        ).first()
        if clash is None:
            sprint.name = m.title[:100]
        if m.due_on and m.due_on >= sprint.starts_on:
            sprint.ends_on = m.due_on
    sprint.repo_link_id = link.id
    sprint.milestone_number = m.number
    session.add(sprint)
    await session.flush()
    return sprint


def _labels_kind(labels: list[str]) -> str:
    lower = {lb.lower() for lb in labels}
    if "security" in lower:
        return TaskKind.security
    if "other" in lower:
        return TaskKind.other
    return TaskKind.development


def _labels_priority(labels: list[str]) -> str | None:
    for lb in labels:
        if match := PRIORITY_RE.match(lb):
            return TaskPriority(match.group(1).lower())
    return None


async def _assignee(
    session: AsyncSession, link: RepoLink, task: Task | None, logins: list[str]
) -> tuple[bool, UUID | None]:
    """(change?, user id). Unknown accounts leave the task's assignee alone."""
    if not logins:
        return True, None
    users = (
        await session.exec(select(User).where(login_in(link.provider, logins), col(User.is_active)))
    ).all()
    if not users:
        return False, None
    if task is not None and task.assignee_id in {u.id for u in users}:
        return False, task.assignee_id
    by_login = {(user_login(u, link.provider) or "").lower(): u for u in users}
    first = next(by_login[lg.lower()] for lg in logins if lg.lower() in by_login)
    return True, first.id


async def find_task(session: AsyncSession, link: RepoLink, number: int) -> Task | None:
    return (
        await session.exec(
            select(Task).where(Task.repo_link_id == link.id, Task.issue_number == number)
        )
    ).first()


async def apply_issue(
    session: AsyncSession,
    link: RepoLink,
    issue: Issue,
    client: RepoClient | None = None,
) -> Task | None:
    """Create or update the task of an issue. Does not commit."""
    if issue.is_pull_request:
        return None
    task = await find_task(session, link, issue.number)
    if task is None and issue.body and (m := MARKER_RE.search(issue.body)):
        # An issue Vectana just opened, arriving before its number was saved.
        marked = await session.get(Task, UUID(m.group(1)))
        if marked is not None and marked.project_id == link.project_id:
            task = marked
            task.repo_link_id, task.issue_number = link.id, issue.number
    if task is None:
        if not link.sync_issues or issue.state == "closed":
            return None
        from app.services import tasks as task_service

        task = Task(
            project_id=link.project_id,
            number=await task_service.next_number(session, link.project_id),
            position=await task_service.next_position(session, link.project_id),
            kind=_labels_kind(issue.labels),
            title=issue.title[:300] or f"#{issue.number}",
            description=MARKER_RE.sub("", issue.body or "").strip() or None,
            repo_link_id=link.id,
            issue_number=issue.number,
        )
    changed = task.id is None or task not in session

    if issue.title and issue.title != task.title:
        if task.kind != TaskKind.security or issue.title != await _issue_title(session, task, link):
            task.title = issue.title[:300]
            changed = True
    now = utcnow()
    if issue.state == "closed" and task.status != TaskStatus.done:
        task.status, task.progress, task.completed_at = TaskStatus.done, 100, now
        changed = True
    elif issue.state == "open" and task.status == TaskStatus.done:
        task.status, task.completed_at = TaskStatus.todo, None
        changed = True
    move, assignee = await _assignee(session, link, task, issue.assignees)
    if move and assignee != task.assignee_id:
        task.assignee_id = assignee
        changed = True
    if not task.subject:  # security tasks of a package keep their kind
        kind = _labels_kind(issue.labels)
        if kind != task.kind:
            task.kind = kind
            changed = True
    priority = _labels_priority(issue.labels)
    if priority != task.priority:
        task.priority = priority
        changed = True
    if issue.milestone is not None:
        sprint = await _sprint_for(session, link, issue.milestone)
        if sprint is None and client is not None:
            sprint = await apply_milestone(
                session, link, await client.get_milestone(issue.milestone)
            )
        if sprint is not None and task.sprint_id != sprint.id:
            task.sprint_id = sprint.id
            changed = True
    elif task.sprint_id is not None:
        sprint = await session.get(Sprint, task.sprint_id)
        if sprint is not None and sprint.repo_link_id == link.id:
            task.sprint_id = None
            changed = True
    if issue.url and task.issue_url != issue.url:
        task.issue_url = issue.url
        changed = True
    if changed:
        task.updated_at = now
        session.add(task)
        await session.flush()
    return task


async def apply_merged(session: AsyncSession, link: RepoLink, text: str) -> int:
    """Complete the tasks of issues a merged pull / merge request closes
    ("Closes #12", "fixes #3"). Does not commit."""
    numbers = {int(n) for n in CLOSES_RE.findall(text or "")}
    done = 0
    now = utcnow()
    for number in sorted(numbers):
        task = await find_task(session, link, number)
        if task is not None and task.status != TaskStatus.done:
            task.status, task.progress, task.completed_at, task.updated_at = (
                TaskStatus.done,
                100,
                now,
                now,
            )
            session.add(task)
            done += 1
    return done


async def pull_issues(session: AsyncSession, link: RepoLink) -> tuple[int, int]:
    """Bring in the open issues and the milestones (first link, or catching
    up). Returns (tasks created or updated, sprints). Commits."""
    client = make_client(link)
    try:
        milestones = [m for m in await client.list_milestones() if m.state == "open"]
        for m in milestones:
            await apply_milestone(session, link, m)
        count = 0
        for issue in await client.list_issues():
            if await apply_issue(session, link, issue, client) is not None:
                count += 1
    finally:
        await client.aclose()
    link.last_event_at = utcnow()
    await _clear_error(session, link)
    session.add(link)
    await session.commit()
    return count, len(milestones)


# --- Dependency files -------------------------------------------------------------------


@dataclass
class FileOutcome:
    path: str
    result: ImportResult | None = None
    error: str | None = None


@dataclass
class RepoImport:
    sha: str
    files: list[FileOutcome] = field(default_factory=list)
    removed_sources: int = 0
    added_package_ids: list[UUID] = field(default_factory=list)
    runtimes_changed: bool = False


def _source(link: RepoLink, path: str) -> str:
    source = f"git:{link.repo}/{path}"
    if len(source) > 80:
        digest = hashlib.sha1(f"{link.repo}/{path}".encode()).hexdigest()[:8]
        source = f"git:{digest}/{path[-(80 - 13) :]}"
    return source


def wanted_paths(link: RepoLink, paths: list[str]) -> list[str]:
    patterns = [p.strip() for p in link.import_paths or [] if str(p).strip()]
    out = []
    for path in paths:
        if any(f"/{d}" in f"/{path}" for d in SKIP_DIRS) or not importer.is_supported(path):
            continue
        if patterns and not any(fnmatch.fnmatch(path, p) for p in patterns):
            continue
        out.append(path)
    return sorted(out)[:MAX_IMPORT_FILES]


async def import_repo(session: AsyncSession, link: RepoLink) -> RepoImport:
    """Import every supported file on the default branch. Files that are gone
    from the branch take their packages and runtimes with them. Commits."""
    client = make_client(link)
    try:
        sha, paths = await client.tree(link.default_branch)
        outcome = RepoImport(sha=sha)
        owners: dict[tuple[str, str, str], str] = {}
        for path in wanted_paths(link, paths):
            try:
                raw = await client.file(path, sha)
            except RepoError as exc:
                outcome.files.append(FileOutcome(path=path, error=str(exc)))
                continue
            if len(raw) > importer.MAX_BYTES:
                outcome.files.append(FileOutcome(path=path, error="File too large"))
                continue
            try:
                done = await importer.import_file(
                    session, link.project_id, path.rsplit("/", 1)[-1], raw, _source(link, path)
                )
            except importer.ImportFailed as exc:
                outcome.files.append(FileOutcome(path=path, error=str(exc)))
                continue
            outcome.files.append(FileOutcome(path=path, result=done.result))
            for key in done.packages:
                owners.setdefault(key, done.source_key or "")
            outcome.added_package_ids += done.added_package_ids
            outcome.runtimes_changed |= done.runtimes_changed
    finally:
        await client.aclose()

    # Drop what files no longer on the branch contributed.
    keep = {_source(link, f.path) for f in outcome.files}
    prefix = f"git:{link.repo}/"
    package_keep = {f"{kind}:{s}" for s in keep for kind in ("lockfile", "sbom")}
    gone_rows = (
        await session.exec(
            select(Package).where(
                Package.project_id == link.project_id,
                or_(
                    col(Package.source).startswith(f"lockfile:{prefix}"),
                    col(Package.source).startswith(f"sbom:{prefix}"),
                ),
                col(Package.source).not_in(package_keep),
            )
        )
    ).all()
    # A package another file still lists (a moved lockfile, say) changes
    # hands instead of being dropped, so its triage and task stay.
    gone = []
    for pkg in gone_rows:
        owner = owners.get((pkg.ecosystem, pkg.name, pkg.version))
        if owner:
            pkg.source = owner
            session.add(pkg)
        else:
            gone.append(pkg.id)
    if gone:
        await session.exec(delete(Package).where(col(Package.id).in_(gone)))
    gone_runtimes = (
        await session.exec(
            select(Runtime.id).where(
                Runtime.project_id == link.project_id,
                col(Runtime.source).startswith(f"file:{prefix}"),
                col(Runtime.source).not_in({f"file:{s}" for s in keep}),
            )
        )
    ).all()
    if gone_runtimes:
        await session.exec(delete(Runtime).where(col(Runtime.id).in_(gone_runtimes)))
        outcome.runtimes_changed = True
    outcome.removed_sources = len(gone) + len(gone_runtimes)

    link.last_import_at = utcnow()
    link.last_import_sha = sha
    await _clear_error(session, link)
    session.add(link)
    await session.commit()
    if gone:
        from app.services import tasks as security_tasks

        await security_tasks.sync(session, [link.project_id])
    return outcome
