"""Organization management: companies, departments, users, invitations.

Group admins manage everything; company admins manage their own company.
Creating or deleting companies is reserved for group admins.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import (
    Actor,
    descendants,
    get_actor,
    require_group_admin,
    require_org_admin,
)
from app.core.config import settings
from app.core.database import get_session
from app.models.invitation import Invitation, InvitationStatus
from app.models.organization import Company, CompanyType, Department, UserDepartment
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas.org import (
    CompanyBody,
    CompanyOut,
    DepartmentBody,
    DepartmentOut,
    DepartmentUpdate,
    InvitationBody,
    InvitationOut,
    UserBrief,
    UserDepartmentIn,
    UserDepartmentOut,
    UserOut,
    UserUpdate,
)
from app.services.mailer import send_invitation_email

router = APIRouter(prefix="/api", tags=["organization"])

Session = Annotated[AsyncSession, Depends(get_session)]
OrgAdmin = Annotated[Actor, Depends(require_org_admin)]
GroupAdmin = Annotated[Actor, Depends(require_group_admin)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def _company_out(c: Company) -> CompanyOut:
    return CompanyOut(id=c.id, name=c.name, type=c.type)


def _dept_out(d: Department) -> DepartmentOut:
    return DepartmentOut(id=d.id, company_id=d.company_id, parent_id=d.parent_id, name=d.name)


def _ensure_company_scope(actor: Actor, company_id: UUID) -> None:
    if not actor.can_manage_company(company_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for this company")


async def _get_company(company_id: UUID, session: AsyncSession) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


def _check_role(actor: Actor, role: UserRole, company: Company) -> None:
    if role == UserRole.group_admin and not actor.is_group_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only group admins can grant this role")
    if company.type == CompanyType.partner and role != UserRole.member:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Partner users can only be members"
        )


async def _validate_departments(
    entries: list[UserDepartmentIn], company_id: UUID, session: AsyncSession
) -> None:
    if not entries:
        return
    ids = {e.department_id for e in entries}
    found = (
        await session.exec(
            select(Department.id).where(
                col(Department.id).in_(ids), Department.company_id == company_id
            )
        )
    ).all()
    if len(set(found)) != len(ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Departments must belong to the user's company",
        )
    if sum(1 for e in entries if e.is_primary) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only one primary department allowed"
        )


# --- Companies ---------------------------------------------------------------


@router.get("/companies", response_model=list[CompanyOut], summary="会社一覧")
async def list_companies(actor: CurrentActor, session: Session) -> list[CompanyOut]:
    """Group admins see every company. Others see their own company, and
    managers also see the rest so they can assign people across companies."""
    if actor.is_partner:
        companies = (
            [await _get_company(actor.user.company_id, session)] if actor.user.company_id else []
        )
    else:
        companies = list((await session.exec(select(Company).order_by(Company.name))).all())
    order = {CompanyType.parent: 0, CompanyType.affiliate: 1, CompanyType.partner: 2}
    companies.sort(key=lambda c: (order.get(CompanyType(c.type), 9), c.name))
    return [_company_out(c) for c in companies]


@router.post(
    "/companies",
    response_model=CompanyOut,
    status_code=status.HTTP_201_CREATED,
    summary="会社の作成",
)
async def create_company(body: CompanyBody, _: GroupAdmin, session: Session) -> CompanyOut:
    company = Company(name=body.name.strip(), type=body.type)
    session.add(company)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Company name already exists")
    return _company_out(company)


@router.patch("/companies/{company_id}", response_model=CompanyOut, summary="会社の更新")
async def update_company(
    company_id: UUID, body: CompanyBody, _: GroupAdmin, session: Session
) -> CompanyOut:
    company = await _get_company(company_id, session)
    if body.type == CompanyType.partner and company.type != CompanyType.partner:
        admins = (
            await session.exec(
                select(User.id).where(User.company_id == company_id, User.role != UserRole.member)
            )
        ).first()
        if admins:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Demote this company's administrators before making it a partner",
            )
    company.name = body.name.strip()
    company.type = body.type
    session.add(company)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Company name already exists")
    return _company_out(company)


@router.delete(
    "/companies/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="会社の削除",
)
async def delete_company(company_id: UUID, _: GroupAdmin, session: Session) -> None:
    company = await _get_company(company_id, session)
    in_use = (await session.exec(select(User.id).where(User.company_id == company_id))).first() or (
        await session.exec(select(Project.id).where(Project.company_id == company_id))
    ).first()
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "Company still has users or projects")
    await session.delete(company)
    await session.commit()


# --- Departments -------------------------------------------------------------


@router.get("/departments", response_model=list[DepartmentOut], summary="部署一覧")
async def list_departments(
    actor: CurrentActor,
    session: Session,
    company_id: Annotated[UUID | None, Query()] = None,
) -> list[DepartmentOut]:
    query = select(Department).order_by(Department.name)
    if actor.is_partner:
        query = query.where(Department.company_id == actor.user.company_id)
    elif company_id is not None:
        query = query.where(Department.company_id == company_id)
    return [_dept_out(d) for d in (await session.exec(query)).all()]


async def _check_parent(
    parent_id: UUID | None,
    company_id: UUID,
    session: AsyncSession,
    self_id: UUID | None = None,
) -> None:
    if parent_id is None:
        return
    parent = await session.get(Department, parent_id)
    if parent is None or parent.company_id != company_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Parent must be in the same company"
        )
    if self_id is not None:
        siblings = list(
            (
                await session.exec(select(Department).where(Department.company_id == company_id))
            ).all()
        )
        if parent_id in descendants(siblings, {self_id}):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A department cannot be its own ancestor",
            )


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="部署の作成",
)
async def create_department(
    body: DepartmentBody, actor: OrgAdmin, session: Session
) -> DepartmentOut:
    _ensure_company_scope(actor, body.company_id)
    company = await _get_company(body.company_id, session)
    await _check_parent(body.parent_id, company.id, session)
    dept = Department(company_id=company.id, parent_id=body.parent_id, name=body.name.strip())
    session.add(dept)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Department already exists here")
    return _dept_out(dept)


async def _get_department(dept_id: UUID, actor: Actor, session: AsyncSession) -> Department:
    dept = await session.get(Department, dept_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    _ensure_company_scope(actor, dept.company_id)
    return dept


@router.patch("/departments/{dept_id}", response_model=DepartmentOut, summary="部署の更新")
async def update_department(
    dept_id: UUID, body: DepartmentUpdate, actor: OrgAdmin, session: Session
) -> DepartmentOut:
    dept = await _get_department(dept_id, actor, session)
    fields = body.model_dump(exclude_unset=True)
    if "parent_id" in fields:
        await _check_parent(body.parent_id, dept.company_id, session, self_id=dept.id)
        dept.parent_id = body.parent_id
    if body.name is not None:
        dept.name = body.name.strip()
    session.add(dept)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Department already exists here")
    return _dept_out(dept)


@router.delete(
    "/departments/{dept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="部署の削除",
)
async def delete_department(dept_id: UUID, actor: OrgAdmin, session: Session) -> None:
    dept = await _get_department(dept_id, actor, session)
    child = (
        await session.exec(select(Department.id).where(Department.parent_id == dept.id))
    ).first()
    if child:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delete sub-departments first")
    await session.delete(dept)
    await session.commit()


# --- Users -------------------------------------------------------------------


async def _user_out(users: list[User], session: AsyncSession) -> list[UserOut]:
    ids = [u.id for u in users]
    rows = (
        (
            await session.exec(select(UserDepartment).where(col(UserDepartment.user_id).in_(ids)))
        ).all()
        if ids
        else []
    )
    by_user: dict[UUID, list[UserDepartmentOut]] = {}
    for r in rows:
        by_user.setdefault(r.user_id, []).append(
            UserDepartmentOut(
                department_id=r.department_id,
                is_primary=r.is_primary,
                is_head=r.is_head,
            )
        )
    return [
        UserOut(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
            company_id=u.company_id,
            departments=by_user.get(u.id, []),
        )
        for u in users
    ]


@router.get("/users", response_model=list[UserOut], summary="ユーザー一覧（管理用）")
async def list_users(
    actor: OrgAdmin,
    session: Session,
    company_id: Annotated[UUID | None, Query()] = None,
) -> list[UserOut]:
    query = select(User).order_by(User.email)
    if not actor.is_group_admin:
        query = query.where(User.company_id == actor.user.company_id)
    elif company_id is not None:
        query = query.where(User.company_id == company_id)
    return await _user_out(list((await session.exec(query)).all()), session)


@router.get("/users/directory", response_model=list[UserBrief], summary="アサイン用ユーザー検索")
async def user_directory(
    actor: CurrentActor,
    session: Session,
    q: Annotated[str, Query(max_length=100)] = "",
) -> list[UserBrief]:
    """Active users across the group and partners, for assigning to projects.
    Partner users cannot browse the directory."""
    if actor.is_partner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for partner users")
    query = select(User).where(col(User.is_active).is_(True)).order_by(User.email).limit(50)
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(col(User.email).ilike(pattern) | col(User.display_name).ilike(pattern))
    return [
        UserBrief(id=u.id, email=u.email, display_name=u.display_name, company_id=u.company_id)
        for u in (await session.exec(query)).all()
    ]


@router.patch("/users/{user_id}", response_model=UserOut, summary="ユーザーの更新")
async def update_user(
    user_id: UUID, body: UserUpdate, actor: OrgAdmin, session: Session
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None or (not actor.is_group_admin and user.company_id != actor.user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.role == UserRole.group_admin and not actor.is_group_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot modify a group admin")
    if user.id == actor.user.id and (
        (body.role is not None and body.role != user.role) or body.is_active is False
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "You cannot change your own role or disable yourself",
        )

    if body.role is not None:
        company = await session.get(Company, user.company_id) if user.company_id else None
        if company is not None:
            _check_role(actor, body.role, company)
        elif body.role == UserRole.group_admin and not actor.is_group_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only group admins can grant this role")
        user.role = body.role
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.departments is not None:
        if user.company_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "User has no company")
        await _validate_departments(body.departments, user.company_id, session)
        await session.exec(delete(UserDepartment).where(col(UserDepartment.user_id) == user.id))
        for e in body.departments:
            session.add(
                UserDepartment(
                    user_id=user.id,
                    department_id=e.department_id,
                    is_primary=e.is_primary,
                    is_head=e.is_head,
                )
            )
    session.add(user)
    await session.commit()
    return (await _user_out([user], session))[0]


# --- Invitations -------------------------------------------------------------


def _invitation_out(inv: Invitation, **extra: object) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        display_name=inv.display_name,
        company_id=inv.company_id,
        role=inv.role,
        status=inv.status,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        **extra,  # type: ignore[arg-type]
    )


def accept_url(token: str) -> str:
    return f"{settings.web_url.rstrip('/')}/invite/?token={token}"


@router.get("/invitations", response_model=list[InvitationOut], summary="招待一覧")
async def list_invitations(actor: OrgAdmin, session: Session) -> list[InvitationOut]:
    query = (
        select(Invitation)
        .where(Invitation.status == InvitationStatus.pending)
        .order_by(col(Invitation.created_at).desc())
    )
    if not actor.is_group_admin:
        query = query.where(Invitation.company_id == actor.user.company_id)
    return [_invitation_out(i) for i in (await session.exec(query)).all()]


@router.post(
    "/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
    summary="ユーザーを招待",
)
async def create_invitation(
    body: InvitationBody, actor: OrgAdmin, session: Session
) -> InvitationOut:
    _ensure_company_scope(actor, body.company_id)
    company = await _get_company(body.company_id, session)
    _check_role(actor, body.role, company)
    await _validate_departments(body.departments, company.id, session)

    email = body.email.lower()
    if (await session.exec(select(User.id).where(User.email == email))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    # Re-inviting replaces any pending invitation for the same address.
    for old in (
        await session.exec(
            select(Invitation).where(
                Invitation.email == email, Invitation.status == InvitationStatus.pending
            )
        )
    ).all():
        old.status = InvitationStatus.revoked
        session.add(old)

    invitation = Invitation(
        email=email,
        display_name=body.display_name,
        company_id=company.id,
        role=body.role,
        department_ids=[e.model_dump(mode="json") for e in body.departments],
        token=secrets.token_urlsafe(32),
        invited_by=actor.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.invitation_expire_days),
    )
    session.add(invitation)
    await session.commit()

    url = accept_url(invitation.token)
    sent = await send_invitation_email(to=email, company_name=company.name, accept_url=url)
    return _invitation_out(invitation, email_sent=sent, accept_url=url)


@router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="招待の取り消し",
)
async def revoke_invitation(invitation_id: UUID, actor: OrgAdmin, session: Session) -> None:
    invitation = await session.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    _ensure_company_scope(actor, invitation.company_id)
    invitation.status = InvitationStatus.revoked
    session.add(invitation)
    await session.commit()
