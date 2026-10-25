from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field, utcnow


class Runtime(SQLModel, table=True):
    """Something a project runs on that lockfiles don't reveal (Python, Node.js,
    PostgreSQL, Ubuntu…). ``product`` is an endoflife.date product id."""

    __tablename__ = "runtimes"
    __table_args__ = (UniqueConstraint("project_id", "product", "version"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    product: str = Field(max_length=100)
    version: str = Field(max_length=100)
    created_at: datetime = created_at_field()


class EolStatus(StrEnum):
    supported = "supported"
    approaching = "approaching"  # EOL within the configured warning window
    eol = "eol"
    unknown = "unknown"  # product known, but no release cycle matches the version


EOL_STAGE_RANK = {EolStatus.approaching: 1, EolStatus.eol: 2}


class EolFinding(SQLModel, table=True):
    """EOL state of one package or runtime, recomputed on every scan."""

    __tablename__ = "eol_findings"
    __table_args__ = (
        UniqueConstraint("package_id", "product"),
        UniqueConstraint("runtime_id", "product"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    package_id: UUID | None = Field(
        default=None, foreign_key="packages.id", index=True, ondelete="CASCADE"
    )
    runtime_id: UUID | None = Field(
        default=None, foreign_key="runtimes.id", index=True, ondelete="CASCADE"
    )
    product: str = Field(max_length=100)
    product_label: str = Field(max_length=200)
    version: str = Field(max_length=100)
    cycle: str | None = Field(default=None, max_length=50)
    eol_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    latest: str | None = Field(default=None, max_length=100)
    status: str = Field(default=EolStatus.unknown, max_length=20)
    status_changed_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    checked_at: datetime | None = nullable_ts_field()


class EolDelivery(SQLModel, table=True):
    """One EOL stage (approaching / eol) delivered to one target."""

    __tablename__ = "eol_deliveries"
    __table_args__ = (UniqueConstraint("finding_id", "stage", "channel", "target"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    finding_id: UUID = Field(foreign_key="eol_findings.id", index=True, ondelete="CASCADE")
    stage: str = Field(max_length=20)
    channel: str = Field(max_length=20)
    target: str = Field(max_length=1000)
    sent_at: datetime = created_at_field()


class AppSettings(SQLModel, table=True):
    """Instance-wide settings editable by group admins (single row, id=1)."""

    __tablename__ = "app_settings"

    id: int = Field(default=1, primary_key=True)
    eol_warning_days: int = Field(default=90)
