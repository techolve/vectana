from collections import defaultdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import case, func
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
from app.models.eol import EolFinding, EolStatus
from app.models.organization import Company, CompanyType, Department
from app.models.package import MatchStatus, Package, Severity, VulnMatch
from app.models.project import Project, ProjectMember, ProjectRole, ProjectWebhook
from app.models.user import User
from app.schemas.project import (
    DashboardOut,
    EolCounts,
    ImportResult,
    MatchOut,
    MatchUpdate,
    MemberBody,
    MemberOut,
    MemberUpdate,
    PackageBody,
    PackageOut,
    ProjectBody,
    ProjectOut,
    ProjectUpdate,
    SeverityCounts,
    WebhookBody,
    WebhookOut,
)
from app.services import lockfile
from app.services.notify import digest
from app.services.scanner import scan_and_notify

router = APIRouter(prefix="/api", tags=["projects"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]

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


async def project_rows(session: AsyncSession, projects: list[Project]) -> list[ProjectOut]:
    ids = [p.id for p in projects]
    counts = await _open_counts(session, ids)
    packages = await _package_counts(session, ids)
    eol_counts = await _eol_counts(session, ids)
    scans = await _last_scans(session, ids)
    return [
        _project_out(
            p,
            counts[p.id],
            packages.get(p.id, 0),
            eol_counts=eol_counts[p.id],
            last_scanned_at=scans.get(p.id),
        )
        for p in projects
    ]


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
        package_count=packages,
        open_counts=counts,
        eol_counts=eol_counts or EolCounts(),
        last_scanned_at=last_scanned_at,
        my_level=level.name if level else None,
    )


# --- Projects ----------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut], summary="プロジェクト一覧")
async def list_projects(actor: CurrentActor, session: Session) -> list[ProjectOut]:
    projects = list(
        (
            await session.exec(
                select(Project).where(visible_projects_clause(actor)).order_by(Project.name)
            )
        ).all()
    )
    return await project_rows(session, projects)


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
    if body.department_id is not None:
        dept = await session.get(Department, body.department_id)
        if dept is None or dept.company_id != company_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Department must be in the same company",
            )

    project = Project(
        company_id=company_id,
        department_id=body.department_id,
        name=body.name.strip(),
        description=body.description,
    )
    session.add(project)
    await session.flush()
    # The creator owns the project so it is never orphaned from their view.
    session.add(ProjectMember(project_id=project.id, user_id=actor.user.id, role=ProjectRole.owner))
    await session.commit()
    return _project_out(project, SeverityCounts(), 0, Level.manage)


@router.get("/projects/{project_id}", response_model=ProjectOut, summary="プロジェクト詳細")
async def get_project(project_id: UUID, actor: CurrentActor, session: Session) -> ProjectOut:
    project = await accessible_project(project_id, actor, session)
    level = await project_level(project, actor, session)
    row = (await project_rows(session, [project]))[0]
    row.my_level = level.name if level else None
    return row


