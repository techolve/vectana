import re
from collections import defaultdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import (
    Actor,
    Level,
    accessible_project,
    get_actor,
    project_level,
    visible_projects_clause,
)
from app.core.config import settings
from app.core.database import get_session
from app.core.tokens import Caller, caller_project, get_caller
from app.models.eol import EolFinding, EolStatus, Runtime
from app.models.organization import Company, CompanyType, Department
from app.models.package import MatchStatus, Package, VulnMatch
from app.models.project import (
    ARCHIVED_STATUSES,
    DELIVERY_STATUSES,
    Project,
    ProjectMember,
    ProjectRole,
    ProjectWebhook,
)
from app.models.task import Task, TaskKind, TaskStatus
from app.models.user import User
from app.routers.vulnerability import upgrade_out
from app.schemas.project import (
    DashboardOut,
    EolCounts,
    ImportResult,
    MemberBody,
    MemberOut,
    MemberUpdate,
    PackageBody,
    PackageOut,
    ProjectBody,
    ProjectOut,
    ProjectUpdate,
    SeverityCounts,
    SkippedTool,
    WebhookBody,
    WebhookOut,
)
from app.schemas.sales import CustomerBrief
from app.services import deals, eol, lockfile, toolfile, upgrade
from app.services import tasks as security_tasks
from app.services.notify import digest
from app.services.scanner import scan_and_notify

