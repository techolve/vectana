from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, nullable_ts_field

# OSV ecosystem identifiers accepted for manual registration.
ECOSYSTEMS = (
    "npm",
    "PyPI",
    "Pub",
    "Maven",
    "Go",
    "crates.io",
    "RubyGems",
    "Packagist",
    "NuGet",
)


class Severity(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_RANK = {
    Severity.UNKNOWN: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def meets_threshold(severity: str, minimum: str) -> bool:
    """UNKNOWN always passes: an unscored advisory is not a reason to stay quiet."""
    if severity == Severity.UNKNOWN:
        return True
    return SEVERITY_RANK.get(Severity(severity), 0) >= SEVERITY_RANK.get(Severity(minimum), 0)


class Package(SQLModel, table=True):
    """A dependency a project uses (= what we watch)."""

    __tablename__ = "packages"
    __table_args__ = (UniqueConstraint("project_id", "ecosystem", "name", "version"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    ecosystem: str = Field(max_length=30)
    name: str = Field(max_length=300)
    version: str = Field(max_length=100)
    # "manual" or "lockfile:<filename>"
    source: str = Field(default="manual", max_length=100)
    last_scanned_at: datetime | None = nullable_ts_field()
    created_at: datetime = created_at_field()


class MatchStatus(StrEnum):
    open = "open"
    ack = "ack"  # 確認済み
    ignored = "ignored"


class VulnMatch(SQLModel, table=True):
    """A vulnerability that affects a registered package version. Also the
    dedup record: the same (package, vuln) pair is only ever inserted once."""

    __tablename__ = "vuln_matches"
    __table_args__ = (UniqueConstraint("package_id", "vuln_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    package_id: UUID = Field(foreign_key="packages.id", index=True, ondelete="CASCADE")
    vuln_id: str = Field(max_length=100)  # OSV id, e.g. GHSA-xxxx / PYSEC-xxxx
    aliases: list[Any] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    summary: str | None = Field(default=None)
    severity: str = Field(default=Severity.UNKNOWN, max_length=20)
    cvss_score: float | None = Field(default=None)
    fixed_version: str | None = Field(default=None, max_length=100)
    status: str = Field(default=MatchStatus.open, max_length=20)
    first_seen_at: datetime = created_at_field()
