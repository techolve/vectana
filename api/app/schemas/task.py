from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.task import SprintStatus, TaskKind, TaskPriority, TaskStatus
from app.schemas.org import UserBrief
from app.schemas.project import UpgradeOut


class TaskBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: TaskKind = TaskKind.development
    description: str | None = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority | None = None
    assignee_id: UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    parent_id: UUID | None = None
    is_milestone: bool = False
    progress: int = Field(default=0, ge=0, le=100)
    depends_on: list[UUID] = []
    sprint_id: UUID | None = None
    points: float | None = Field(default=None, ge=0)
    estimate_hours: float | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: TaskKind | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    parent_id: UUID | None = None
    is_milestone: bool | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    depends_on: list[UUID] | None = None
    sprint_id: UUID | None = None
    points: float | None = Field(default=None, ge=0)
    position: float | None = None
    estimate_hours: float | None = Field(default=None, ge=0)


class SecurityOut(BaseModel):
    """What a security task upgrades and why."""

    subject: str  # package | runtime
    ecosystem: str
    name: str
    label: str  # how the package / runtime is called (the task's initial title)
    installed: list[str]  # versions in use
    vuln_count: int  # unresolved linked vulnerabilities
    max_severity: str | None
    eol_status: str | None  # eol | approaching
    eol_date: date | None
    latest: str | None
    upgrade: UpgradeOut | None  # recommended version (vulnerabilities)


class TaskOut(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    number: int
    kind: str
    title: str
    description: str | None
    status: str
    priority: str | None
    assignee: UserBrief | None
    start_date: date | None
    due_date: date | None  # set on the task
    # The task's due date, else (security) its earliest vulnerability's.
    effective_due: date | None
    overdue: bool
    parent_id: UUID | None
    is_milestone: bool
    progress: int
    depends_on: list[UUID]
    sprint_id: UUID | None
    points: float | None
    position: float
    estimate_hours: float | None
    auto_created: bool
    # The linked GitHub / GitLab issue.
    issue_number: int | None
    issue_url: str | None
    security: SecurityOut | None = None
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None


class LinkedMatch(BaseModel):
    id: UUID
    vuln_id: str
    summary: str | None
    severity: str
    package_version: str
    fixed_version: str | None
    status: str


class LinkedFinding(BaseModel):
    id: UUID
    product_label: str
    version: str
    cycle: str | None
    eol_date: date | None
    status: str


class TaskDetail(TaskOut):
    matches: list[LinkedMatch] = []
    findings: list[LinkedFinding] = []


class CandidateOut(BaseModel):
    """Vulnerabilities / EOL of one package that have no task yet."""

    subject: str
    ecosystem: str
    name: str
    label: str
    installed: list[str]
    vuln_count: int
    max_severity: str | None
    eol_status: str | None
    upgrade: UpgradeOut | None


class SecurityTaskBody(BaseModel):
    subject: str
    ecosystem: str
    name: str


class DoneItem(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    done: bool = False


class SprintBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    goal: str | None = None
    starts_on: date
    ends_on: date
    status: SprintStatus = SprintStatus.planned
    definition_of_done: list[DoneItem] = []


class SprintUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    goal: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    status: SprintStatus | None = None
    definition_of_done: list[DoneItem] | None = None


class SprintOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    goal: str | None
    starts_on: date
    ends_on: date
    status: str
    definition_of_done: list[DoneItem]
    task_count: int
    done_count: int
    points: float  # committed (all tasks in the sprint)
    done_points: float


class BurndownPoint(BaseModel):
    date: date
    ideal: float
    remaining: float | None  # None for days still ahead


class BurndownOut(BaseModel):
    sprint_id: UUID
    unit: str  # points | tasks (when nothing is estimated)
    total: float
    points: list[BurndownPoint]


class VelocityOut(BaseModel):
    sprint_id: UUID
    name: str
    status: str
    committed: float
    completed: float