router = APIRouter(prefix="/api", tags=["projects"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
# Endpoints CI may call with a project API token.
CurrentCaller = Annotated[Caller, Depends(get_caller)]

MAX_LOCKFILE_BYTES = 10 * 1024 * 1024


def _schedule_scan(tasks: BackgroundTasks, package_ids: list[UUID]) -> None:
    if settings.scan_on_change and package_ids:
        tasks.add_task(scan_and_notify, package_ids)


async def _open_counts(
    session: AsyncSession, project_ids: list[UUID]
) -> dict[UUID, SeverityCounts]:
    counts: dict[UUID, SeverityCounts] = defaultdict(SeverityCounts)
    if not project_ids:
        return counts
    rows = (
        await session.exec(
            select(Package.project_id, VulnMatch.severity, func.count())
            .join(Package, col(Package.id) == VulnMatch.package_id)
            .where(
                col(Package.project_id).in_(project_ids),
                VulnMatch.status == MatchStatus.open,
            )
            .group_by(col(Package.project_id), col(VulnMatch.severity))
        )
    ).all()
    for project_id, severity, n in rows:
        setattr(counts[project_id], severity, n)
    return counts


async def _package_counts(session: AsyncSession, project_ids: list[UUID]) -> dict[UUID, int]:
    if not project_ids:
        return {}
    rows = (
        await session.exec(
            select(Package.project_id, func.count())
            .where(col(Package.project_id).in_(project_ids))
            .group_by(col(Package.project_id))
        )
    ).all()
    return dict(rows)


async def _eol_counts(session: AsyncSession, project_ids: list[UUID]) -> dict[UUID, EolCounts]:
    counts: dict[UUID, EolCounts] = defaultdict(EolCounts)
    if not project_ids:
        return counts
    rows = (
        await session.exec(
            select(EolFinding.project_id, EolFinding.status, func.count())
            .where(
                col(EolFinding.project_id).in_(project_ids),
                col(EolFinding.status).in_([EolStatus.eol, EolStatus.approaching]),
            )
            .group_by(col(EolFinding.project_id), col(EolFinding.status))
        )
    ).all()
    for project_id, status_, n in rows:
        setattr(counts[project_id], status_, n)
    return counts


async def _last_scans(session: AsyncSession, project_ids: list[UUID]) -> dict[UUID, datetime]:
    if not project_ids:
        return {}
    rows = (
        await session.exec(
            select(Package.project_id, func.max(Package.last_scanned_at))
            .where(col(Package.project_id).in_(project_ids))
            .group_by(col(Package.project_id))
        )
    ).all()
    return {pid: ts for pid, ts in rows if ts is not None}


async def project_rows(
    session: AsyncSession, projects: list[Project], actor: Actor | None = None
) -> list[ProjectOut]:
    ids = [p.id for p in projects]
    counts = await _open_counts(session, ids)
    packages = await _package_counts(session, ids)
    eol_counts = await _eol_counts(session, ids)
    scans = await _last_scans(session, ids)
    security = await _open_security_tasks(session, ids)
    rows = [
        _project_out(
            p,
            counts[p.id],
            packages.get(p.id, 0),
            eol_counts=eol_counts[p.id],
            last_scanned_at=scans.get(p.id),
        )
        for p in projects
    ]
    for row in rows:
        row.open_security_tasks = security.get(row.id, 0)
    await _fill_people_and_money(session, projects, rows, actor)
    return rows


async def _open_security_tasks(session: AsyncSession, project_ids: list[UUID]) -> dict[UUID, int]:
    if not project_ids:
        return {}
    rows = await session.exec(
        select(Task.project_id, func.count())
        .where(
            col(Task.project_id).in_(project_ids),
            Task.kind == TaskKind.security,
            Task.status != TaskStatus.done,
        )
        .group_by(col(Task.project_id))
    )
    return {pid: n for pid, n in rows.all()}


async def _fill_people_and_money(
    session: AsyncSession,
    projects: list[Project],
    rows: list[ProjectOut],
    actor: Actor | None,
) -> None:
    users = await deals.users_by_id(
        session, {p.manager_id for p in projects} | {p.sales_owner_id for p in projects}
    )
    for p, row in zip(projects, rows, strict=True):
        row.manager = deals.brief(users.get(p.manager_id) if p.manager_id else None)
    # Partner (BP) users see tasks and vulnerabilities only.
    if actor is None or not actor.sees_money:
        return
    customers = await deals.customers_by_id(session, {p.customer_id for p in projects})
    totals = await deals.estimate_totals(session, [p.id for p in projects])
    for p, row in zip(projects, rows, strict=True):
        customer = customers.get(p.customer_id) if p.customer_id else None
        t = totals[p.id]
        row.status = p.status
        row.customer = CustomerBrief(id=customer.id, name=customer.name) if customer else None
        row.sales_owner = deals.brief(users.get(p.sales_owner_id) if p.sales_owner_id else None)
        row.ordered_on = p.ordered_on
        row.expected_amount = p.expected_amount
        row.probability = p.probability
        row.next_action = p.next_action
        row.next_action_on = p.next_action_on
        row.lost_reason = p.lost_reason
        row.competitor = p.competitor
        row.estimate_count = t.count
        row.open_estimate_amount = t.open_amount
        row.won_amount = t.won_amount
        row.monthly_amount = t.monthly_amount
        row.can_sell = actor.can_sell(p.company_id)


def _project_out(
    p: Project,
    counts: SeverityCounts,
    packages: int,
    level: Level | None = None,
    eol_counts: EolCounts | None = None,
    last_scanned_at: datetime | None = None,
) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        company_id=p.company_id,
        department_id=p.department_id,
        name=p.name,
        description=p.description,
        created_at=p.created_at,
        method=p.method,
        security_threshold=p.security_threshold,
        archived=p.status in ARCHIVED_STATUSES,
        is_deal=p.is_deal,
        starts_on=p.starts_on,
        ends_on=p.ends_on,
        package_count=packages,
        open_counts=counts,
        eol_counts=eol_counts or EolCounts(),
        last_scanned_at=last_scanned_at,
        my_level=level.name if level else None,
    )


# --- Projects ----------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut], summary="プロジェクト一覧")
async def list_projects(
    actor: CurrentActor,
    session: Session,
    customer_id: Annotated[UUID | None, Query()] = None,
) -> list[ProjectOut]:
    """Every visible project, archived (保留・失注) ones included; the web app
    splits them into tabs."""
    query = select(Project).where(visible_projects_clause(actor)).order_by(Project.name)
    if customer_id is not None:
        query = query.where(Project.customer_id == customer_id)
    projects = list((await session.exec(query)).all())
    return await project_rows(session, projects, actor)


async def _check_department(
    session: AsyncSession, department_id: UUID | None, company_id: UUID
) -> None:
    if department_id is None:
        return
    dept = await session.get(Department, department_id)
    if dept is None or dept.company_id != company_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Department must be in the same company",
        )


