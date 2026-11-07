"""Money and people around projects: estimate totals, user briefs, and the
status rules shared by the project and estimate endpoints."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.customer import Customer
from app.models.estimate import (
    OPEN_ESTIMATE_STATUSES,
    Billing,
    Estimate,
    EstimateLine,
    EstimateStatus,
)
from app.models.project import DELIVERY_STATUSES, Project, ProjectStatus
from app.models.user import User
from app.schemas.org import UserBrief


def brief(u: User | None) -> UserBrief | None:
    if u is None:
        return None
    return UserBrief(id=u.id, email=u.email, display_name=u.display_name, company_id=u.company_id)


async def users_by_id(session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, User]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = (await session.exec(select(User).where(col(User.id).in_(wanted)))).all()
    return {u.id: u for u in rows}


async def customers_by_id(session: AsyncSession, ids: set[UUID | None]) -> dict[UUID, Customer]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = (await session.exec(select(Customer).where(col(Customer.id).in_(wanted)))).all()
    return {c.id: c for c in rows}


@dataclass
class Totals:
    count: int = 0
    open_amount: int = 0
    won_amount: int = 0
    monthly_amount: int | None = None
    _monthly_key: tuple[date, int] | None = None


async def estimate_totals(session: AsyncSession, project_ids: list[UUID]) -> dict[UUID, Totals]:
    totals: dict[UUID, Totals] = defaultdict(Totals)
    if not project_ids:
        return totals
    rows = (
        await session.exec(select(Estimate).where(col(Estimate.project_id).in_(project_ids)))
    ).all()
    for e in rows:
        t = totals[e.project_id]
        t.count += 1
        amount = e.amount or 0
        if e.billing == Billing.monthly:
            if e.status == EstimateStatus.won:
                # The most recent won maintenance contract is the current fee.
                key = (e.decided_on or e.created_at.date(), amount)
                if t._monthly_key is None or key > t._monthly_key:
                    t._monthly_key = key
                    t.monthly_amount = amount
            continue
        if e.status in OPEN_ESTIMATE_STATUSES:
            t.open_amount += amount
        elif e.status == EstimateStatus.won:
            t.won_amount += amount
    return totals


def effort_and_cost(
    estimate: Estimate, lines: list[EstimateLine]
) -> tuple[float | None, int | None, float | None]:
    """(effort in person-days, total cost, margin)."""
    if lines:
        effort: float | None = sum(line.days for line in lines)
        costed = [line for line in lines if line.unit_cost is not None]
        cost = round(sum(line.days * (line.unit_cost or 0) for line in costed)) if costed else None
    else:
        effort, cost = estimate.effort_days, None
    margin = None
    if cost is not None and estimate.amount:
        margin = round((estimate.amount - cost) / estimate.amount, 4)
    return effort, cost, margin


def apply_status(project: Project, new: ProjectStatus, today: date | None = None) -> None:
    """Moving into delivery records the order date once."""
    project.status = new
    if new in DELIVERY_STATUSES and project.ordered_on is None:
        project.ordered_on = today or date.today()


async def check_customer(
    session: AsyncSession, customer_id: UUID | None, company_id: UUID
) -> Customer | None:
    if customer_id is None:
        return None
    customer = await session.get(Customer, customer_id)
    if customer is None or customer.company_id != company_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Customer must belong to the same company"
        )
    return customer


async def check_user(session: AsyncSession, user_id: UUID | None) -> User | None:
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "User not found")
    return user


__all__ = [
    "Project",
    "Totals",
    "apply_status",
    "brief",
    "check_customer",
    "check_user",
    "customers_by_id",
    "effort_and_cost",
    "estimate_totals",
    "users_by_id",
]
