"""Tasks (開発・セキュリティ対応・その他), sprints, burndown and velocity.

Reading needs read access to the project; creating, editing and planning need
write access (project members)."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import (
    Actor,
    Level,
    accessible_project,
    get_actor,
    visible_projects_clause,
)
from app.core.database import get_session
from app.models.base import utcnow
from app.models.eol import EolFinding
from app.models.package import Package, VulnMatch
from app.models.project import Project, ProjectMember
from app.models.task import Sprint, SprintStatus, Task, TaskKind, TaskStatus
from app.routers.vulnerability import _check_assignee, upgrade_out
from app.schemas.task import (
    BurndownOut,
    BurndownPoint,
    CandidateOut,
    DoneItem,
    LinkedFinding,
    LinkedMatch,
    SecurityOut,
    SecurityTaskBody,
    SprintBody,
    SprintOut,
    SprintUpdate,
    TaskBody,
    TaskDetail,
    TaskOut,
    TaskUpdate,
    VelocityOut,
)
from app.services import deals, upgrade
from app.services import tasks as security_tasks
from app.services.osv import _version_key
from app.services.repo import sync as repo_sync

# Changes that show on the linked issue.
ISSUE_FIELDS = {"title", "kind", "status", "priority", "assignee_id", "sprint_id"}

router = APIRouter(prefix="/api", tags=["tasks"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]

STATUS_ORDER = case(
    {TaskStatus.in_progress: 0, TaskStatus.todo: 1, TaskStatus.done: 2},
    value=col(Task.status),
    else_=3,
)


def today() -> date:
    return utcnow().date()


async def task_rows(session: AsyncSession, tasks: list[Task]) -> list[TaskOut]:
    users = await deals.users_by_id(session, {t.assignee_id for t in tasks})
    project_ids = {t.project_id for t in tasks}
    names = (
        {
            p.id: p.name
            for p in (
                await session.exec(select(Project).where(col(Project.id).in_(project_ids)))
            ).all()
        }
        if project_ids
        else {}
    )
    infos = await security_tasks.security_info(session, tasks)
    now = today()
    rows: list[TaskOut] = []
    for t in tasks:
        info = infos.get(t.id)
        due = security_tasks.effective_due(t, info)
        security = None
        if t.kind == TaskKind.security and t.subject:
            i = info or security_tasks.SecurityInfo()
            security = SecurityOut(
                subject=t.subject,
                ecosystem=t.subject_ecosystem or "",
                name=t.subject_name or "",
                label=(i.label if t.subject == "runtime" else None) or t.subject_name or "",
                installed=i.installed,
                vuln_count=i.vuln_count,
                max_severity=i.max_severity,
                eol_status=i.eol_status,
                eol_date=i.eol_date,
                latest=i.latest,
                upgrade=upgrade_out(i.upgrade),
            )
        rows.append(
            TaskOut(
                id=t.id,
                project_id=t.project_id,
                project_name=names.get(t.project_id, ""),
                number=t.number,
                kind=t.kind,
                title=t.title,
                description=t.description,
                status=t.status,
                priority=t.priority,
                assignee=deals.brief(users.get(t.assignee_id)) if t.assignee_id else None,
                start_date=t.start_date,
                due_date=t.due_date,
                effective_due=due,
                overdue=t.status != TaskStatus.done and due is not None and due < now,
                parent_id=t.parent_id,
                is_milestone=t.is_milestone,
                progress=t.progress,
                depends_on=[UUID(str(d)) for d in t.depends_on],
                sprint_id=t.sprint_id,
                points=t.points,
                position=t.position,
                estimate_hours=t.estimate_hours,
                auto_created=t.auto_created,
                issue_number=t.issue_number,
                issue_url=t.issue_url,
                security=security,
                created_at=t.created_at,
                updated_at=t.updated_at,
                completed_at=t.completed_at,
            )
        )
    return rows


# --- Listing -----------------------------------------------------------------


@router.get(
    "/projects/{project_id}/tasks", response_model=list[TaskOut], summary="プロジェクトのタスク"
)
async def list_project_tasks(
    project_id: UUID,
    actor: CurrentActor,
    session: Session,
    kind: Annotated[TaskKind | None, Query()] = None,
    open_only: Annotated[bool, Query(alias="open")] = False,
    sprint_id: Annotated[str | None, Query(description="スプリントID / none（バックログ）")] = None,
) -> list[TaskOut]:
    await accessible_project(project_id, actor, session)
    query = select(Task).where(Task.project_id == project_id)
    if kind is not None:
        query = query.where(Task.kind == kind)
    if open_only:
        query = query.where(Task.status != TaskStatus.done)
    if sprint_id == "none":
        query = query.where(col(Task.sprint_id).is_(None))
    elif sprint_id:
        query = query.where(Task.sprint_id == _uuid(sprint_id))
    query = query.order_by(col(Task.position), col(Task.number))
    return await task_rows(session, list((await session.exec(query)).all()))


def _uuid(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid id")


@router.get("/tasks", response_model=list[TaskOut], summary="タスク一覧（全プロジェクト）")
async def list_tasks(
    actor: CurrentActor,
    session: Session,
    scope: Annotated[
        Literal["mine", "team", "unassigned"],
        Query(description="mine: 自分が担当 / team: 参加PJ / unassigned: 担当なし"),
    ] = "mine",
    open_only: Annotated[bool, Query(alias="open")] = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TaskOut]:
    """Tasks across the projects the caller can see. Overdue and nearest due
    first."""
    query = (
        select(Task)
        .join(Project, col(Project.id) == col(Task.project_id))
        .where(visible_projects_clause(actor))
    )
    if scope == "mine":
        query = query.where(Task.assignee_id == actor.user.id)
    else:
        member_of = select(ProjectMember.project_id).where(ProjectMember.user_id == actor.user.id)
        query = query.where(col(Task.project_id).in_(member_of))
        if scope == "unassigned":
            query = query.where(col(Task.assignee_id).is_(None))
    if open_only:
        query = query.where(Task.status != TaskStatus.done)
    tasks = list((await session.exec(query.order_by(STATUS_ORDER).limit(limit * 2))).all())
    rows = await task_rows(session, tasks)
    rows.sort(
        key=lambda r: (
            not r.overdue,
            r.status == TaskStatus.done,
            r.effective_due or date.max,
            r.project_name,
            r.number,
        )
    )
    return rows[:limit]


# --- CRUD --------------------------------------------------------------------


async def _load(
    task_id: UUID, actor: Actor, session: AsyncSession, level: Level = Level.read
) -> tuple[Task, Project]:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    project = await accessible_project(task.project_id, actor, session, level)
    return task, project


async def _check_refs(
    session: AsyncSession,
    project: Project,
    task_id: UUID | None,
    parent_id: UUID | None,
    depends_on: list[UUID] | None,
    sprint_id: UUID | None,
) -> None:
    def bad(msg: str) -> HTTPException:
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)

    if parent_id is not None:
        if parent_id == task_id:
            raise bad("A task cannot be its own parent")
        parent = await session.get(Task, parent_id)
        if parent is None or parent.project_id != project.id:
            raise bad("Parent task not found")
        # No cycles: walk up from the new parent.
        seen = {parent_id}
        current = parent
        while current.parent_id is not None:
            if current.parent_id == task_id or current.parent_id in seen:
                raise bad("Parent would create a cycle")
            seen.add(current.parent_id)
            nxt = await session.get(Task, current.parent_id)
            if nxt is None:
                break
            current = nxt
    if depends_on:
        if task_id in depends_on:
            raise bad("A task cannot depend on itself")
        found = (
            await session.exec(
                select(Task.id).where(col(Task.id).in_(depends_on), Task.project_id == project.id)
            )
        ).all()
        if len(set(found)) != len(set(depends_on)):
            raise bad("Dependency not found")
    if sprint_id is not None:
        sprint = await session.get(Sprint, sprint_id)
        if sprint is None or sprint.project_id != project.id:
            raise bad("Sprint not found")


def _set_status(task: Task, value: str) -> None:
    if value == task.status:
        return
    task.status = value
    if value == TaskStatus.done:
        task.completed_at = utcnow()
        task.progress = 100
    else:
        task.completed_at = None
        if task.progress == 100:
            task.progress = 0 if value == TaskStatus.todo else 50


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="タスクの作成",
)
async def create_task(
    project_id: UUID, body: TaskBody, actor: CurrentActor, session: Session
) -> TaskOut:
    project = await accessible_project(project_id, actor, session, Level.write)
    if body.assignee_id is not None:
        await _check_assignee(body.assignee_id, project, session)
    await _check_refs(session, project, None, body.parent_id, body.depends_on, body.sprint_id)
    task = Task(
        project_id=project_id,
        number=await security_tasks.next_number(session, project_id),
        position=await security_tasks.next_position(session, project_id),
        kind=body.kind,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assignee_id=body.assignee_id,
        start_date=body.start_date,
        due_date=body.start_date if body.is_milestone else body.due_date,
        parent_id=body.parent_id,
        is_milestone=body.is_milestone,
        progress=body.progress,
        depends_on=[str(d) for d in dict.fromkeys(body.depends_on)],
        sprint_id=body.sprint_id,
        points=body.points,
        estimate_hours=body.estimate_hours,
        created_by=actor.user.id,
    )
    _set_status(task, body.status)
    _check_dates(task)
    session.add(task)
    await session.commit()
    await repo_sync.push_task(session, task)
    return (await task_rows(session, [task]))[0]


def _check_dates(task: Task) -> None:
    if task.start_date and task.due_date and task.due_date < task.start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Due date is before the start date"
        )


async def _detail(session: AsyncSession, task: Task) -> TaskDetail:
    row = (await task_rows(session, [task]))[0]
    matches = (
        await session.exec(
            select(VulnMatch, Package)
            .join(Package, col(Package.id) == col(VulnMatch.package_id))
            .where(VulnMatch.task_id == task.id)
            .order_by(col(VulnMatch.first_seen_at))
        )
    ).all()
    findings = (await session.exec(select(EolFinding).where(EolFinding.task_id == task.id))).all()
    return TaskDetail(
        **row.model_dump(),
        matches=[
            LinkedMatch(
                id=m.id,
                vuln_id=m.vuln_id,
                summary=m.summary,
                severity=m.severity,
                package_version=p.version,
                fixed_version=m.fixed_version,
                status=m.status,
            )
            for m, p in matches
        ],
        findings=[
            LinkedFinding(
                id=f.id,
                product_label=f.product_label,
                version=f.version,
                cycle=f.cycle,
                eol_date=f.eol_date,
                status=f.status,
            )
            for f in findings
        ],
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail, summary="タスク詳細")
async def get_task(task_id: UUID, actor: CurrentActor, session: Session) -> TaskDetail:
    task, _ = await _load(task_id, actor, session)
    return await _detail(session, task)


@router.patch("/tasks/{task_id}", response_model=TaskDetail, summary="タスクの更新")
async def update_task(
    task_id: UUID, body: TaskUpdate, actor: CurrentActor, session: Session
) -> TaskDetail:
    task, project = await _load(task_id, actor, session, Level.write)
    fields = body.model_dump(exclude_unset=True)
    if "assignee_id" in fields and body.assignee_id not in (None, task.assignee_id):
        assert body.assignee_id is not None
        await _check_assignee(body.assignee_id, project, session)
    await _check_refs(
        session,
        project,
        task.id,
        body.parent_id if "parent_id" in fields else None,
        body.depends_on if "depends_on" in fields else None,
        body.sprint_id if "sprint_id" in fields else None,
    )
    for key in (
        "title",
        "description",
        "priority",
        "assignee_id",
        "start_date",
        "due_date",
        "parent_id",
        "sprint_id",
        "points",
        "estimate_hours",
    ):
        if key in fields:
            setattr(task, key, fields[key])
    for key in ("kind", "is_milestone", "progress", "position"):
        if fields.get(key) is not None:
            setattr(task, key, fields[key])
    if body.depends_on is not None:
        task.depends_on = [str(d) for d in dict.fromkeys(body.depends_on)]
    if task.is_milestone and task.start_date:
        task.due_date = task.start_date
    if body.status is not None:
        _set_status(task, body.status)
    _check_dates(task)
    task.updated_at = utcnow()
    session.add(task)
    await session.commit()
    if fields.keys() & ISSUE_FIELDS:
        await repo_sync.push_task(session, task)
    return await _detail(session, task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="タスクの削除")
async def delete_task(task_id: UUID, actor: CurrentActor, session: Session) -> None:
    """Linked vulnerabilities and EOL findings go back to the candidates."""
    task, _ = await _load(task_id, actor, session, Level.write)
    for model in (VulnMatch, EolFinding):
        for row in (await session.exec(select(model).where(model.task_id == task.id))).all():
            row.task_id = None
            session.add(row)
    for child in (await session.exec(select(Task).where(Task.parent_id == task.id))).all():
        child.parent_id = None
        session.add(child)
    for other in (await session.exec(select(Task).where(Task.project_id == task.project_id))).all():
        if str(task.id) in other.depends_on:
            other.depends_on = [d for d in other.depends_on if d != str(task.id)]
            session.add(other)
    await session.delete(task)
    await session.commit()


# --- Security candidates -----------------------------------------------------


@router.get(
    "/projects/{project_id}/security/candidates",
    response_model=list[CandidateOut],
    summary="タスク化されていない脆弱性・EOL",
)
async def list_candidates(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[CandidateOut]:
    await accessible_project(project_id, actor, session)
    rows: list[CandidateOut] = []
    for c in await security_tasks.candidates(session, project_id):
        _, subject, ecosystem, name = c.key
        installed: set[str] = {f.version for f in c.findings}
        pkg_versions: dict[UUID, str] = {}
        for m in c.matches:
            pkg = await session.get(Package, m.package_id)
            if pkg is not None:
                installed.add(pkg.version)
                pkg_versions[pkg.id] = pkg.version
        worst = None
        for m in c.matches:
            if worst is None or security_tasks._rank(m.severity) > security_tasks._rank(worst):
                worst = m.severity
        up = None
        if c.matches and installed:
            lowest = min(installed, key=_version_key)
            up = upgrade.recommend(lowest, [m.fixed_version for m in c.matches])
        eol_status = None
        for f in c.findings:
            eol_status = f.status if eol_status != "eol" else eol_status
        rows.append(
            CandidateOut(
                subject=subject,
                ecosystem=ecosystem,
                name=name,
                label=c.label,
                installed=sorted(installed),
                vuln_count=len(c.matches),
                max_severity=worst,
                eol_status=eol_status,
                upgrade=upgrade_out(up),
            )
        )
    return rows


@router.post(
    "/projects/{project_id}/security/tasks",
    response_model=TaskDetail,
    status_code=status.HTTP_201_CREATED,
    summary="タスク化",
)
async def create_security_task(
    project_id: UUID, body: SecurityTaskBody, actor: CurrentActor, session: Session
) -> TaskDetail:
    """Turn a candidate into a security task (or add it to the open task of the
    same package)."""
    await accessible_project(project_id, actor, session, Level.write)
    task = await security_tasks.create_for_subject(
        session, project_id, body.subject, body.ecosystem, body.name
    )
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing to fix for this package")
    if task.created_by is None:
        task.created_by = actor.user.id
        session.add(task)
        await session.commit()
    await repo_sync.push_task(session, task)
    return await _detail(session, task)


# --- Sprints -----------------------------------------------------------------


def _done_items(raw: list[object]) -> list[DoneItem]:
    items: list[DoneItem] = []
    for entry in raw:
        if isinstance(entry, dict):
            items.append(DoneItem(text=str(entry.get("text", "")), done=bool(entry.get("done"))))
    return items


async def _sprint_rows(session: AsyncSession, sprints: list[Sprint]) -> list[SprintOut]:
    ids = [s.id for s in sprints]
    tasks = (
        list((await session.exec(select(Task).where(col(Task.sprint_id).in_(ids)))).all())
        if ids
        else []
    )
    by_sprint: dict[UUID, list[Task]] = defaultdict(list)
    for t in tasks:
        assert t.sprint_id is not None
        by_sprint[t.sprint_id].append(t)
    rows = []
    for s in sprints:
        ts = by_sprint.get(s.id, [])
        done = [t for t in ts if t.status == TaskStatus.done]
        rows.append(
            SprintOut(
                id=s.id,
                project_id=s.project_id,
                name=s.name,
                goal=s.goal,
                starts_on=s.starts_on,
                ends_on=s.ends_on,
                status=s.status,
                definition_of_done=_done_items(s.definition_of_done),
                task_count=len(ts),
                done_count=len(done),
                points=sum(t.points or 0 for t in ts),
                done_points=sum(t.points or 0 for t in done),
            )
        )
    return rows


@router.get(
    "/projects/{project_id}/sprints", response_model=list[SprintOut], summary="スプリント一覧"
)
async def list_sprints(project_id: UUID, actor: CurrentActor, session: Session) -> list[SprintOut]:
    await accessible_project(project_id, actor, session)
    sprints = list(
        (
            await session.exec(
                select(Sprint)
                .where(Sprint.project_id == project_id)
                .order_by(col(Sprint.starts_on))
            )
        ).all()
    )
    return await _sprint_rows(session, sprints)


async def _only_active(session: AsyncSession, sprint: Sprint) -> None:
    """At most one active sprint per project."""
    if sprint.status != SprintStatus.active:
        return
    others = (
        await session.exec(
            select(Sprint).where(
                Sprint.project_id == sprint.project_id,
                Sprint.status == SprintStatus.active,
                Sprint.id != sprint.id,
            )
        )
    ).all()
    if others:
        raise HTTPException(status.HTTP_409_CONFLICT, "Another sprint is already active")


def _check_sprint_dates(starts_on: date, ends_on: date) -> None:
    if ends_on < starts_on:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Sprint ends before it starts")


async def _check_sprint_name(session: AsyncSession, sprint: Sprint) -> None:
    clash = (
        await session.exec(
            select(Sprint).where(
                Sprint.project_id == sprint.project_id,
                Sprint.name == sprint.name,
                Sprint.id != sprint.id,
            )
        )
    ).first()
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sprint name already used")


@router.post(
    "/projects/{project_id}/sprints",
    response_model=SprintOut,
    status_code=status.HTTP_201_CREATED,
    summary="スプリントの作成",
)
async def create_sprint(
    project_id: UUID, body: SprintBody, actor: CurrentActor, session: Session
) -> SprintOut:
    await accessible_project(project_id, actor, session, Level.write)
    _check_sprint_dates(body.starts_on, body.ends_on)
    sprint = Sprint(
        project_id=project_id,
        name=body.name.strip(),
        goal=body.goal,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        status=body.status,
        definition_of_done=[i.model_dump() for i in body.definition_of_done],
    )
    await _check_sprint_name(session, sprint)
    await _only_active(session, sprint)
    session.add(sprint)
    await session.commit()
    await repo_sync.push_sprint(session, sprint)
    return (await _sprint_rows(session, [sprint]))[0]


async def _load_sprint(
    sprint_id: UUID, actor: Actor, session: AsyncSession, level: Level = Level.read
) -> Sprint:
    sprint = await session.get(Sprint, sprint_id)
    if sprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sprint not found")
    await accessible_project(sprint.project_id, actor, session, level)
    return sprint


@router.patch("/sprints/{sprint_id}", response_model=SprintOut, summary="スプリントの更新")
async def update_sprint(
    sprint_id: UUID, body: SprintUpdate, actor: CurrentActor, session: Session
) -> SprintOut:
    """Closing a sprint moves its unfinished tasks back to the backlog."""
    sprint = await _load_sprint(sprint_id, actor, session, Level.write)
    fields = body.model_dump(exclude_unset=True)
    if body.name is not None:
        sprint.name = body.name.strip()
        await _check_sprint_name(session, sprint)
    if "goal" in fields:
        sprint.goal = body.goal
    if body.starts_on is not None:
        sprint.starts_on = body.starts_on
    if body.ends_on is not None:
        sprint.ends_on = body.ends_on
    _check_sprint_dates(sprint.starts_on, sprint.ends_on)
    if body.definition_of_done is not None:
        sprint.definition_of_done = [i.model_dump() for i in body.definition_of_done]
    closing = body.status == SprintStatus.closed and sprint.status != SprintStatus.closed
    if body.status is not None:
        sprint.status = body.status
        await _only_active(session, sprint)
    if closing:
        sprint.committed_points = sum(
            t.points or 0
            for t in (await session.exec(select(Task).where(Task.sprint_id == sprint.id))).all()
        )
        for t in (
            await session.exec(
                select(Task).where(Task.sprint_id == sprint.id, Task.status != TaskStatus.done)
            )
        ).all():
            t.sprint_id = None
            session.add(t)
    session.add(sprint)
    await session.commit()
    await repo_sync.push_sprint(session, sprint)
    return (await _sprint_rows(session, [sprint]))[0]


@router.delete(
    "/sprints/{sprint_id}", status_code=status.HTTP_204_NO_CONTENT, summary="スプリントの削除"
)
async def delete_sprint(sprint_id: UUID, actor: CurrentActor, session: Session) -> None:
    sprint = await _load_sprint(sprint_id, actor, session, Level.write)
    for t in (await session.exec(select(Task).where(Task.sprint_id == sprint.id))).all():
        t.sprint_id = None
        session.add(t)
    await session.delete(sprint)
    await session.commit()


def _weight(tasks: list[Task]) -> tuple[str, dict[UUID, float]]:
    """Points when anything is estimated, else one per task."""
    if any(t.points for t in tasks):
        return "points", {t.id: float(t.points or 0) for t in tasks}
    return "tasks", {t.id: 1.0 for t in tasks}


@router.get("/sprints/{sprint_id}/burndown", response_model=BurndownOut, summary="バーンダウン")
async def burndown(sprint_id: UUID, actor: CurrentActor, session: Session) -> BurndownOut:
    """Remaining work at the end of each sprint day, from the tasks now in the
    sprint and when they were completed."""
    sprint = await _load_sprint(sprint_id, actor, session)
    tasks = list((await session.exec(select(Task).where(Task.sprint_id == sprint.id))).all())
    unit, weight = _weight(tasks)
    total = sum(weight.values())
    days = (sprint.ends_on - sprint.starts_on).days
    now = today()
    points: list[BurndownPoint] = []
    for i in range(days + 1):
        day = sprint.starts_on + timedelta(days=i)
        ideal = total - total * i / days if days else 0.0
        remaining: float | None = None
        if day <= now:
            remaining = total - sum(
                weight[t.id]
                for t in tasks
                if t.status == TaskStatus.done
                and t.completed_at is not None
                and t.completed_at.date() <= day
            )
        points.append(BurndownPoint(date=day, ideal=round(ideal, 2), remaining=remaining))
    return BurndownOut(sprint_id=sprint.id, unit=unit, total=total, points=points)


@router.get(
    "/projects/{project_id}/velocity", response_model=list[VelocityOut], summary="ベロシティ"
)
async def velocity(project_id: UUID, actor: CurrentActor, session: Session) -> list[VelocityOut]:
    """Committed and completed points of every started sprint, oldest first."""
    await accessible_project(project_id, actor, session)
    sprints = list(
        (
            await session.exec(
                select(Sprint)
                .where(Sprint.project_id == project_id, Sprint.status != SprintStatus.planned)
                .order_by(col(Sprint.starts_on))
            )
        ).all()
    )
    rows = {r.id: r for r in await _sprint_rows(session, sprints)}
    return [
        VelocityOut(
            sprint_id=s.id,
            name=s.name,
            status=s.status,
            committed=s.committed_points if s.committed_points is not None else rows[s.id].points,
            completed=rows[s.id].done_points,
        )
        for s in sprints
    ]