@router.post(
    "/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    summary="プロジェクトの作成",
)
async def create_project(body: ProjectBody, actor: CurrentActor, session: Session) -> ProjectOut:
    if actor.is_partner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Partner users cannot create projects")
    company_id = body.company_id or actor.user.company_id
    if company_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "company_id is required")
    company = await session.get(Company, company_id)
    if company is None or company.type == CompanyType.partner:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Projects belong to a group company"
        )
    if company_id != actor.user.company_id and not actor.is_group_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for this company")
    await _check_department(session, body.department_id, company_id)
    deal_fields = SALES_FIELDS & body.model_dump(exclude_defaults=True).keys()
    if (deal_fields or body.status not in DELIVERY_STATUSES) and not actor.can_sell(company_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only sales and administrators can create deals"
        )
    await deals.check_customer(session, body.customer_id, company_id)
    await deals.check_user(session, body.sales_owner_id)
    await deals.check_user(session, body.manager_id)

    project = Project(
        company_id=company_id,
        department_id=body.department_id,
        name=body.name.strip(),
        description=body.description,
        method=body.method,
        customer_id=body.customer_id,
        sales_owner_id=body.sales_owner_id,
        manager_id=body.manager_id,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        expected_amount=body.expected_amount,
        probability=body.probability,
        next_action=body.next_action,
        next_action_on=body.next_action_on,
    )
    deals.apply_status(project, body.status)
    session.add(project)
    await session.flush()
    # The creator owns the project so it is never orphaned from their view.
    session.add(ProjectMember(project_id=project.id, user_id=actor.user.id, role=ProjectRole.owner))
    await session.commit()
    row = (await project_rows(session, [project], actor))[0]
    row.my_level = Level.manage.name
    return row


@router.get("/projects/{project_id}", response_model=ProjectOut, summary="プロジェクト詳細")
async def get_project(project_id: UUID, actor: CurrentActor, session: Session) -> ProjectOut:
    project = await accessible_project(project_id, actor, session)
    level = await project_level(project, actor, session)
    row = (await project_rows(session, [project], actor))[0]
    row.my_level = level.name if level else None
    return row


# Fields only sales (and admins) change: the deal side of a project.
SALES_FIELDS = {
    "customer_id",
    "sales_owner_id",
    "ordered_on",
    "expected_amount",
    "probability",
    "next_action",
    "next_action_on",
    "lost_reason",
    "competitor",
}


@router.patch("/projects/{project_id}", response_model=ProjectOut, summary="プロジェクトの更新")
async def update_project(
    project_id: UUID, body: ProjectUpdate, actor: CurrentActor, session: Session
) -> ProjectOut:
    """Project managers edit delivery fields; status and the deal fields need
    sales (or admin) rights, except moving between delivery statuses."""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    level = await project_level(project, actor, session)
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    fields = body.model_dump(exclude_unset=True)
    selling = actor.can_sell(project.company_id)
    status_change = body.status is not None and body.status != project.status
    delivery_move = (
        status_change and project.status in DELIVERY_STATUSES and body.status in DELIVERY_STATUSES
    )
    needs_sales = bool(SALES_FIELDS & fields.keys()) or (status_change and not delivery_move)
    other = fields.keys() - SALES_FIELDS - {"status"}
    if needs_sales and not selling:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
    if (other or delivery_move) and level < Level.manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")

    if "department_id" in fields:
        await _check_department(session, body.department_id, project.company_id)
        project.department_id = body.department_id
    if "customer_id" in fields:
        await deals.check_customer(session, body.customer_id, project.company_id)
        project.customer_id = body.customer_id
    for key in ("sales_owner_id", "manager_id"):
        if key in fields:
            await deals.check_user(session, fields[key])
            setattr(project, key, fields[key])
    if body.name is not None:
        project.name = body.name.strip()
    for key in (
        "description",
        "ordered_on",
        "starts_on",
        "ends_on",
        "expected_amount",
        "probability",
        "next_action",
        "next_action_on",
        "lost_reason",
        "competitor",
    ):
        if key in fields:
            setattr(project, key, fields[key])
    if body.method is not None:
        project.method = body.method
    if body.security_threshold is not None:
        project.security_threshold = body.security_threshold.value
    if body.status is not None:
        deals.apply_status(project, body.status)
    session.add(project)
    await session.commit()
    if "security_threshold" in fields:
        await security_tasks.sync(session, [project.id])
    return await get_project(project_id, actor, session)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="プロジェクトの削除",
)
async def delete_project(project_id: UUID, actor: CurrentActor, session: Session) -> None:
    project = await accessible_project(project_id, actor, session, Level.manage)
    await session.delete(project)
    await session.commit()


