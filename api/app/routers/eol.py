"""EOL: runtimes registered per project, EOL findings, the product catalog,
and the instance-wide warning window (system settings)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import (
    Actor,
    Level,
    accessible_project,
    get_actor,
    require_group_admin,
    visible_projects_clause,
)
from app.core.config import settings
from app.core.database import get_session
from app.models.eol import AppSettings, EolFinding, EolStatus, Runtime
from app.models.project import Project
from app.schemas.eol import EolFindingOut, ProductOut, RuntimeBody, RuntimeOut, SystemSettings
from app.services import eol
from app.services.scanner import scan_and_notify

router = APIRouter(prefix="/api", tags=["eol"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
GroupAdmin = Annotated[Actor, Depends(require_group_admin)]

STATUS_ORDER = case(
    {"eol": 0, "approaching": 1, "unknown": 2, "supported": 3},
    value=col(EolFinding.status),
    else_=9,
)


def _refresh_later(tasks: BackgroundTasks, project_id: UUID) -> None:
    if settings.scan_on_change:
        tasks.add_task(scan_and_notify, None, [project_id])


# --- Products ------------------------------------------------------------------


@router.get("/eol/products", response_model=list[ProductOut], summary="EOL製品の検索")
async def search_products(
    _: CurrentActor, q: Annotated[str, Query(max_length=100)] = ""
) -> list[ProductOut]:
    async with eol.make_client() as client:
        products = await eol.list_products(client)
    needle = q.strip().lower()
    out = []
    for p in products:
        names = [p.get("name", ""), p.get("label", ""), *(p.get("aliases") or [])]
        if not needle or any(needle in str(n).lower() for n in names):
            out.append(
                ProductOut(
                    name=p["name"], label=p.get("label") or p["name"], category=p.get("category")
                )
            )
    return out[:30]


# --- Runtimes ------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/runtimes", response_model=list[RuntimeOut], summary="ランタイム一覧"
)
async def list_runtimes(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[RuntimeOut]:
    await accessible_project(project_id, actor, session)
    rows = (
        await session.exec(
            select(Runtime).where(Runtime.project_id == project_id).order_by(Runtime.product)
        )
    ).all()
    return [
        RuntimeOut(id=r.id, product=r.product, version=r.version, source=r.source) for r in rows
    ]


@router.post(
    "/projects/{project_id}/runtimes",
    response_model=RuntimeOut,
    status_code=status.HTTP_201_CREATED,
    summary="ランタイムの登録",
)
async def add_runtime(
    project_id: UUID,
    body: RuntimeBody,
    tasks: BackgroundTasks,
    actor: CurrentActor,
    session: Session,
) -> RuntimeOut:
    await accessible_project(project_id, actor, session, Level.write)
    async with eol.make_client() as client:
        if await eol.get_product(client, body.product) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown product")
    runtime = Runtime(project_id=project_id, product=body.product, version=body.version)
    session.add(runtime)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Runtime already registered")
    _refresh_later(tasks, project_id)
    return RuntimeOut(
        id=runtime.id, product=runtime.product, version=runtime.version, source=runtime.source
    )


@router.delete(
    "/projects/{project_id}/runtimes/{runtime_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="ランタイムの削除",
)
async def delete_runtime(
    project_id: UUID, runtime_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.write)
    runtime = await session.get(Runtime, runtime_id)
    if runtime is None or runtime.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Runtime not found")
    await session.delete(runtime)
    await session.commit()


# --- Findings ------------------------------------------------------------------


async def list_findings(
    actor: Actor,
    session: AsyncSession,
    project_id: UUID | None = None,
    statuses: list[str] | None = None,
    limit: int = 500,
) -> list[EolFindingOut]:
    query = (
        select(EolFinding, Project)
        .join(Project, col(Project.id) == EolFinding.project_id)
        .where(visible_projects_clause(actor))
    )
    if project_id is not None:
        query = query.where(EolFinding.project_id == project_id)
    if statuses:
        query = query.where(col(EolFinding.status).in_(statuses))
    query = query.order_by(STATUS_ORDER, col(EolFinding.eol_date), Project.name).limit(limit)
    return [
        EolFindingOut(
            id=f.id,
            project_id=p.id,
            project_name=p.name,
            source="runtime" if f.runtime_id else "package",
            product=f.product,
            product_label=f.product_label,
            version=f.version,
            cycle=f.cycle,
            eol_date=f.eol_date,
            latest=f.latest,
            status=f.status,
            checked_at=f.checked_at,
        )
        for f, p in (await session.exec(query)).all()
    ]


@router.get("/eol", response_model=list[EolFindingOut], summary="EOL一覧")
async def get_findings(
    actor: CurrentActor,
    session: Session,
    project_id: Annotated[UUID | None, Query()] = None,
    status_: Annotated[list[EolStatus] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[EolFindingOut]:
    return await list_findings(actor, session, project_id, [s.value for s in status_ or []], limit)


@router.post(
    "/projects/{project_id}/eol/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    summary="EOLを今すぐ再判定",
)
async def refresh_project(
    project_id: UUID, tasks: BackgroundTasks, actor: CurrentActor, session: Session
) -> None:
    await accessible_project(project_id, actor, session, Level.write)
    tasks.add_task(scan_and_notify, None, [project_id])


# --- System settings -------------------------------------------------------------


@router.get("/settings", response_model=SystemSettings, summary="システム設定")
async def get_settings(_: CurrentActor, session: Session) -> SystemSettings:
    return SystemSettings(eol_warning_days=await eol.warning_days(session))


@router.put("/settings", response_model=SystemSettings, summary="システム設定の更新")
async def put_settings(
    body: SystemSettings, tasks: BackgroundTasks, _: GroupAdmin, session: Session
) -> SystemSettings:
    row = await session.get(AppSettings, 1) or AppSettings(id=1)
    changed = row.eol_warning_days != body.eol_warning_days
    row.eol_warning_days = body.eol_warning_days
    session.add(row)
    await session.commit()
    if changed and settings.scan_on_change:
        # Re-evaluate every finding against the new window (no OSV scan needed).
        tasks.add_task(_refresh_all_eol)
    return body


async def _refresh_all_eol() -> None:
    from app.core.database import AsyncSessionLocal
    from app.services.notify import notify_pending

    async with AsyncSessionLocal() as session:
        await eol.refresh(session)
        await notify_pending(session)
