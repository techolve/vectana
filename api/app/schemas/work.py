from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.work import ActivityKind, InvoiceStatus
from app.schemas.org import UserBrief

# --- Timesheet ---------------------------------------------------------------


class TimesheetRowIn(BaseModel):
    """One row of the weekly sheet: a task, a project without a task, or a
    free label for work outside projects."""

    project_id: UUID | None = None
    task_id: UUID | None = None
    label: str | None = Field(default=None, max_length=200)
    # Monday..Sunday; None or 0 = nothing that day.
    hours: list[float | None] = Field(min_length=7, max_length=7)

    @field_validator("hours")
    @classmethod
    def _range(cls, v: list[float | None]) -> list[float | None]:
        for h in v:
            if h is not None and not 0 <= h <= 24:
                raise ValueError("hours must be between 0 and 24")
        return v


class TimesheetBody(BaseModel):
    week_start: date  # any day of the week; normalized to Monday
    user_id: UUID | None = None  # defaults to the caller
    rows: list[TimesheetRowIn] = Field(max_length=200)


class TimesheetRow(BaseModel):
    project_id: UUID | None
    project_name: str | None
    task_id: UUID | None
    task_number: int | None
    task_title: str | None
    task_kind: str | None
    label: str | None
    hours: list[float | None]
    # Of the task across everyone: estimate and total actual hours so far.
    estimate_hours: float | None
    actual_hours: float | None


class TimesheetOut(BaseModel):
    user: UserBrief
    week_start: date
    days: list[date]
    rows: list[TimesheetRow]
    standard_hours: float  # 所定（40h）
    submitted_at: datetime | None
    can_edit: bool


# --- Estimate vs actual --------------------------------------------------------


class PhaseActual(BaseModel):
    task_id: UUID | None  # None = time not under any phase
    title: str | None
    estimate_days: float | None  # sum of the phase's task estimates (hours / 8)
    actual_days: float


class PersonActual(BaseModel):
    user: UserBrief
    actual_days: float


class ActualsOut(BaseModel):
    project_id: UUID
    # Won one-time estimates (initial and additional).
    estimate_days: float | None
    estimate_amount: int | None
    actual_hours: float
    actual_days: float
    this_month_days: float
    # Hours x the person's unit cost; only for those who see unit costs.
    actual_cost: int | None
    phases: list[PhaseActual]
    people: list[PersonActual]


# --- Activities ----------------------------------------------------------------


class ActivityBody(BaseModel):
    kind: ActivityKind = ActivityKind.meeting
    occurred_on: date
    participants: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1)
    next_action: str | None = Field(default=None, max_length=200)
    next_action_assignee_id: UUID | None = None
    next_action_due: date | None = None


class ActivityUpdate(BaseModel):
    kind: ActivityKind | None = None
    occurred_on: date | None = None
    participants: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, min_length=1)


class ActivityTask(BaseModel):
    id: UUID
    title: str
    status: str
    assignee: UserBrief | None
    due_date: date | None
    overdue: bool


class ActivityOut(BaseModel):
    id: UUID
    project_id: UUID
    kind: str
    occurred_on: date
    participants: str | None
    body: str
    next_action: str | None
    task: ActivityTask | None
    created_by: UserBrief | None
    created_at: datetime


# --- Invoices --------------------------------------------------------------------


class InvoicePlanItem(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    planned_on: date
    amount: int = Field(ge=0)


class InvoicePlanBody(BaseModel):
    """Replaces the estimate's invoices that are still planned. Invoiced and
    paid ones stay as they are."""

    items: list[InvoicePlanItem] = Field(max_length=120)


class InvoiceUpdate(BaseModel):
    status: InvoiceStatus | None = None
    invoiced_on: date | None = None
    due_on: date | None = None
    paid_on: date | None = None
    # While planned (sales):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    planned_on: date | None = None
    amount: int | None = Field(default=None, ge=0)


class InvoiceOut(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    customer_name: str | None
    company_id: UUID
    estimate_id: UUID
    estimate_title: str
    billing: str  # one_time | monthly
    seq: int
    count: int  # installments of the estimate
    label: str
    planned_on: date
    amount: int
    status: str
    invoiced_on: date | None
    due_on: date | None
    paid_on: date | None
    overdue: bool  # invoiced and past its due date (入金遅れ)
    can_record: bool  # caller may mark it invoiced / paid