@router.patch("/projects/{project_id}", response_model=ProjectOut, summary="プロジェクトの更新")
async def update_project(
    project_id: UUID, body: ProjectUpdate, actor: CurrentActor, session: Session
) -> ProjectOut:
    project = await accessible_project(project_id, actor, session, Level.manage)
    fields = body.model_dump(exclude_unset=True)
    if "department_id" in fields:
        if body.department_id is not None:
            dept = await session.get(Department, body.department_id)
            if dept is None or dept.company_id != project.company_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Department must be in the same company",
                )
        project.department_id = body.department_id
    if body.name is not None:
        project.name = body.name.strip()
    if "description" in fields:
        project.description = body.description
    session.add(project)
    await session.commit()
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
    return [
        PackageOut(
            id=p.id,
            ecosystem=p.ecosystem,
            name=p.name,
            version=p.version,
            source=p.source,
            last_scanned_at=p.last_scanned_at,
            open_vulns=open_counts.get(p.id, 0),
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


@router.post(
    "/projects/{project_id}/packages/import",
    response_model=ImportResult,
    summary="lockfileから取り込み",
)
async def import_lockfile(
    project_id: UUID,
    file: UploadFile,
    tasks: BackgroundTasks,
    actor: CurrentActor,
    session: Session,
) -> ImportResult:
    """Sync packages from a lockfile. Re-importing the same filename replaces
    what that file previously contributed; manual entries are untouched."""
    await accessible_project(project_id, actor, session, Level.write)
    raw = await file.read(MAX_LOCKFILE_BYTES + 1)
    if len(raw) > MAX_LOCKFILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    filename = (file.filename or "").rsplit("/", 1)[-1]
    try:
        ecosystem, parsed = lockfile.parse(filename, raw.decode("utf-8"))
    except lockfile.UnsupportedLockfile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Could not parse {filename}: {exc}"
        ) from exc

    source = f"lockfile:{filename}"
    existing = list(
        (
            await session.exec(
                select(Package).where(
                    Package.project_id == project_id, Package.ecosystem == ecosystem
                )
            )
        ).all()
    )
    by_key = {(p.name, p.version): p for p in existing}
    wanted = set(parsed)

    removed = 0
    for p in existing:
        if p.source == source and (p.name, p.version) not in wanted:
            await session.delete(p)
            removed += 1
    added: list[Package] = []
    for name, version in parsed:
        if (name, version) in by_key:
            continue
        pkg = Package(
            project_id=project_id,
            ecosystem=ecosystem,
            name=name,
            version=version,
            source=source,
        )
        session.add(pkg)
        added.append(pkg)
    await session.commit()
    _schedule_scan(tasks, [p.id for p in added])
    return ImportResult(
        filename=filename,
        ecosystem=ecosystem,
        added=len(added),
        removed=removed,
        total=len(wanted),
    )


@router.post(
    "/projects/{project_id}/scan",
    status_code=status.HTTP_202_ACCEPTED,
    summary="今すぐスキャン",
)
async def scan_project(
    project_id: UUID, tasks: BackgroundTasks, actor: CurrentActor, session: Session
) -> dict[str, int]:
    await accessible_project(project_id, actor, session, Level.write)
    ids = list(
        (await session.exec(select(Package.id).where(Package.project_id == project_id))).all()
    )
    tasks.add_task(scan_and_notify, ids)
    return {"packages": len(ids)}


# --- Vulnerability matches ---------------------------------------------------


def _match_query(actor: Actor):  # type: ignore[no-untyped-def]
    return (
        select(VulnMatch, Package, Project)
        .join(Package, col(Package.id) == VulnMatch.package_id)
        .join(Project, col(Project.id) == Package.project_id)
        .where(visible_projects_clause(actor))
    )


def _match_out(m: VulnMatch, pkg: Package, project: Project) -> MatchOut:
    return MatchOut(
        id=m.id,
        project_id=project.id,
        project_name=project.name,
        package_id=pkg.id,
        ecosystem=pkg.ecosystem,
        package_name=pkg.name,
        package_version=pkg.version,
        vuln_id=m.vuln_id,
        aliases=[str(a) for a in m.aliases],
        summary=m.summary,
        severity=m.severity,
        cvss_score=m.cvss_score,
        fixed_version=m.fixed_version,
        status=m.status,
        first_seen_at=m.first_seen_at,
    )


SEVERITY_ORDER = case(
    {s: i for i, s in enumerate(["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"])},
    value=col(VulnMatch.severity),
    else_=9,
)


@router.get("/vulnerabilities", response_model=list[MatchOut], summary="脆弱性ヒット一覧")
async def list_matches(
    actor: CurrentActor,
    session: Session,
    project_id: Annotated[UUID | None, Query()] = None,
    status_: Annotated[str | None, Query(alias="status")] = "open",
    severity: Annotated[Severity | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[MatchOut]:
    query = _match_query(actor)
    if project_id is not None:
        query = query.where(Project.id == project_id)
    if status_:
        query = query.where(VulnMatch.status == status_)
    if severity is not None:
        query = query.where(VulnMatch.severity == severity)
    query = query.order_by(SEVERITY_ORDER, col(VulnMatch.first_seen_at).desc()).limit(limit)
    return [_match_out(m, p, pr) for m, p, pr in (await session.exec(query)).all()]


@router.patch("/vulnerabilities/{match_id}", response_model=MatchOut, summary="対応状況の更新")
async def update_match(
    match_id: UUID, body: MatchUpdate, actor: CurrentActor, session: Session
) -> MatchOut:
    match = await session.get(VulnMatch, match_id)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    package = await session.get(Package, match.package_id)
    assert package is not None
    project = await accessible_project(package.project_id, actor, session, Level.write)
    match.status = body.status
    session.add(match)
    await session.commit()
    return _match_out(match, package, project)


@router.get("/dashboard", response_model=DashboardOut, summary="ダッシュボード")
async def dashboard(actor: CurrentActor, session: Session) -> DashboardOut:
    from app.routers.eol import list_findings

    projects = list(
        (
            await session.exec(
                select(Project).where(visible_projects_clause(actor)).order_by(Project.name)
            )
        ).all()
    )
    rows = await project_rows(session, projects)
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
        projects=rows,
        recent=await list_matches(actor, session, None, "open", None, 20),
        eol=await list_findings(actor, session, None, [EolStatus.eol, EolStatus.approaching], 20),
    )
