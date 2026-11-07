"""Estimates of a project.

Everyone on the project except partner (BP) users sees amounts, effort and
margin. Per-person unit costs and the total cost are shown only to admins,
sales and accounting of the project's company. Sales and admins edit.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, accessible_project, get_actor
from app.core.database import get_session
from app.models.base import utcnow
from app.models.estimate import Estimate, EstimateLine, EstimateStatus
from app.models.project import Project, ProjectStatus
from app.schemas.sales import (
    EstimateBody,
    EstimateLineIn,
    EstimateLineOut,
    EstimateOut,
    EstimateUpdate,
)
from app.services import deals

router = APIRouter(prefix="/api", tags=["estimates"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]

SALES_STAGES = {ProjectStatus.inquiry, ProjectStatus.proposal, ProjectStatus.negotiation}


async def _project_for_money(project_id: UUID, actor: Actor, session: AsyncSession) -> Project:
    project = await accessible_project(project_id, actor, session)
    if not actor.sees_money:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for partner users")
    return project


def _require_sell(actor: Actor, project: Project) -> None:
    if not actor.can_sell(project.company_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only sales and administrators can edit")


async def _outs(
    session: AsyncSession, actor: Actor, project: Project, estimates: list[Estimate]
) -> list[EstimateOut]:
    ids = [e.id for e in estimates]
    lines = (
        list(
            (
                await session.exec(
                    select(EstimateLine)
                    .where(col(EstimateLine.estimate_id).in_(ids))
                    .order_by(col(EstimateLine.position))
                )
            ).all()
        )
        if ids
        else []
    )
    users = await deals.users_by_id(session, {line.user_id for line in lines})
    show_cost = actor.can_see_unit_cost(project.company_id)
    out = []
    for e in estimates:
        own = [line for line in lines if line.estimate_id == e.id]
        effort, cost, margin = deals.effort_and_cost(e, own)
        out.append(
            EstimateOut(
                id=e.id,
                project_id=e.project_id,
                title=e.title,
                kind=e.kind,
                status=e.status,
                billing=e.billing,
                amount=e.amount,
                effort_days=effort,
                margin=margin,
                cost=cost if show_cost else None,
                issued_on=e.issued_on,
                due_on=e.due_on,
                valid_until=e.valid_until,
                decided_on=e.decided_on,
                lost_reason=e.lost_reason,
                competitor=e.competitor,
                notes=e.notes,
                created_at=e.created_at,
                updated_at=e.updated_at,
                lines=[
                    EstimateLineOut(
                        id=line.id,
                        label=line.label,
                        user=deals.brief(users.get(line.user_id) if line.user_id else None),
                        days=line.days,
                        unit_cost=line.unit_cost if show_cost else None,
                        cost=(
                            round(line.days * line.unit_cost)
                            if show_cost and line.unit_cost is not None
                            else None
                        ),
                    )
                    for line in own
                ],
            )
        )
    return out


async def _replace_lines(
    session: AsyncSession, estimate: Estimate, entries: list[EstimateLineIn]
) -> None:
    await session.exec(delete(EstimateLine).where(col(EstimateLine.estimate_id) == estimate.id))
    users = await deals.users_by_id(session, {e.user_id for e in entries})
    for i, entry in enumerate(entries):
        if entry.user_id is not None and entry.user_id not in users:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "User not found")
        unit_cost = entry.unit_cost
        if unit_cost is None and entry.user_id is not None:
            unit_cost = users[entry.user_id].unit_cost
        session.add(
            EstimateLine(
                estimate_id=estimate.id,
                position=i,
                label=entry.label.strip(),
                user_id=entry.user_id,
                days=entry.days,
                unit_cost=unit_cost,
            )
        )


def _on_decided(project: Project, estimate: Estimate) -> None:
    """Winning an estimate of a deal makes the project 受注."""
    if estimate.status in (EstimateStatus.won, EstimateStatus.lost) and not estimate.decided_on:
        estimate.decided_on = date.today()
    if estimate.status == EstimateStatus.won and (
        project.status in SALES_STAGES or project.is_deal
    ):
        deals.apply_status(project, ProjectStatus.won, estimate.decided_on)


@router.get(
    "/projects/{project_id}/estimates",
    response_model=list[EstimateOut],
    summary="見積一覧",
)
async def list_estimates(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[EstimateOut]:
    project = await _project_for_money(project_id, actor, session)
    estimates = list(
        (
            await session.exec(
                select(Estimate)
                .where(Estimate.project_id == project.id)
                .order_by(col(Estimate.created_at).desc())
            )
        ).all()
    )
    return await _outs(session, actor, project, estimates)


@router.post(
    "/projects/{project_id}/estimates",
    response_model=EstimateOut,
    status_code=status.HTTP_201_CREATED,
    summary="見積の作成",
)
async def create_estimate(
    project_id: UUID, body: EstimateBody, actor: CurrentActor, session: Session
) -> EstimateOut:
    project = await _project_for_money(project_id, actor, session)
    _require_sell(actor, project)
    estimate = Estimate(
        project_id=project.id,
        created_by=actor.user.id,
        **body.model_dump(exclude={"lines", "title"}),
        title=body.title.strip(),
    )
    session.add(estimate)
    await session.flush()
    await _replace_lines(session, estimate, body.lines)
    _on_decided(project, estimate)
    session.add(project)
    await session.commit()
    return (await _outs(session, actor, project, [estimate]))[0]


async def _get_estimate(
    estimate_id: UUID, actor: Actor, session: AsyncSession
) -> tuple[Estimate, Project]:
    estimate = await session.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate not found")
    project = await _project_for_money(estimate.project_id, actor, session)
    return estimate, project


@router.get("/estimates/{estimate_id}", response_model=EstimateOut, summary="見積詳細")
async def get_estimate(estimate_id: UUID, actor: CurrentActor, session: Session) -> EstimateOut:
    estimate, project = await _get_estimate(estimate_id, actor, session)
    return (await _outs(session, actor, project, [estimate]))[0]


@router.patch("/estimates/{estimate_id}", response_model=EstimateOut, summary="見積の更新")
async def update_estimate(
    estimate_id: UUID, body: EstimateUpdate, actor: CurrentActor, session: Session
) -> EstimateOut:
    estimate, project = await _get_estimate(estimate_id, actor, session)
    _require_sell(actor, project)
    fields = body.model_dump(exclude_unset=True, exclude={"lines"})
    for key in ("title", "kind", "status", "billing"):
        if fields.get(key, "") is None:
            fields.pop(key)
    for key, value in fields.items():
        setattr(estimate, key, value.strip() if key == "title" else value)
    if body.lines is not None:
        await _replace_lines(session, estimate, body.lines)
    estimate.updated_at = utcnow()
    _on_decided(project, estimate)
    session.add_all([estimate, project])
    await session.commit()
    return (await _outs(session, actor, project, [estimate]))[0]


@router.delete(
    "/estimates/{estimate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="見積の削除",
)
async def delete_estimate(estimate_id: UUID, actor: CurrentActor, session: Session) -> None:
    estimate, project = await _get_estimate(estimate_id, actor, session)
    _require_sell(actor, project)
    await session.delete(estimate)
    await session.commit()
