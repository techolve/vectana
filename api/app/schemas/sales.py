"""Customers and estimates."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.estimate import Billing, EstimateKind, EstimateStatus
from app.schemas.org import UserBrief


class CustomerBrief(BaseModel):
    id: UUID
    name: str


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool = False


class ContactOut(ContactBody):
    id: UUID


class CustomerBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company_id: UUID | None = None  # defaults to the caller's company
    industry: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=300)
    payment_terms: str | None = Field(default=None, max_length=200)
    billing_contact: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    sales_owner_id: UUID | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=300)
    payment_terms: str | None = Field(default=None, max_length=200)
    billing_contact: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    sales_owner_id: UUID | None = None


class CustomerOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    industry: str | None
    address: str | None
    phone: str | None
    website: str | None
    payment_terms: str | None
    billing_contact: str | None
    notes: str | None
    sales_owner: UserBrief | None
    created_at: datetime
    primary_contact: str | None = None
    project_count: int = 0
    # Open and won one-time estimates of deals and running projects.
    pipeline_amount: int = 0
    can_edit: bool = False


class CustomerDetail(CustomerOut):
    contacts: list[ContactOut] = []


class EstimateLineIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    user_id: UUID | None = None
    days: float = Field(ge=0)
    # Defaults to the user's current unit cost.
    unit_cost: int | None = Field(default=None, ge=0)


class EstimateLineOut(BaseModel):
    id: UUID
    label: str
    user: UserBrief | None
    days: float
    # None unless the caller may see per-person costs.
    unit_cost: int | None
    cost: int | None


class EstimateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: EstimateKind = EstimateKind.initial
    status: EstimateStatus = EstimateStatus.draft
    billing: Billing = Billing.one_time
    amount: int | None = Field(default=None, ge=0)
    effort_days: float | None = Field(default=None, ge=0)
    issued_on: date | None = None
    due_on: date | None = None
    valid_until: date | None = None
    decided_on: date | None = None
    lost_reason: str | None = None
    competitor: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    lines: list[EstimateLineIn] = []


class EstimateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: EstimateKind | None = None
    status: EstimateStatus | None = None
    billing: Billing | None = None
    amount: int | None = Field(default=None, ge=0)
    effort_days: float | None = Field(default=None, ge=0)
    issued_on: date | None = None
    due_on: date | None = None
    valid_until: date | None = None
    decided_on: date | None = None
    lost_reason: str | None = None
    competitor: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    lines: list[EstimateLineIn] | None = None


class EstimateOut(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    kind: str
    status: str
    billing: str
    amount: int | None
    effort_days: float | None  # lines' total when there are lines
    # Margin is shown to every proper member; total cost only with unit costs.
    margin: float | None  # 0.32 = 32 %
    cost: int | None
    issued_on: date | None
    due_on: date | None
    valid_until: date | None
    decided_on: date | None
    lost_reason: str | None
    competitor: str | None
    notes: str | None
    lines: list[EstimateLineOut]
    created_at: datetime
    updated_at: datetime | None