# --- Members -----------------------------------------------------------------


@router.get(
    "/projects/{project_id}/members",
    response_model=list[MemberOut],
    summary="メンバー一覧",
)
async def list_members(project_id: UUID, actor: CurrentActor, session: Session) -> list[MemberOut]:
    await accessible_project(project_id, actor, session)
    rows = (
        await session.exec(
            select(ProjectMember, User)
            .join(User, col(User.id) == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.email)
        )
    ).all()
    return [
        MemberOut(
            id=m.id,
            user_id=u.id,
            email=u.email,
            display_name=u.display_name,
            company_id=u.company_id,
            role=m.role,
        )
        for m, u in rows
    ]


async def _check_member_role(user: User, role: ProjectRole, session: AsyncSession) -> None:
    if role != ProjectRole.owner or user.company_id is None:
        return
    company = await session.get(Company, user.company_id)
    if company is not None and company.type == CompanyType.partner:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Partner users cannot be project owners",
        )


@router.post(
    "/projects/{project_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="メンバーのアサイン",
)
async def add_member(
    project_id: UUID, body: MemberBody, actor: CurrentActor, session: Session
) -> MemberOut:
    await accessible_project(project_id, actor, session, Level.manage)
    user = await session.get(User, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    await _check_member_role(user, body.role, session)
    member = ProjectMember(project_id=project_id, user_id=user.id, role=body.role)
    session.add(member)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        company_id=user.company_id,
        role=member.role,
    )


async def _get_member(project_id: UUID, member_id: UUID, session: AsyncSession) -> ProjectMember:
    member = await session.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


@router.patch(
    "/projects/{project_id}/members/{member_id}",
    response_model=MemberOut,
    summary="ロール変更",
)
async def update_member(
    project_id: UUID,
    member_id: UUID,
    body: MemberUpdate,
    actor: CurrentActor,
    session: Session,
) -> MemberOut:
    await accessible_project(project_id, actor, session, Level.manage)
    member = await _get_member(project_id, member_id, session)
    user = await session.get(User, member.user_id)
    assert user is not None
    await _check_member_role(user, body.role, session)
    member.role = body.role
    session.add(member)
    await session.commit()
    return MemberOut(
        id=member.id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        company_id=user.company_id,
        role=member.role,
    )


@router.delete(
    "/projects/{project_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="アサイン解除",
)
async def remove_member(
    project_id: UUID, member_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.manage)
    member = await _get_member(project_id, member_id, session)
    await session.delete(member)
    await session.commit()


# --- Webhooks ----------------------------------------------------------------


def _webhook_out(w: ProjectWebhook) -> WebhookOut:
    return WebhookOut(
        id=w.id,
        type=w.type,
        url=w.url,
        min_severity=w.min_severity,
        locale=w.locale,
        enabled=w.enabled,
    )


