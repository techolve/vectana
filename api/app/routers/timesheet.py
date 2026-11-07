"""実績工数: hours per day and task, entered a week at a time, and how they
compare with the estimate.

People enter their own weeks. Company admins (and group admins) may read and
edit anyone of their company; department heads read the people of their
departments."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, accessible_project, get_actor, load_actor, project_level
from app.core.database import get_session
from app.models.base import utcnow
from app.models.estimate import Billing, Estimate, EstimateLine, EstimateStatus
from app.models.organization import UserDepartment
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.models.work import HOURS_PER_DAY, TimeEntry, TimesheetWeek
from app.schemas.org import UserBrief
from app.schemas.work import (
    ActualsOut,
    PersonActual,
    PhaseActual,
    TimesheetBody,
    TimesheetOut,
    TimesheetRow,
)
from app.services import deals

router = APIRouter(prefix="/api", tags=["timesheet"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]

STANDARD_WEEK_HOURS = 40.0


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def _target(session: AsyncSession, actor: Actor, user_id: UUID | None, edit: bool) -> User:
    if user_id is None or user_id == actor.user.id:
        return actor.user
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    admin = user.company_id is not None and actor.can_manage_company(user.company_id)
    if admin or actor.is_group_admin:
        return user
    if not edit and actor.managed_department_ids:
        heads = (
            await session.exec(
                select(UserDepartment.department_id).where(
                    UserDepartment.user_id == user.id,
                    col(UserDepartment.department_id).in_(actor.managed_department_ids),
                )
            )
        ).first()
        if heads is not None:
            return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot see this person's timesheet")


async def _sheet(session: AsyncSession, actor: Actor, user: User, start: date) -> TimesheetOut:
    days = [start + timedelta(days=i) for i in range(7)]
    entries = list(
        (
            await session.exec(
                select(TimeEntry)
                .where(
                    TimeEntry.user_id == user.id,
                    col(TimeEntry.work_date) >= days[0],
                    col(TimeEntry.work_date) <= days[-1],
                )
                .order_by(col(TimeEntry.position), col(TimeEntry.created_at))
            )
        ).all()
    )
    rows: dict[tuple[UUID | None, UUID | None, str | None], list[float | None]] = {}
    for e in entries:
        key = (e.project_id, e.task_id, e.label)
        hours = rows.setdefault(key, [None] * 7)
        i = (e.work_date - start).days
        hours[i] = (hours[i] or 0) + e.hours

    project_ids = {k[0] for k in rows if k[0]}
    task_ids = {k[1] for k in rows if k[1]}
    projects = await deals.rows_by_id(session, Project, project_ids)
    tasks = await deals.rows_by_id(session, Task, task_ids)
    actual = await _task_hours(session, task_ids)
    out_rows = []
    for (pid, tid, label), hours in rows.items():
        task = tasks.get(tid) if tid else None
        project = projects.get(pid) if pid else None
        out_rows.append(
            TimesheetRow(
                project_id=pid,
                project_name=project.name if project else None,
                task_id=tid,
                task_number=task.number if task else None,
                task_title=task.title if task else None,
                task_kind=task.kind if task else None,
                label=label,
                hours=hours,
                estimate_hours=task.estimate_hours if task else None,
                actual_hours=actual.get(tid) if tid else None,
            )
        )
    week = await session.get(TimesheetWeek, (user.id, start))
    can_edit = user.id == actor.user.id or (
        user.company_id is not None and actor.can_manage_company(user.company_id)
    )
    return TimesheetOut(
        user=deals.brief(user),  # type: ignore[arg-type]
        week_start=start,
        days=days,
        rows=out_rows,
        standard_hours=STANDARD_WEEK_HOURS,
        submitted_at=week.submitted_at if week else None,
        can_edit=can_edit,
    )


async def _task_hours(session: AsyncSession, task_ids: set[UUID]) -> dict[UUID, float]:
    if not task_ids:
        return {}
    rows = await session.exec(
        select(TimeEntry.task_id, func.sum(TimeEntry.hours))
        .where(col(TimeEntry.task_id).in_(task_ids))
        .group_by(col(TimeEntry.task_id))
    )
    return {tid: float(h or 0) for tid, h in rows.all() if tid is not None}


@router.get("/timesheet/people", response_model=list[UserBrief], summary="工数を見られる人")
async def timesheet_people(actor: CurrentActor, session: Session) -> list[UserBrief]:
    """The caller first, then whoever's sheet the caller may read: everyone
    of the company for admins (all companies for group admins), the
    department's people for heads."""
    query = select(User).where(col(User.is_active).is_(True))
    if actor.is_group_admin:
        pass
    elif actor.is_company_admin and actor.user.company_id is not None:
        query = query.where(User.company_id == actor.user.company_id)
    elif actor.managed_department_ids:
        query = query.where(
            col(User.id).in_(
                select(UserDepartment.user_id).where(
                    col(UserDepartment.department_id).in_(actor.managed_department_ids)
                )
            )
        )
    else:
        query = query.where(User.id == actor.user.id)
    users = list(
        (await session.exec(query.order_by(col(User.display_name), col(User.email)))).all()
    )
    users.sort(key=lambda u: u.id != actor.user.id)
    return [b for u in users if (b := deals.brief(u)) is not None]


