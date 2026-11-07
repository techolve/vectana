from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field


class ProjectRole(StrEnum):
    owner = "owner"  # manage settings, members, webhooks
    member = "member"  # edit packages, triage vulnerabilities
    viewer = "viewer"  # read only


class ProjectStatus(StrEnum):
    inquiry = "inquiry"  # 引き合い
    proposal = "proposal"  # 提案・見積
    negotiation = "negotiation"  # 商談中
    won = "won"  # 受注
    development = "development"  # 開発中
    maintenance = "maintenance"  # 運用・保守
    on_hold = "on_hold"  # 保留
    lost = "lost"  # 失注


# Statuses that mean the work has been ordered (or, for an internal project,
# started). Entering one sets ``ordered_on``.
DELIVERY_STATUSES = frozenset(
    {ProjectStatus.won, ProjectStatus.development, ProjectStatus.maintenance}
)
# Kept out of the normal lists (the 終了 tab).
ARCHIVED_STATUSES = frozenset({ProjectStatus.on_hold, ProjectStatus.lost})


class ProjectMethod(StrEnum):
    waterfall = "waterfall"  # Gantt
    scrum = "scrum"  # sprint board


class Project(SQLModel, table=True):
    """One project from the first inquiry through delivery and maintenance.

    Until ``ordered_on`` is set the project is a deal (営業中): only sales,
    admins and its members can see it.
    """

    __tablename__ = "projects"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True, ondelete="RESTRICT")
    department_id: UUID | None = Field(
        default=None, foreign_key="departments.id", index=True, ondelete="SET NULL"
    )
    name: str = Field(max_length=200)
    description: str | None = Field(default=None)
    customer_id: UUID | None = Field(
        default=None, foreign_key="customers.id", index=True, ondelete="SET NULL"
    )
    status: str = Field(default=ProjectStatus.development, max_length=20, index=True)
    method: str = Field(default=ProjectMethod.waterfall, max_length=20)
    # 受注日. For an internal project that skipped sales, the day it started.
    ordered_on: date | None = Field(default=None)
    starts_on: date | None = Field(default=None)
    ends_on: date | None = Field(default=None)
    sales_owner_id: UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="SET NULL"
    )
    manager_id: UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="SET NULL"
    )
    # Deal fields: rough amount before any estimate, win probability (%).
    expected_amount: int | None = Field(default=None)
    probability: int | None = Field(default=None)
    next_action: str | None = Field(default=None, max_length=200)
    next_action_on: date | None = Field(default=None)
    # Kept for later analysis when the deal is lost.
    lost_reason: str | None = Field(default=None)
    competitor: str | None = Field(default=None, max_length=200)
    # Vulnerabilities at or above this severity (and reached EOL) become
    # security tasks automatically; below it, someone presses タスク化.
    security_threshold: str = Field(default="HIGH", max_length=20)
    created_at: datetime = created_at_field()

    @property
    def is_deal(self) -> bool:
        return self.ordered_on is None


class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    role: str = Field(default=ProjectRole.member, max_length=20)
    created_at: datetime = created_at_field()


class WebhookType(StrEnum):
    discord = "discord"
    slack = "slack"


class ProjectWebhook(SQLModel, table=True):
    __tablename__ = "project_webhooks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    type: str = Field(max_length=20)
    url: str = Field(max_length=1000)
    min_severity: str = Field(default="LOW", max_length=20)
    locale: str = Field(default="ja", max_length=5)
    enabled: bool = Field(default=True)
    created_at: datetime = created_at_field()
