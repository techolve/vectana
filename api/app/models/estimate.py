from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field


class EstimateKind(StrEnum):
    initial = "initial"  # 初回開発
    additional = "additional"  # 追加開発
    maintenance = "maintenance"  # 保守（新規・更新）
    other = "other"


class EstimateStatus(StrEnum):
    draft = "draft"  # 作成中
    submitted = "submitted"  # 提出済み
    won = "won"  # 受注
    lost = "lost"  # 失注


OPEN_ESTIMATE_STATUSES = frozenset({EstimateStatus.draft, EstimateStatus.submitted})


class Billing(StrEnum):
    one_time = "one_time"
    monthly = "monthly"  # amount is per month (保守)


class Estimate(SQLModel, table=True):
    """One estimate of a project. A project collects several over its life:
    the first build, additional work, maintenance renewals. Each is won or
    lost on its own."""

    __tablename__ = "estimates"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    title: str = Field(max_length=200)
    kind: str = Field(default=EstimateKind.initial, max_length=20)
    status: str = Field(default=EstimateStatus.draft, max_length=20)
    billing: str = Field(default=Billing.one_time, max_length=20)
    amount: int | None = Field(default=None)  # yen, tax excluded
    # Used when the estimate has no lines; otherwise the lines' sum wins.
    effort_days: float | None = Field(default=None)
    issued_on: date | None = Field(default=None)  # 見積日
    due_on: date | None = Field(default=None)  # 提出期限
    valid_until: date | None = Field(default=None)  # 契約期間の終わり（保守）
    decided_on: date | None = Field(default=None)  # 受注・失注日
    lost_reason: str | None = Field(default=None)
    competitor: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None)
    created_by: UUID | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
    updated_at: datetime | None = nullable_ts_field()


class EstimateLine(SQLModel, table=True):
    """Effort of one person or role. ``unit_cost`` is copied from the user
    when the line is saved, so later rate changes do not rewrite history."""

    __tablename__ = "estimate_lines"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    estimate_id: UUID = Field(foreign_key="estimates.id", index=True, ondelete="CASCADE")
    position: int = Field(default=0)
    label: str = Field(max_length=200)
    user_id: UUID | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    days: float = Field(default=0)
    unit_cost: int | None = Field(default=None)  # yen per person-day
