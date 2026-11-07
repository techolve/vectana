"""請求予定: the invoices planned from won estimates.

Sales and admins plan them (split a one-time estimate into installments, or
list the months of maintenance). Accounting of the company, and admins, record
that an invoice was sent (請求済) and paid (入金済); the invoice itself is
issued in the accounting software. Partner users never see invoices."""

import calendar
import csv
import io
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import ColumnElement, and_, or_, true
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, accessible_project, get_actor
from app.core.database import get_session
from app.i18n import request_locale, t
from app.models.base import utcnow
from app.models.customer import Customer
from app.models.estimate import Estimate, EstimateStatus
from app.models.project import Project
from app.models.work import Invoice, InvoiceStatus
from app.schemas.work import InvoiceOut, InvoicePlanBody, InvoiceUpdate
from app.services import deals

router = APIRouter(prefix="/api", tags=["billing"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def can_record(actor: Actor, company_id: UUID) -> bool:
    """Mark invoices as sent and paid."""
    return actor.can_manage_company(company_id) or (
        actor.is_accounting and actor.own_company(company_id)
    )


def default_due(invoiced_on: date) -> date:
    """End of the following month (月末締め翌月末払い)."""
    year, month = (
        (invoiced_on.year + 1, 1)
        if invoiced_on.month == 12
        else (
            invoiced_on.year,
            invoiced_on.month + 1,
        )
    )
    return date(year, month, calendar.monthrange(year, month)[1])


async def _outs(session: AsyncSession, actor: Actor, invoices: list[Invoice]) -> list[InvoiceOut]:
    project_ids = {i.project_id for i in invoices}
    estimate_ids = {i.estimate_id for i in invoices}
    projects = await deals.rows_by_id(session, Project, project_ids)
    estimates = await deals.rows_by_id(session, Estimate, estimate_ids)
    customer_ids = {p.customer_id for p in projects.values() if p.customer_id}
    customers = await deals.rows_by_id(session, Customer, customer_ids)
    counts: dict[UUID, int] = {}
    for eid in estimate_ids:
        counts[eid] = len(
            (await session.exec(select(Invoice.id).where(Invoice.estimate_id == eid))).all()
        )
    today = utcnow().date()
    out = []
    for i in invoices:
        p = projects[i.project_id]
        e = estimates[i.estimate_id]
        customer = customers.get(p.customer_id) if p.customer_id else None
        out.append(
            InvoiceOut(
                id=i.id,
                project_id=p.id,
                project_name=p.name,
                customer_name=customer.name if customer else None,
                company_id=p.company_id,
                estimate_id=e.id,
                estimate_title=e.title,
                billing=e.billing,
                seq=i.seq,
                count=counts.get(e.id, 1),
                label=i.label,
                planned_on=i.planned_on,
                amount=i.amount,
                status=i.status,
                invoiced_on=i.invoiced_on,
                due_on=i.due_on,
                paid_on=i.paid_on,
                overdue=i.status == InvoiceStatus.invoiced
                and i.due_on is not None
                and i.due_on < today,
                can_record=can_record(actor, p.company_id),
            )
        )
    return out


async def _money_project(project_id: UUID, actor: Actor, session: AsyncSession) -> Project:
    project = await accessible_project(project_id, actor, session)
    if not actor.sees_money:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available for partner users")
    return project


@router.get(
    "/projects/{project_id}/invoices",
    response_model=list[InvoiceOut],
    summary="プロジェクトの請求予定",
)
async def project_invoices(
    project_id: UUID, actor: CurrentActor, session: Session
) -> list[InvoiceOut]:
    await _money_project(project_id, actor, session)
    rows = list(
        (
            await session.exec(
                select(Invoice)
                .where(Invoice.project_id == project_id)
                .order_by(col(Invoice.planned_on), col(Invoice.seq))
            )
        ).all()
    )
    return await _outs(session, actor, rows)


@router.put(
    "/estimates/{estimate_id}/invoices",
    response_model=list[InvoiceOut],
    summary="見積から請求予定を作る",
)
async def plan_invoices(
    estimate_id: UUID, body: InvoicePlanBody, actor: CurrentActor, session: Session
) -> list[InvoiceOut]:
    """Replaces the estimate's planned invoices with ``items``. Invoices
    already sent or paid are kept and numbered first."""
    estimate = await session.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate not found")
    project = await _money_project(estimate.project_id, actor, session)
    if not actor.can_sell(project.company_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only sales and administrators can plan")
    if estimate.status != EstimateStatus.won:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only won estimates can be billed"
        )
    existing = list(
        (await session.exec(select(Invoice).where(Invoice.estimate_id == estimate_id))).all()
    )
    kept = sorted(
        (i for i in existing if i.status != InvoiceStatus.planned), key=lambda i: i.planned_on
    )
    for i in existing:
        if i.status == InvoiceStatus.planned:
            await session.delete(i)
    for n, i in enumerate(kept, start=1):
        i.seq = n
        session.add(i)
    for n, item in enumerate(sorted(body.items, key=lambda x: x.planned_on), start=len(kept) + 1):
        session.add(
            Invoice(
                project_id=project.id,
                estimate_id=estimate_id,
                seq=n,
                label=item.label.strip(),
                planned_on=item.planned_on,
                amount=item.amount,
            )
        )
    await session.commit()
    return await project_invoices(project.id, actor, session)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut, summary="請求予定の更新")
async def update_invoice(
    invoice_id: UUID, body: InvoiceUpdate, actor: CurrentActor, session: Session
) -> InvoiceOut:
    """Accounting and admins record 請求済 / 入金済 (or undo them). Sales and
    admins change the label, date and amount while it is still planned."""
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    project = await _money_project(invoice.project_id, actor, session)
    fields = body.model_dump(exclude_unset=True)

    plan_fields = {"label", "planned_on", "amount"} & fields.keys()
    if plan_fields:
        if not actor.can_sell(project.company_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
        if invoice.status != InvoiceStatus.planned:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Already invoiced: undo it before changing it"
            )
        if body.label is not None:
            invoice.label = body.label.strip()
        if body.planned_on is not None:
            invoice.planned_on = body.planned_on
        if body.amount is not None:
            invoice.amount = body.amount

    record_fields = {"status", "invoiced_on", "due_on", "paid_on"} & fields.keys()
    if record_fields:
        if not can_record(actor, project.company_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only accounting and administrators can record"
            )
        today = utcnow().date()
        new = body.status or InvoiceStatus(invoice.status)
        if new == InvoiceStatus.planned:
            invoice.invoiced_on = invoice.due_on = invoice.paid_on = None
        else:
            invoiced_on = fields.get("invoiced_on") or invoice.invoiced_on or today
            invoice.invoiced_on = invoiced_on
            invoice.due_on = fields.get("due_on") or invoice.due_on or default_due(invoiced_on)
            if new == InvoiceStatus.paid:
                invoice.paid_on = fields.get("paid_on") or invoice.paid_on or today
            else:
                invoice.paid_on = None
        invoice.status = new

    invoice.updated_at = utcnow()
    session.add(invoice)
    await session.commit()
    return (await _outs(session, actor, [invoice]))[0]


def _billing_clause(actor: Actor) -> ColumnElement[bool]:
    """Projects whose invoices the actor works with: admins' companies and
    accounting's own company."""
    if actor.is_group_admin:
        return true()
    own = actor.user.company_id
    if own is not None and (actor.is_company_admin or actor.is_accounting):
        return col(Project.company_id) == own
    return col(Project.id).is_(None)  # nothing


def _month_range(month: str) -> tuple[date, date]:
    try:
        year, mon = (int(x) for x in month.split("-"))
        start = date(year, mon, 1)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "month must be YYYY-MM")
    return start, date(year, mon, calendar.monthrange(year, mon)[1])


