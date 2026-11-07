"""Authorization rules, kept in one place.

Who can see a project:
- group admins: every project
- company admins and sales: every project of their company, deals included
- department heads: delivered projects of the departments they head and their
  sub-departments
- accounting: delivered projects of their company (read only)
- PMO: delivered projects of every company (read only)
- everyone else (including partner/BP users): projects they are assigned to

A "deal" is a project that has not been ordered yet (``ordered_on`` is empty):
only sales, admins and its members see it.

Money: partner users never see customers, statuses or amounts. Per-person unit
costs are shown only to admins, sales and accounting of the same company.

Hidden projects answer 404 so their existence never leaks; visible but
insufficient access answers 403.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import ColumnElement, and_, or_, true
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

    def has(self, role: UserRole) -> bool:
        return self.user.has_role(role)

    @property
    def is_group_admin(self) -> bool:
        return self.has(UserRole.group_admin)

    @property
    def is_company_admin(self) -> bool:
        return self.has(UserRole.company_admin)

    @property
    def is_sales(self) -> bool:
        return self.has(UserRole.sales) and not self.is_partner

    @property
    def is_accounting(self) -> bool:
        return self.has(UserRole.accounting) and not self.is_partner

    @property
    def is_pmo(self) -> bool:
        return self.has(UserRole.pmo) and not self.is_partner

    def own_company(self, company_id: UUID) -> bool:
        return self.user.company_id is not None and self.user.company_id == company_id

    def can_sell(self, company_id: UUID) -> bool:
        """Create and edit customers and estimates of this company."""
        return self.can_manage_company(company_id) or (
            self.is_sales and self.own_company(company_id)
        )

    def can_see_customers(self, company_id: UUID) -> bool:
        return (
            self.can_sell(company_id)
            or self.is_pmo
            or (self.is_accounting and self.own_company(company_id))
        )

    def can_see_unit_cost(self, company_id: UUID | None) -> bool:
        """Per-person unit cost (原価) of users or estimates of this company."""
        if self.is_group_admin:
            return True
        if company_id is None or not self.own_company(company_id):
            return False
        return self.is_company_admin or self.is_sales or self.is_accounting

    @property
    def sees_money(self) -> bool:
        """Customers, project status, estimate amounts. Never for BP users."""
        return not self.is_partner

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
    ordered = col(Project.ordered_on).is_not(None)
    own = actor.user.company_id
    if own is not None and (actor.is_company_admin or actor.is_sales):
        conditions.append(col(Project.company_id) == own)
    if own is not None and actor.is_accounting:
        conditions.append(and_(col(Project.company_id) == own, ordered))
    if actor.is_pmo:
        conditions.append(ordered)
    if actor.managed_department_ids:
        conditions.append(
            and_(col(Project.department_id).in_(actor.managed_department_ids), ordered)
        )
    return or_(*conditions)


async def project_level(project: Project, actor: Actor, session: AsyncSession) -> Level | None:
    """The actor's access level on a project, or None if it is hidden."""
    if actor.can_manage_company(project.company_id):
        return Level.manage
    # Sales run the deal; once ordered, delivery takes over and sales keep
    # read access (estimates stay editable through can_sell).
    selling = actor.is_sales and actor.own_company(project.company_id)
    if selling and project.is_deal:
        return Level.manage
    if (
        not project.is_deal
        and project.department_id is not None
        and project.department_id in actor.managed_department_ids
    ):
        return Level.manage
    membership = (
        await session.exec(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == actor.user.id,
            )
        )
    ).first()
    if membership is not None:
        return ROLE_LEVEL[ProjectRole(membership.role)]
    if selling:
        return Level.read
    if not project.is_deal and (
        actor.is_pmo or (actor.is_accounting and actor.own_company(project.company_id))
    ):
        return Level.read
    return None


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