@router.get(
    "/projects/{project_id}/webhooks",
    response_model=list[WebhookOut],
    summary="Webhook一覧",
)
async def list_webhooks(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[WebhookOut]:
    await accessible_project(project_id, actor, session, Level.manage)
    rows = (
        await session.exec(select(ProjectWebhook).where(ProjectWebhook.project_id == project_id))
    ).all()
    return [_webhook_out(w) for w in rows]


@router.post(
    "/projects/{project_id}/webhooks",
    response_model=WebhookOut,
    status_code=status.HTTP_201_CREATED,
    summary="Webhookの登録",
)
async def create_webhook(
    project_id: UUID, body: WebhookBody, actor: CurrentActor, session: Session
) -> WebhookOut:
    await accessible_project(project_id, actor, session, Level.manage)
    hook = ProjectWebhook(project_id=project_id, **body.model_dump())
    session.add(hook)
    await session.commit()
    return _webhook_out(hook)


async def _get_webhook(project_id: UUID, webhook_id: UUID, session: AsyncSession) -> ProjectWebhook:
    hook = await session.get(ProjectWebhook, webhook_id)
    if hook is None or hook.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found")
    return hook


@router.put(
    "/projects/{project_id}/webhooks/{webhook_id}",
    response_model=WebhookOut,
    summary="Webhookの更新",
)
async def update_webhook(
    project_id: UUID,
    webhook_id: UUID,
    body: WebhookBody,
    actor: CurrentActor,
    session: Session,
) -> WebhookOut:
    await accessible_project(project_id, actor, session, Level.manage)
    hook = await _get_webhook(project_id, webhook_id, session)
    for key, value in body.model_dump().items():
        setattr(hook, key, value)
    session.add(hook)
    await session.commit()
    return _webhook_out(hook)


@router.delete(
    "/projects/{project_id}/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Webhookの削除",
)
async def delete_webhook(
    project_id: UUID, webhook_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.manage)
    await session.delete(await _get_webhook(project_id, webhook_id, session))
    await session.commit()


@router.post(
    "/projects/{project_id}/webhooks/{webhook_id}/test",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Webhookのテスト送信",
)
async def test_webhook(
    project_id: UUID, webhook_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.manage)
    hook = await _get_webhook(project_id, webhook_id, session)
    try:
        await digest.send_test(hook.type, hook.url, hook.locale)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Webhook failed: {exc}") from exc


# --- Packages ----------------------------------------------------------------


async def _package_out(session: AsyncSession, packages: list[Package]) -> list[PackageOut]:
    ids = [p.id for p in packages]
    open_counts: dict[UUID, int] = {}
    if ids:
        open_counts = dict(
            (
                await session.exec(
                    select(VulnMatch.package_id, func.count())
                    .where(
                        col(VulnMatch.package_id).in_(ids),
                        VulnMatch.status == MatchStatus.open,
                    )
                    .group_by(col(VulnMatch.package_id))
                )
            ).all()
        )
    upgrades = await upgrade.for_packages(session, {p.id: p.version for p in packages})
    return [
        PackageOut(
            id=p.id,
            ecosystem=p.ecosystem,
            name=p.name,
            version=p.version,
            source=p.source,
            last_scanned_at=p.last_scanned_at,
            open_vulns=open_counts.get(p.id, 0),
            upgrade=upgrade_out(upgrades.get(p.id)),
        )
        for p in packages
    ]


@router.get(
    "/projects/{project_id}/packages",
    response_model=list[PackageOut],
    summary="パッケージ一覧",
)
async def list_packages(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[PackageOut]:
    await accessible_project(project_id, actor, session)
    packages = list(
        (
            await session.exec(
                select(Package)
                .where(Package.project_id == project_id)
                .order_by(Package.ecosystem, Package.name, Package.version)
            )
        ).all()
    )
    return await _package_out(session, packages)


@router.post(
    "/projects/{project_id}/packages",
    response_model=PackageOut,
    status_code=status.HTTP_201_CREATED,
    summary="パッケージの登録",
)
async def add_package(
    project_id: UUID,
    body: PackageBody,
    tasks: BackgroundTasks,
    actor: CurrentActor,
    session: Session,
) -> PackageOut:
    await accessible_project(project_id, actor, session, Level.write)
    package = Package(project_id=project_id, **body.model_dump())
    session.add(package)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Package already registered")
    _schedule_scan(tasks, [package.id])
    return (await _package_out(session, [package]))[0]


@router.delete(
    "/projects/{project_id}/packages/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="パッケージの削除",
)
async def delete_package(
    project_id: UUID, package_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.write)
    package = await session.get(Package, package_id)
    if package is None or package.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    await session.delete(package)
    await session.commit()
    await security_tasks.sync(session, [project_id])


_SOURCE_NAME = re.compile(r"^[A-Za-z0-9._/@+-]{1,80}$")


@router.post(
    "/projects/{project_id}/packages/import",
    response_model=ImportResult,
    summary="lockfile・SBOMから取り込み",
)
async def import_lockfile(
    project_id: UUID,
    file: UploadFile,
    tasks: BackgroundTasks,
    caller: CurrentCaller,
    session: Session,
    source: Annotated[str | None, Form(description="取り込み元の名前（既定はファイル名）")] = None,
) -> ImportResult:
    """Sync packages from a lockfile or an SBOM (CycloneDX / SPDX), or runtimes
    from mise.toml / .tool-versions. Callable with a project API token.

    Re-importing under the same source name (the filename unless ``source`` is
    given) replaces what that source previously contributed; manual entries and
    other sources are untouched."""
    await caller_project(project_id, caller, session, Level.write)
    raw = await file.read(MAX_LOCKFILE_BYTES + 1)
    if len(raw) > MAX_LOCKFILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    filename = (file.filename or "").rsplit("/", 1)[-1]
    if source is not None and not _SOURCE_NAME.match(source):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "source must be 1-80 characters of letters, digits and ._/@+-",
        )
    if toolfile.is_tool_file(filename):
        return await _import_tool_file(project_id, filename, raw, tasks, session)
    try:
        parsed = lockfile.parse(filename, raw.decode("utf-8"))
    except lockfile.UnsupportedLockfile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Could not parse {filename}: {exc}"
        ) from exc

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
    _schedule_scan(tasks, [p.id for p in added])
    return ImportResult(
        filename=filename,
        format=parsed.format,
        ecosystem=", ".join(parsed.ecosystems) or parsed.format,
        added=len(added),
        removed=removed,
        total=len(wanted),
        unsupported=parsed.unsupported,
    )