@router.get("/timesheet", response_model=TimesheetOut, summary="週の実績工数")
async def get_timesheet(
    actor: CurrentActor,
    session: Session,
    week: Annotated[date | None, Query(description="週のどの日でも可（既定は今週）")] = None,
    user_id: Annotated[UUID | None, Query()] = None,
) -> TimesheetOut:
    user = await _target(session, actor, user_id, edit=False)
    return await _sheet(session, actor, user, monday(week or utcnow().date()))


@router.put("/timesheet", response_model=TimesheetOut, summary="週の実績工数を保存")
async def put_timesheet(body: TimesheetBody, actor: CurrentActor, session: Session) -> TimesheetOut:
    """Replaces the whole week with the rows sent (what the sheet shows)."""
    user = await _target(session, actor, body.user_id, edit=True)
    start = monday(body.week_start)
    target_actor = actor if user.id == actor.user.id else await load_actor(user, session)

    def bad(msg: str) -> HTTPException:
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)

    checked: dict[UUID, bool] = {}
    entries: list[TimeEntry] = []
    totals = [0.0] * 7
    seen: set[tuple[UUID | None, UUID | None, str | None]] = set()
    for pos, row in enumerate(body.rows):
        project_id, task_id = row.project_id, row.task_id
        label = (row.label or "").strip() or None
        if task_id is not None:
            task = await session.get(Task, task_id)
            if task is None:
                raise bad("Task not found")
            if project_id is not None and project_id != task.project_id:
                raise bad("Task belongs to another project")
            project_id = task.project_id
            label = None
        if project_id is not None:
            if project_id not in checked:
                project = await session.get(Project, project_id)
                checked[project_id] = (
                    project is not None
                    and await project_level(project, target_actor, session) is not None
                )
            if not checked[project_id]:
                raise bad("Project not found")
        elif not label:
            raise bad("A row needs a project, a task or a label")
        key = (project_id, task_id, label)
        if key in seen:
            raise bad("The same row appears twice")
        seen.add(key)
        for i, h in enumerate(row.hours):
            if not h:
                continue
            totals[i] += h
            entries.append(
                TimeEntry(
                    user_id=user.id,
                    work_date=start + timedelta(days=i),
                    project_id=project_id,
                    task_id=task_id,
                    label=label if project_id is None else None,
                    hours=h,
                    position=pos,
                )
            )
    if any(t > 24 for t in totals):
        raise bad("More than 24 hours in a day")

    await session.exec(
        delete(TimeEntry).where(
            col(TimeEntry.user_id) == user.id,
            col(TimeEntry.work_date) >= start,
            col(TimeEntry.work_date) <= start + timedelta(days=6),
        )
    )
    session.add_all(entries)
    await session.commit()
    return await _sheet(session, actor, user, start)


@router.post("/timesheet/submit", response_model=TimesheetOut, summary="週を提出")
async def submit_week(
    actor: CurrentActor,
    session: Session,
    week: Annotated[date, Query()],
    user_id: Annotated[UUID | None, Query()] = None,
) -> TimesheetOut:
    user = await _target(session, actor, user_id, edit=True)
    start = monday(week)
    if await session.get(TimesheetWeek, (user.id, start)) is None:
        session.add(TimesheetWeek(user_id=user.id, week_start=start))
        await session.commit()
    return await _sheet(session, actor, user, start)


@router.delete("/timesheet/submit", response_model=TimesheetOut, summary="提出を取り消す")
async def unsubmit_week(
    actor: CurrentActor,
    session: Session,
    week: Annotated[date, Query()],
    user_id: Annotated[UUID | None, Query()] = None,
) -> TimesheetOut:
    user = await _target(session, actor, user_id, edit=True)
    start = monday(week)
    row = await session.get(TimesheetWeek, (user.id, start))
    if row is not None:
        await session.delete(row)
        await session.commit()
    return await _sheet(session, actor, user, start)