async def _query(
    actor: Actor,
    session: AsyncSession,
    month: str | None,
    status_: str | None,
    company_id: UUID | None,
) -> list[Invoice]:
    if not (actor.can_manage_org or actor.is_accounting):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accounting or administrators only")
    query = (
        select(Invoice)
        .join(Project, col(Project.id) == col(Invoice.project_id))
        .where(_billing_clause(actor))
    )
    today = utcnow().date()
    overdue = and_(
        col(Invoice.status) == InvoiceStatus.invoiced,
        col(Invoice.due_on).is_not(None),
        col(Invoice.due_on) < today,
    )
    if month:
        start, end = _month_range(month)
        # The month's planned invoices, plus anything paid in it and every
        # invoice still awaiting payment, so nothing unpaid drops off.
        query = query.where(
            or_(
                and_(col(Invoice.planned_on) >= start, col(Invoice.planned_on) <= end),
                and_(col(Invoice.paid_on) >= start, col(Invoice.paid_on) <= end),
                col(Invoice.status) == InvoiceStatus.invoiced,
            )
        )
    if status_ == "overdue":
        query = query.where(overdue)
    elif status_:
        if status_ not in InvoiceStatus.__members__:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown status")
        query = query.where(Invoice.status == status_)
    if company_id is not None:
        query = query.where(Project.company_id == company_id)
    query = query.order_by(col(Invoice.planned_on).desc(), col(Project.name), col(Invoice.seq))
    return list((await session.exec(query)).all())


@router.get("/invoices", response_model=list[InvoiceOut], summary="請求一覧（経理）")
async def list_invoices(
    actor: CurrentActor,
    session: Session,
    month: Annotated[str | None, Query(description="YYYY-MM")] = None,
    status_: Annotated[
        str | None, Query(alias="status", description="planned / invoiced / paid / overdue")
    ] = None,
    company_id: Annotated[UUID | None, Query()] = None,
) -> list[InvoiceOut]:
    return await _outs(session, actor, await _query(actor, session, month, status_, company_id))


CSV_COLUMNS = (
    "planned_on",
    "project",
    "customer",
    "estimate",
    "label",
    "amount",
    "status",
    "invoiced_on",
    "due_on",
    "paid_on",
)


@router.get("/invoices.csv", summary="請求一覧の CSV")
async def export_invoices(
    request: Request,
    actor: CurrentActor,
    session: Session,
    month: Annotated[str | None, Query(description="YYYY-MM")] = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    company_id: Annotated[UUID | None, Query()] = None,
) -> Response:
    locale = request_locale(request)
    rows = await _outs(session, actor, await _query(actor, session, month, status_, company_id))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([t(locale, f"invoice.col.{c}") for c in CSV_COLUMNS])
    for r in rows:
        writer.writerow(
            [
                r.planned_on,
                r.project_name,
                r.customer_name or "",
                r.estimate_title,
                r.label,
                r.amount,
                t(locale, f"invoice.status.{'overdue' if r.overdue else r.status}"),
                r.invoiced_on or "",
                r.due_on or "",
                r.paid_on or "",
            ]
        )
    name = f"vectana-invoices-{month or 'all'}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),  # BOM so Excel reads UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
