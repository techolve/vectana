"""Phase 3: time entries (実績工数), deal activity log (商談メモ) and the
billing schedule (請求予定)."""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, Date
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field

# A person-day (人日) is 8 hours.
HOURS_PER_DAY = 8


class TimeEntry(SQLModel, table=True):
    """Hours one person spent on one day. A row of the weekly sheet is
    (project, task) or, for work outside projects, a free label."""

    __tablename__ = "time_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    work_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    project_id: UUID | None = Field(
        default=None, foreign_key="projects.id", index=True, ondelete="CASCADE"
    )
    task_id: UUID | None = Field(
        default=None, foreign_key="tasks.id", index=True, ondelete="SET NULL"
    )
    label: str | None = Field(default=None, max_length=200)  # outside projects
    hours: float
    # Row order inside the week, so the sheet comes back as it was typed.
    position: int = Field(default=0)
    created_at: datetime = created_at_field()


class TimesheetWeek(SQLModel, table=True):
    """A submitted week (週を提出). Absent = not submitted."""

    __tablename__ = "timesheet_weeks"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True, ondelete="CASCADE")
    week_start: date = Field(sa_column=Column(Date, primary_key=True))
    submitted_at: datetime = created_at_field()


class ActivityKind(StrEnum):
    meeting = "meeting"  # 打合せ
    phone = "phone"  # 電話
    email = "email"  # メール


class Activity(SQLModel, table=True):
    """One entry of a project's deal log. Its next action becomes a task."""

    __tablename__ = "activities"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    kind: str = Field(default=ActivityKind.meeting, max_length=20)
    occurred_on: date = Field(sa_column=Column(Date, nullable=False))
    participants: str | None = Field(default=None, max_length=300)
    body: str
    next_action: str | None = Field(default=None, max_length=200)
    task_id: UUID | None = Field(default=None, foreign_key="tasks.id", ondelete="SET NULL")
    created_by: UUID | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
    updated_at: datetime | None = nullable_ts_field()


class InvoiceStatus(StrEnum):
    planned = "planned"  # 予定
    invoiced = "invoiced"  # 請求済・入金待ち
    paid = "paid"  # 入金済


class Invoice(SQLModel, table=True):
    """One planned invoice of a won estimate: an installment of a one-time
    estimate or a month of maintenance. The invoice itself is issued in the
    accounting software; accounting records here that it was sent and paid."""

    __tablename__ = "invoices"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    estimate_id: UUID = Field(foreign_key="estimates.id", index=True, ondelete="CASCADE")
    seq: int = Field(default=1)  # 1-based within the estimate
    label: str = Field(max_length=200)  # 着手金（30%）, 11 月分
    planned_on: date = Field(sa_column=Column(Date, nullable=False, index=True))
    amount: int  # yen, tax excluded
    status: str = Field(default=InvoiceStatus.planned, max_length=20, index=True)
    invoiced_on: date | None = Field(default=None)
    due_on: date | None = Field(default=None)  # 入金予定
    paid_on: date | None = Field(default=None)
    created_at: datetime = created_at_field()
    updated_at: datetime | None = nullable_ts_field()