# --- Estimate vs actual --------------------------------------------------------------


def _root(task_id: UUID, parents: dict[UUID, UUID | None]) -> UUID:
    seen = set()
    current = task_id
    while parents.get(current) is not None and current not in seen:
        seen.add(current)
        current = parents[current]  # type: ignore[assignment]
    return current


@router.get("/projects/{project_id}/actuals", response_model=ActualsOut, summary="見積と実績")
async def project_actuals(project_id: UUID, actor: CurrentActor, session: Session) -> ActualsOut:
    """Actual effort against the won estimates, overall, per phase (top-level
    task with sub-tasks) and per person. Hidden from partner (BP) users."""
    project = await accessible_project(project_id, actor, session)
    if not actor.sees_money:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for partner users")

    estimates = list(
        (
            await session.exec(
                select(Estimate).where(
                    Estimate.project_id == project_id,
                    Estimate.status == EstimateStatus.won,
                    Estimate.billing == Billing.one_time,
                )
            )
        ).all()
    )
    estimate_days: float | None = None
    estimate_amount: int | None = None
    if estimates:
        lines = list(
            (
                await session.exec(
                    select(EstimateLine).where(
                        col(EstimateLine.estimate_id).in_([e.id for e in estimates])
                    )
                )
            ).all()
        )
        for est in estimates:
            effort, _, _ = deals.effort_and_cost(est, [x for x in lines if x.estimate_id == est.id])
            if effort is not None:
                estimate_days = (estimate_days or 0) + effort
            if est.amount is not None:
                estimate_amount = (estimate_amount or 0) + est.amount

    entries = list(
        (await session.exec(select(TimeEntry).where(TimeEntry.project_id == project_id))).all()
    )
    tasks = list((await session.exec(select(Task).where(Task.project_id == project_id))).all())
    parents = {t.id: t.parent_id for t in tasks}
    by_id = {t.id: t for t in tasks}
    has_children = {t.parent_id for t in tasks if t.parent_id}
    phases = [t for t in tasks if t.parent_id is None and t.id in has_children]
    phase_ids = {p.id for p in phases}

    phase_hours: dict[UUID | None, float] = defaultdict(float)
    person_hours: dict[UUID, float] = defaultdict(float)
    month_start = utcnow().date().replace(day=1)
    month_hours = 0.0
    for e in entries:
        root = _root(e.task_id, parents) if e.task_id else None
        phase_hours[root if root in phase_ids else None] += e.hours
        person_hours[e.user_id] += e.hours
        if e.work_date >= month_start:
            month_hours += e.hours

    estimate_by_phase: dict[UUID, float] = defaultdict(float)
    for t in tasks:
        if t.estimate_hours:
            root = _root(t.id, parents)
            if root in phase_ids:
                estimate_by_phase[root] += t.estimate_hours

    users = await deals.users_by_id(session, set(person_hours))
    actual_cost = None
    if actor.can_see_unit_cost(project.company_id):
        actual_cost = round(
            sum(
                h / HOURS_PER_DAY * (users[u].unit_cost or 0)
                for u, h in person_hours.items()
                if u in users
            )
        )
    total = sum(e.hours for e in entries)
    phase_rows = [
        PhaseActual(
            task_id=p.id,
            title=by_id[p.id].title,
            estimate_days=round(estimate_by_phase[p.id] / HOURS_PER_DAY, 2)
            if p.id in estimate_by_phase
            else None,
            actual_days=round(phase_hours.get(p.id, 0) / HOURS_PER_DAY, 2),
        )
        for p in sorted(phases, key=lambda t: (t.start_date or date.max, t.number))
    ]
    if phase_hours.get(None):
        phase_rows.append(
            PhaseActual(
                task_id=None,
                title=None,
                estimate_days=None,
                actual_days=round(phase_hours[None] / HOURS_PER_DAY, 2),
            )
        )
    return ActualsOut(
        project_id=project_id,
        estimate_days=estimate_days,
        estimate_amount=estimate_amount,
        actual_hours=total,
        actual_days=round(total / HOURS_PER_DAY, 2),
        this_month_days=round(month_hours / HOURS_PER_DAY, 2),
        actual_cost=actual_cost,
        phases=phase_rows,
        people=[
            PersonActual(user=deals.brief(users[u]), actual_days=round(h / HOURS_PER_DAY, 2))  # type: ignore[arg-type]
            for u, h in sorted(person_hours.items(), key=lambda kv: -kv[1])
            if u in users
        ],
    )