async def _import_tool_file(
    project_id: UUID,
    filename: str,
    raw: bytes,
    tasks: BackgroundTasks,
    session: AsyncSession,
) -> ImportResult:
    try:
        entries = toolfile.parse(filename, raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Could not parse {filename}: {exc}"
        ) from exc
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

    source = f"file:{filename}"
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
    if settings.scan_on_change and (added or removed):
        tasks.add_task(scan_and_notify, None, [project_id])
    return ImportResult(
        filename=filename,
        kind="runtimes",
        ecosystem="endoflife.date",
        added=added,
        removed=removed,
        total=len(wanted),
        skipped=skipped,
    )


@router.post(
    "/projects/{project_id}/scan",
    status_code=status.HTTP_202_ACCEPTED,
    summary="今すぐスキャン",
)
async def scan_project(
    project_id: UUID, tasks: BackgroundTasks, caller: CurrentCaller, session: Session
) -> dict[str, int]:
    """Callable with a project API token."""
    await caller_project(project_id, caller, session, Level.write)
    ids = list(
        (await session.exec(select(Package.id).where(Package.project_id == project_id))).all()
    )
    tasks.add_task(scan_and_notify, ids)
    return {"packages": len(ids)}


# --- Dashboard ---------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardOut, summary="ダッシュボード")
async def dashboard(actor: CurrentActor, session: Session) -> DashboardOut:
    from app.routers.eol import list_findings
    from app.routers.vulnerability import list_matches, triage_counts

    projects = list(
        (
            await session.exec(
                select(Project).where(visible_projects_clause(actor)).order_by(Project.name)
            )
        ).all()
    )
    rows = await project_rows(session, projects, actor)
    totals = SeverityCounts()
    eol_totals = EolCounts()
    for row in rows:
        for key in SeverityCounts.model_fields:
            setattr(totals, key, getattr(totals, key) + getattr(row.open_counts, key))
        eol_totals.eol += row.eol_counts.eol
        eol_totals.approaching += row.eol_counts.approaching
    # Riskiest projects first: CRITICAL, HIGH, EOL reached, then everything else.
    rows.sort(
        key=lambda r: (
            -r.open_counts.CRITICAL,
            -r.open_counts.HIGH,
            -r.eol_counts.eol,
            -(r.open_counts.MEDIUM + r.open_counts.LOW + r.eol_counts.approaching),
            r.name,
        )
    )
    return DashboardOut(
        project_count=len(rows),
        package_count=sum(r.package_count for r in rows),
        open_counts=totals,
        eol_counts=eol_totals,
        triage=await triage_counts(actor, session),
        projects=rows,
        recent=await list_matches(actor, session, None, "open", None, None, False, 20),
        eol=await list_findings(actor, session, None, [EolStatus.eol, EolStatus.approaching], 20),
    )
