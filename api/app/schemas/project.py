from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.models.package import ECOSYSTEMS, Severity
from app.models.project import ProjectRole, WebhookType
from app.schemas.eol import EolFindingOut


class ProjectBody(BaseModel):
    name: str
    description: str | None = None
    company_id: UUID | None = None  # defaults to the caller's company
    department_id: UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    department_id: UUID | None = None


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


class PackageOut(BaseModel):
    id: UUID
    ecosystem: str
    name: str
    version: str
    source: str
    last_scanned_at: datetime | None
    open_vulns: int = 0


class ImportResult(BaseModel):
    filename: str
    ecosystem: str
    added: int
    removed: int
    total: int


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


class MatchUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid(cls, v: str) -> str:
        if v not in ("open", "ack", "ignored"):
            raise ValueError("status must be open, ack or ignored")
        return v


class DashboardOut(BaseModel):
    project_count: int
    package_count: int
    open_counts: SeverityCounts
    eol_counts: EolCounts
    projects: list[ProjectOut]
    recent: list[MatchOut]
    eol: list[EolFindingOut]
