"""Authorization rules, kept in one place.

Who can see a project:
- group admins: every project
- company admins: every project of their company
- department heads: projects of the departments they head and their sub-departments
- everyone else (including partner/BP users): projects they are assigned to

Hidden projects answer 404 so their existence never leaks; visible but
insufficient access answers 403.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import ColumnElement, or_, true
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models.organization import Company, CompanyType, Department, UserDepartment
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole


class Level(IntEnum):
    read = 1
    write = 2  # packages, vulnerability triage
    manage = 3  # project settings, members, webhooks, delete


ROLE_LEVEL = {
    ProjectRole.viewer: Level.read,
    ProjectRole.member: Level.write,
    ProjectRole.owner: Level.manage,
}


@dataclass
class Actor:
    user: User
    company_type: str | None
    # Departments the user heads, plus all of their descendants.
    managed_department_ids: set[UUID] = field(default_factory=set)

    @property
    def is_group_admin(self) -> bool:
        return self.user.role == UserRole.group_admin

    @property
    def is_company_admin(self) -> bool:
        return self.user.role == UserRole.company_admin

    @property
    def is_partner(self) -> bool:
        return self.company_type == CompanyType.partner

    def can_manage_company(self, company_id: UUID) -> bool:
        return self.is_group_admin or (self.is_company_admin and self.user.company_id == company_id)

    @property
    def can_manage_org(self) -> bool:
        return self.is_group_admin or self.is_company_admin


def descendants(departments: list[Department], roots: set[UUID]) -> set[UUID]:
    children: dict[UUID, list[UUID]] = {}
    for d in departments:
        if d.parent_id is not None:
            children.setdefault(d.parent_id, []).append(d.id)
    result: set[UUID] = set()
    stack = list(roots)
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, []))
    return result


async def load_actor(user: User, session: AsyncSession) -> Actor:
    company_type = None
    if user.company_id is not None:
        company = await session.get(Company, user.company_id)
        company_type = company.type if company else None

    headed = set(
        (
            await session.exec(
                select(UserDepartment.department_id).where(
                    UserDepartment.user_id == user.id,
                    col(UserDepartment.is_head).is_(True),
                )
            )
        ).all()
    )
    managed: set[UUID] = set()
    if headed and user.company_id is not None:
        departments = list(
            (
                await session.exec(
                    select(Department).where(Department.company_id == user.company_id)
                )
            ).all()
        )
        managed = descendants(departments, headed)
    return Actor(user=user, company_type=company_type, managed_department_ids=managed)


async def get_actor(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Actor:
    return await load_actor(user, session)


async def require_org_admin(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
    if not actor.can_manage_org:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return actor


async def require_group_admin(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
    if not actor.is_group_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Group administrator required")
    return actor


def visible_projects_clause(actor: Actor) -> ColumnElement[bool]:
    """SQL condition on ``Project`` matching what the actor may see."""
    if actor.is_group_admin:
        return true()
    member_of = select(ProjectMember.project_id).where(ProjectMember.user_id == actor.user.id)
    conditions: list[ColumnElement[bool]] = [col(Project.id).in_(member_of)]
    if actor.is_company_admin and actor.user.company_id is not None:
        conditions.append(col(Project.company_id) == actor.user.company_id)
    if actor.managed_department_ids:
        conditions.append(col(Project.department_id).in_(actor.managed_department_ids))
    return or_(*conditions)


async def project_level(project: Project, actor: Actor, session: AsyncSession) -> Level | None:
    """The actor's access level on a project, or None if it is hidden."""
    if actor.can_manage_company(project.company_id):
        return Level.manage
    if project.department_id is not None and project.department_id in actor.managed_department_ids:
        return Level.manage
    membership = (
        await session.exec(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == actor.user.id,
            )
        )
    ).first()
    if membership is None:
        return None
    return ROLE_LEVEL[ProjectRole(membership.role)]


async def accessible_project(
    project_id: UUID,
    actor: Actor,
    session: AsyncSession,
    level: Level = Level.read,
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    actual = await project_level(project, actor, session)
    if actual is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if actual < level:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
    return project
