"""商談メモ: a project's log of meetings, calls and emails.

Everyone who sees the project's money (not partner users) reads it. Sales and
admins of the company, and project members with write access, add entries. A
next action becomes a task for its assignee, and the project's "next action"
follows the latest one."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, Level, accessible_project, get_actor, load_actor, project_level
from app.core.database import get_session
from app.models.base import utcnow
from app.models.project import Project
from app.models.task import Task, TaskKind, TaskStatus
from app.models.user import User
from app.models.work import Activity
from app.schemas.work import ActivityBody, ActivityOut, ActivityTask, ActivityUpdate
from app.services import deals
from app.services import tasks as task_service
from app.services.repo import sync as repo_sync

router = APIRouter(prefix="/api", tags=["activities"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


async def _project(
    project_id: UUID, actor: Actor, session: AsyncSession, write: bool = False
) -> Project:
    project = await accessible_project(project_id, actor, session)
    if not actor.sees_money:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for partner users")
    if write and not actor.can_sell(project.company_id):
        level = await project_level(project, actor, session)
        if level is None or level < Level.write:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
    return project


async def _outs(session: AsyncSession, activities: list[Activity]) -> list[ActivityOut]:
    task_ids = {a.task_id for a in activities if a.task_id}
    tasks = await deals.rows_by_id(session, Task, task_ids)
    users = await deals.users_by_id(
        session,
        {a.created_by for a in activities} | {t.assignee_id for t in tasks.values()},
    )
    today = utcnow().date()
    out = []
    for a in activities:
        task = tasks.get(a.task_id) if a.task_id else None
        out.append(
            ActivityOut(
                id=a.id,
                project_id=a.project_id,
                kind=a.kind,
                occurred_on=a.occurred_on,
                participants=a.participants,
                body=a.body,
                next_action=a.next_action,
                task=ActivityTask(
                    id=task.id,
                    title=task.title,
                    status=task.status,
                    assignee=deals.brief(users.get(task.assignee_id)) if task.assignee_id else None,
                    due_date=task.due_date,
                    overdue=task.status != TaskStatus.done
                    and task.due_date is not None
                    and task.due_date < today,
                )
                if task
                else None,
                created_by=deals.brief(users.get(a.created_by)) if a.created_by else None,
                created_at=a.created_at,
            )
        )
    return out


@router.get(
    "/projects/{project_id}/activities",
    response_model=list[ActivityOut],
    summary="商談メモ一覧",
)
async def list_activities(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[ActivityOut]:
    await _project(project_id, actor, session)
    rows = list(
        (
            await session.exec(
                select(Activity)
                .where(Activity.project_id == project_id)
                .order_by(col(Activity.occurred_on).desc(), col(Activity.created_at).desc())
            )
        ).all()
    )
    return await _outs(session, rows)


async def _check_assignee(session: AsyncSession, project: Project, user_id: UUID) -> None:
    """Sales of the company or members who can work on the project."""
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Assignee not found")
    target = await load_actor(user, session)
    if target.can_sell(project.company_id):
        return
    level = await project_level(project, target, session)
    if level is None or level < Level.write:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Assignee cannot work on this project"
        )


@router.post(
    "/projects/{project_id}/activities",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
    summary="商談メモの追加",
)
async def create_activity(
    project_id: UUID, body: ActivityBody, actor: CurrentActor, session: Session
) -> ActivityOut:
    project = await _project(project_id, actor, session, write=True)
    activity = Activity(
        project_id=project_id,
        kind=body.kind,
        occurred_on=body.occurred_on,
        participants=(body.participants or "").strip() or None,
        body=body.body.strip(),
        next_action=(body.next_action or "").strip() or None,
        created_by=actor.user.id,
    )
    if activity.next_action:
        assignee = body.next_action_assignee_id or actor.user.id
        await _check_assignee(session, project, assignee)
        task = Task(
            project_id=project_id,
            number=await task_service.next_number(session, project_id),
            position=await task_service.next_position(session, project_id),
            kind=TaskKind.other,
            title=activity.next_action,
            assignee_id=assignee,
            due_date=body.next_action_due,
            created_by=actor.user.id,
        )
        session.add(task)
        await session.flush()
        activity.task_id = task.id
        # The pipeline card shows the latest next action.
        project.next_action = activity.next_action
        project.next_action_on = body.next_action_due
        session.add(project)
    session.add(activity)
    await session.commit()
    if activity.task_id is not None:
        made = await session.get(Task, activity.task_id)
        if made is not None:
            await repo_sync.push_task(session, made)
    return (await _outs(session, [activity]))[0]


async def _load(
    activity_id: UUID, actor: Actor, session: AsyncSession, write: bool = False
) -> Activity:
    activity = await session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await _project(activity.project_id, actor, session, write=write)
    return activity


@router.patch("/activities/{activity_id}", response_model=ActivityOut, summary="商談メモの更新")
async def update_activity(
    activity_id: UUID, body: ActivityUpdate, actor: CurrentActor, session: Session
) -> ActivityOut:
    """The next action is edited on its task."""
    activity = await _load(activity_id, actor, session, write=True)
    fields = body.model_dump(exclude_unset=True)
    if body.kind is not None:
        activity.kind = body.kind
    if body.occurred_on is not None:
        activity.occurred_on = body.occurred_on
    if "participants" in fields:
        activity.participants = (body.participants or "").strip() or None
    if body.body is not None:
        activity.body = body.body.strip()
    activity.updated_at = utcnow()
    session.add(activity)
    await session.commit()
    return (await _outs(session, [activity]))[0]


@router.delete(
    "/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="商談メモの削除",
)
async def delete_activity(activity_id: UUID, actor: CurrentActor, session: Session) -> None:
    """The next action's task stays."""
    activity = await _load(activity_id, actor, session, write=True)
    await session.delete(activity)
    await session.commit()
