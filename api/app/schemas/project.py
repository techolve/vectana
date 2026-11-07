from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.package import ECOSYSTEMS, MatchStatus, Severity
from app.models.project import ProjectMethod, ProjectRole, ProjectStatus, WebhookType
from app.schemas.eol import EolFindingOut
from app.schemas.org import UserBrief
from app.schemas.sales import CustomerBrief


class ProjectBody(BaseModel):
    name: str
    description: str | None = None
    company_id: UUID | None = None  # defaults to the caller's company
    department_id: UUID | None = None
    # Internal projects start at development or maintenance; deals at inquiry.
    status: ProjectStatus = ProjectStatus.development
    method: ProjectMethod = ProjectMethod.waterfall
    customer_id: UUID | None = None
    sales_owner_id: UUID | None = None
    manager_id: UUID | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    expected_amount: int | None = Field(default=None, ge=0)
    probability: int | None = Field(default=None, ge=0, le=100)
    next_action: str | None = Field(default=None, max_length=200)
    next_action_on: date | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    department_id: UUID | None = None
    status: ProjectStatus | None = None
    method: ProjectMethod | None = None
    customer_id: UUID | None = None
    sales_owner_id: UUID | None = None
    manager_id: UUID | None = None
    ordered_on: date | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    expected_amount: int | None = Field(default=None, ge=0)
    probability: int | None = Field(default=None, ge=0, le=100)
    next_action: str | None = Field(default=None, max_length=200)
    next_action_on: date | None = None
    lost_reason: str | None = None
    competitor: str | None = Field(default=None, max_length=200)


class SeverityCounts(BaseModel):
    CRITICAL: int = 0
    HIGH: int = 0
    MEDIUM: int = 0
    LOW: int = 0
    UNKNOWN: int = 0


class EolCounts(BaseModel):
    eol: int = 0
    approaching: int = 0


class ProjectOut(BaseModel):
    id: UUID
    company_id: UUID
    department_id: UUID | None
    name: str
    description: str | None
    created_at: datetime
    method: str
    archived: bool = False  # 保留・失注
    # A deal (not ordered yet). Shown to everyone who can see the project.
    is_deal: bool = False
    manager: UserBrief | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    # Sales fields: None for partner (BP) users.
    status: str | None = None
    customer: CustomerBrief | None = None
    sales_owner: UserBrief | None = None
    ordered_on: date | None = None
    expected_amount: int | None = None
    probability: int | None = None
    next_action: str | None = None
    next_action_on: date | None = None
    lost_reason: str | None = None
    competitor: str | None = None
    estimate_count: int | None = None
    open_estimate_amount: int | None = None  # drafts and submitted, one-time
    won_amount: int | None = None  # won one-time estimates (受注金額)
    monthly_amount: int | None = None  # latest won monthly (maintenance) estimate
    can_sell: bool = False  # caller may edit customers and estimates here
    package_count: int = 0
    open_counts: SeverityCounts = SeverityCounts()
    eol_counts: EolCounts = EolCounts()
    last_scanned_at: datetime | None = None
    my_level: str | None = None


class MemberBody(BaseModel):
    user_id: UUID
    role: ProjectRole = ProjectRole.member


class MemberUpdate(BaseModel):
    role: ProjectRole


class MemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    display_name: str | None
    company_id: UUID | None
    role: str


class WebhookBody(BaseModel):
    type: WebhookType
    url: str
    min_severity: Severity = Severity.LOW
    locale: Literal["ja", "en"] = "ja"
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def https_only(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must start with https://")
        return v


class WebhookOut(BaseModel):
    id: UUID
    type: str
    url: str
    min_severity: str
    locale: str
    enabled: bool


class PackageBody(BaseModel):
    ecosystem: str
    name: str
    version: str

    @field_validator("ecosystem")
    @classmethod
    def known_ecosystem(cls, v: str) -> str:
        if v not in ECOSYSTEMS:
            raise ValueError(f"ecosystem must be one of {', '.join(ECOSYSTEMS)}")
        return v

    @field_validator("name", "version")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class UpgradeOut(BaseModel):
    """Lowest version that fixes every unresolved vulnerability of a package."""

    version: str | None  # None when none of them has a published fix
    bump: str | None  # patch | minor | major | unknown
    unfixed: int  # unresolved vulnerabilities with no published fix


class PackageOut(BaseModel):
    id: UUID
    ecosystem: str
    name: str
    version: str
    source: str
    last_scanned_at: datetime | None
    open_vulns: int = 0
    upgrade: UpgradeOut | None = None


class SkippedTool(BaseModel):
    tool: str
    version: str
    reason: str  # unsupported | unpinned


class ImportResult(BaseModel):
    filename: str
    kind: str = "packages"  # packages | runtimes
    # Lockfile ecosystem, "CycloneDX" / "SPDX", or None for tool files.
    format: str | None = None
    ecosystem: str  # comma-separated when an SBOM spans several
    added: int
    removed: int
    total: int
    skipped: list[SkippedTool] = []
    # SBOM components left out, by purl type ("(no purl)" when missing).
    unsupported: dict[str, int] = {}


class MatchOut(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    package_id: UUID
    ecosystem: str
    package_name: str
    package_version: str
    vuln_id: str
    aliases: list[str]
    summary: str | None
    severity: str
    cvss_score: float | None
    fixed_version: str | None
    status: str
    first_seen_at: datetime
    # Recommended upgrade for the package (across all its unresolved vulns).
    upgrade: UpgradeOut | None = None
    assignee: UserBrief | None = None
    due_date: date | None = None
    # The SLA deadline, when no due date is set (overdue falls back to it).
    sla_due_date: date | None = None
    updated_at: datetime | None = None
    comment_count: int = 0


class MatchUpdate(BaseModel):
    """Partial update: only the fields sent are changed (null clears)."""

    status: MatchStatus | None = None
    assignee_id: UUID | None = None
    due_date: date | None = None


class CommentBody(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        if len(v) > 10000:
            raise ValueError("must be at most 10000 characters")
        return v


class MatchEventOut(BaseModel):
    id: UUID
    kind: str  # comment | status | assignee | due_date
    user: UserBrief | None  # None: system or deleted user
    old_value: str | None
    new_value: str | None
    # For assignee changes: the users behind old_value / new_value.
    old_user: UserBrief | None = None
    new_user: UserBrief | None = None
    body: str | None
    created_at: datetime


class MatchDetail(MatchOut):
    events: list[MatchEventOut] = []


class TriageCounts(BaseModel):
    mine: int = 0  # unresolved and assigned to the caller
    overdue: int = 0  # unresolved and past due
    unassigned: int = 0  # open and nobody assigned


class DashboardOut(BaseModel):
    project_count: int
    package_count: int
    open_counts: SeverityCounts
    eol_counts: EolCounts
    triage: TriageCounts = TriageCounts()
    projects: list[ProjectOut]
    recent: list[MatchOut]
    eol: list[EolFindingOut]


class TokenBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # None = never expires.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class TokenOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_by_email: str | None
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class TokenCreated(TokenOut):
    # The secret. Shown once: only its hash is stored.
    token: str
