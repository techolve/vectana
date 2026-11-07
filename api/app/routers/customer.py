"""Customers (取引先) and their contacts.

Sales and company admins manage their own company's customers; group admins
manage every company's. Accounting sees its own company's, PMO sees all.
Partner (BP) users never see customers.
"""

from collections import defaultdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, true
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, get_actor, visible_projects_clause
from app.core.database import get_session
from app.models.customer import Customer, CustomerContact
from app.models.organization import Company, CompanyType
from app.models.project import ARCHIVED_STATUSES, Project
from app.schemas.sales import (
    ContactBody,
    ContactOut,
    CustomerBody,
    CustomerDetail,
    CustomerOut,
    CustomerUpdate,
)
from app.services import deals

router = APIRouter(prefix="/api", tags=["customers"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def _visible_customers(actor: Actor) -> ColumnElement[bool]:
    if actor.is_group_admin or actor.is_pmo:
        return true()
    own = actor.user.company_id
    if own is not None and (actor.is_company_admin or actor.is_sales or actor.is_accounting):
        return col(Customer.company_id) == own
    return col(Customer.id).is_(None)


def _require_customer_access(actor: Actor) -> None:
    if actor.is_partner or not (
        actor.is_group_admin
        or actor.is_pmo
        or actor.is_company_admin
        or actor.is_sales
        or actor.is_accounting
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to view customers")


async def _get_customer(customer_id: UUID, actor: Actor, session: AsyncSession) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None or not actor.can_see_customers(customer.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


async def _rows(
    session: AsyncSession, actor: Actor, customers: list[Customer]
) -> list[CustomerOut]:
    ids = [c.id for c in customers]
    users = await deals.users_by_id(session, {c.sales_owner_id for c in customers})
    primary: dict[UUID, str] = {}
    projects_by_customer: dict[UUID, list[Project]] = defaultdict(list)
    if ids:
        for contact in (
            await session.exec(
                select(CustomerContact)
                .where(col(CustomerContact.customer_id).in_(ids))
                .order_by(col(CustomerContact.is_primary).desc(), col(CustomerContact.created_at))
            )
        ).all():
            primary.setdefault(contact.customer_id, contact.name)
        for p in (
            await session.exec(
                select(Project).where(
                    col(Project.customer_id).in_(ids), visible_projects_clause(actor)
                )
            )
        ).all():
            assert p.customer_id is not None
            projects_by_customer[p.customer_id].append(p)
    all_projects = [p for ps in projects_by_customer.values() for p in ps]
    totals = await deals.estimate_totals(session, [p.id for p in all_projects])
    out = []
    for c in customers:
        projects = projects_by_customer.get(c.id, [])
        live = [p for p in projects if p.status not in ARCHIVED_STATUSES]
        out.append(
            CustomerOut(
                id=c.id,
                company_id=c.company_id,
                name=c.name,
                industry=c.industry,
                address=c.address,
                phone=c.phone,
                website=c.website,
                payment_terms=c.payment_terms,
                billing_contact=c.billing_contact,
                notes=c.notes,
                sales_owner=deals.brief(users.get(c.sales_owner_id) if c.sales_owner_id else None),
                created_at=c.created_at,
                primary_contact=primary.get(c.id),
                project_count=len(projects),
                pipeline_amount=sum(
                    totals[p.id].open_amount + totals[p.id].won_amount for p in live
                ),
                can_edit=actor.can_sell(c.company_id),
            )
        )
    return out


def _contact_out(c: CustomerContact) -> ContactOut:
    return ContactOut(
        id=c.id, name=c.name, title=c.title, email=c.email, phone=c.phone, is_primary=c.is_primary
    )


@router.get("/customers", response_model=list[CustomerOut], summary="顧客一覧")
async def list_customers(
    actor: CurrentActor,
    session: Session,
    company_id: Annotated[UUID | None, Query()] = None,
    q: Annotated[str, Query(max_length=100)] = "",
) -> list[CustomerOut]:
    _require_customer_access(actor)
    query = select(Customer).where(_visible_customers(actor)).order_by(Customer.name)
    if company_id is not None:
        query = query.where(Customer.company_id == company_id)
    if q:
        query = query.where(col(Customer.name).ilike(f"%{q}%"))
    return await _rows(session, actor, list((await session.exec(query)).all()))


@router.post(
    "/customers",
    response_model=CustomerDetail,
    status_code=status.HTTP_201_CREATED,
    summary="顧客の作成",
)
async def create_customer(
    body: CustomerBody, actor: CurrentActor, session: Session
) -> CustomerDetail:
    company_id = body.company_id or actor.user.company_id
    if company_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "company_id is required")
    company = await session.get(Company, company_id)
    if company is None or company.type == CompanyType.partner:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Customers belong to a group company"
        )
    if not actor.can_sell(company_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for this company")
    await deals.check_user(session, body.sales_owner_id)
    customer = Customer(
        **body.model_dump(exclude={"company_id", "name"}),
        company_id=company_id,
        name=body.name.strip(),
    )
    session.add(customer)
    await session.commit()
    return await get_customer(customer.id, actor, session)


@router.get("/customers/{customer_id}", response_model=CustomerDetail, summary="顧客詳細")
async def get_customer(customer_id: UUID, actor: CurrentActor, session: Session) -> CustomerDetail:
    customer = await _get_customer(customer_id, actor, session)
    row = (await _rows(session, actor, [customer]))[0]
    contacts = (
        await session.exec(
            select(CustomerContact)
            .where(CustomerContact.customer_id == customer.id)
            .order_by(col(CustomerContact.is_primary).desc(), col(CustomerContact.created_at))
        )
    ).all()
    return CustomerDetail(**row.model_dump(), contacts=[_contact_out(c) for c in contacts])


async def _editable(customer_id: UUID, actor: Actor, session: AsyncSession) -> Customer:
    customer = await _get_customer(customer_id, actor, session)
    if not actor.can_sell(customer.company_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
    return customer


@router.patch("/customers/{customer_id}", response_model=CustomerDetail, summary="顧客の更新")
async def update_customer(
    customer_id: UUID, body: CustomerUpdate, actor: CurrentActor, session: Session
) -> CustomerDetail:
    customer = await _editable(customer_id, actor, session)
    fields = body.model_dump(exclude_unset=True)
    if "sales_owner_id" in fields:
        await deals.check_user(session, body.sales_owner_id)
    if fields.get("name") is None:
        fields.pop("name", None)
    for key, value in fields.items():
        setattr(customer, key, value.strip() if key == "name" else value)
    session.add(customer)
    await session.commit()
    return await get_customer(customer.id, actor, session)


@router.delete(
    "/customers/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="顧客の削除",
)
async def delete_customer(customer_id: UUID, actor: CurrentActor, session: Session) -> None:
    """Refused while projects point at the customer, so deal history stays."""
    customer = await _editable(customer_id, actor, session)
    used = (
        await session.exec(select(Project.id).where(Project.customer_id == customer.id))
    ).first()
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "Customer still has projects")
    await session.delete(customer)
    await session.commit()


# --- Contacts ----------------------------------------------------------------


async def _unset_other_primary(session: AsyncSession, customer_id: UUID, keep: UUID) -> None:
    for other in (
        await session.exec(
            select(CustomerContact).where(
                CustomerContact.customer_id == customer_id,
                col(CustomerContact.is_primary).is_(True),
                CustomerContact.id != keep,
            )
        )
    ).all():
        other.is_primary = False
        session.add(other)


@router.post(
    "/customers/{customer_id}/contacts",
    response_model=ContactOut,
    status_code=status.HTTP_201_CREATED,
    summary="担当者の追加",
)
async def add_contact(
    customer_id: UUID, body: ContactBody, actor: CurrentActor, session: Session
) -> ContactOut:
    customer = await _editable(customer_id, actor, session)
    contact = CustomerContact(customer_id=customer.id, **body.model_dump())
    session.add(contact)
    await session.flush()
    if contact.is_primary:
        await _unset_other_primary(session, customer.id, contact.id)
    await session.commit()
    return _contact_out(contact)


async def _get_contact(
    customer_id: UUID, contact_id: UUID, session: AsyncSession
) -> CustomerContact:
    contact = await session.get(CustomerContact, contact_id)
    if contact is None or contact.customer_id != customer_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    return contact


@router.put(
    "/customers/{customer_id}/contacts/{contact_id}",
    response_model=ContactOut,
    summary="担当者の更新",
)
async def update_contact(
    customer_id: UUID,
    contact_id: UUID,
    body: ContactBody,
    actor: CurrentActor,
    session: Session,
) -> ContactOut:
    await _editable(customer_id, actor, session)
    contact = await _get_contact(customer_id, contact_id, session)
    for key, value in body.model_dump().items():
        setattr(contact, key, value)
    session.add(contact)
    if contact.is_primary:
        await _unset_other_primary(session, customer_id, contact.id)
    await session.commit()
    return _contact_out(contact)


@router.delete(
    "/customers/{customer_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="担当者の削除",
)
async def delete_contact(
    customer_id: UUID, contact_id: UUID, actor: CurrentActor, session: Session
) -> None:
    await _editable(customer_id, actor, session)
    contact = await _get_contact(customer_id, contact_id, session)
    await session.delete(contact)
    await session.commit()


__all__ = ["router"]
