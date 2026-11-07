from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Date, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field


class TaskKind(StrEnum):
    development = "development"  # 開発
    security = "security"  # セキュリティ対応 (vulnerabilities and EOL together)
    other = "other"  # その他


class TaskStatus(StrEnum):
    todo = "todo"  # 未着手
    in_progress = "in_progress"  # 対応中
    done = "done"  # 完了


class TaskPriority(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class SecuritySubject(StrEnum):
    package = "package"  # upgrade a dependency
    runtime = "runtime"  # upgrade a runtime / product (EOL)


class Task(SQLModel, table=True):
    """One unit of work. The same row shows on the dashboard, the Gantt chart,
    the sprint board and the maintenance list.

    A security task is one upgrade of one package (or runtime): every
    unresolved vulnerability and EOL finding of that package links to it via
    ``VulnMatch.task_id`` / ``EolFinding.task_id``.
    """

    __tablename__ = "tasks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    # Per-project sequence shown as #12.
    number: int = Field(default=0)
    kind: str = Field(default=TaskKind.development, max_length=20, index=True)
    title: str = Field(max_length=300)
    description: str | None = Field(default=None)
    status: str = Field(default=TaskStatus.todo, max_length=20, index=True)
    priority: str | None = Field(default=None, max_length=10)  # TaskPriority
    assignee_id: UUID | None = Field(
        default=None, foreign_key="users.id", index=True, ondelete="SET NULL"
    )
    start_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    due_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    # Gantt: a phase groups child tasks; a milestone is a single day.
    parent_id: UUID | None = Field(
        default=None, foreign_key="tasks.id", index=True, ondelete="SET NULL"
    )
    is_milestone: bool = Field(default=False)
    progress: int = Field(default=0)  # 0-100, for the Gantt bar
    depends_on: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # Scrum.
    sprint_id: UUID | None = Field(
        default=None, foreign_key="sprints.id", index=True, ondelete="SET NULL"
    )
    points: float | None = Field(default=None)
    position: float = Field(default=0)  # order inside a list or board column
    estimate_hours: float | None = Field(default=None)
    # Security tasks.
    subject: str | None = Field(default=None, max_length=20)  # SecuritySubject
    subject_ecosystem: str | None = Field(default=None, max_length=30)
    subject_name: str | None = Field(default=None, max_length=300)
    auto_created: bool = Field(default=False)
    # The GitHub issue / GitLab issue this task is kept in step with.
    repo_link_id: UUID | None = Field(
        default=None, foreign_key="repo_links.id", index=True, ondelete="SET NULL"
    )
    issue_number: int | None = Field(default=None)
    issue_url: str | None = Field(default=None, max_length=500)
    created_by: UUID | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_at: datetime = created_at_field()
    updated_at: datetime | None = nullable_ts_field()
    completed_at: datetime | None = nullable_ts_field()


class SprintStatus(StrEnum):
    planned = "planned"
    active = "active"
    closed = "closed"


class Sprint(SQLModel, table=True):
    __tablename__ = "sprints"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=100)
    goal: str | None = Field(default=None)
    # Definition of done: [{"text": "...", "done": false}].
    definition_of_done: list[Any] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    starts_on: date = Field(sa_column=Column(Date, nullable=False))
    ends_on: date = Field(sa_column=Column(Date, nullable=False))
    status: str = Field(default=SprintStatus.planned, max_length=20)
    # Points planned for the sprint, frozen when it closes (unfinished tasks
    # then go back to the backlog).
    committed_points: float | None = Field(default=None)
    # The milestone this sprint is kept in step with.
    repo_link_id: UUID | None = Field(
        default=None, foreign_key="repo_links.id", index=True, ondelete="SET NULL"
    )
    milestone_number: int | None = Field(default=None)
    created_at: datetime = created_at_field()
