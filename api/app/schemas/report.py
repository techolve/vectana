from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.project import EolCounts, SeverityCounts


class OrgRow(BaseModel):
    """One company, department, or "no department" bucket of a company.

    Department figures include their sub-departments. Every figure covers only
    the projects the viewer can see; ``complete`` is false when the viewer does
    not manage the unit, so the row may not be the unit's whole picture."""

    kind: Literal["total", "company", "department", "unassigned"]
    id: UUID | None  # None for "total" and "unassigned"
    company_id: UUID | None  # None for "total"
    parent_id: UUID | None  # parent department; None directly under the company
    name: str
    depth: int  # 0 = company
    complete: bool
    project_count: int = 0
    open_counts: SeverityCounts = SeverityCounts()
    overdue: int = 0
    oldest_overdue_days: int | None = None
    eol_counts: EolCounts = EolCounts()
    nearest_eol_date: date | None = None
    nearest_eol_days: int | None = None  # negative once passed


class OverdueItem(BaseModel):
    match_id: UUID
    company_id: UUID
    project_id: UUID
    project_name: str
    package_name: str
    package_version: str
    vuln_id: str
    severity: str
    status: str
    first_seen_at: datetime
    due_date: date
    days_overdue: int


class EolItemOut(BaseModel):
    finding_id: UUID
    company_id: UUID
    project_id: UUID
    project_name: str
    product: str
    product_label: str
    version: str
    cycle: str | None
    eol_date: date
    days_left: int  # negative once passed


class OrgDashboardOut(BaseModel):
    today: date
    sla_days: dict[str, int]
    totals: OrgRow
    rows: list[OrgRow]
    overdue: list[OverdueItem]
    upcoming_eol: list[EolItemOut]


class SystemSettingsUpdate(BaseModel):
    """Partial update of system settings: omitted fields stay as they are."""

    eol_warning_days: int | None = Field(default=None, ge=1, le=730)
    sla_critical_days: int | None = Field(default=None, ge=1, le=3650)
    sla_high_days: int | None = Field(default=None, ge=1, le=3650)
    sla_medium_days: int | None = Field(default=None, ge=1, le=3650)
    sla_low_days: int | None = Field(default=None, ge=1, le=3650)
    sla_unknown_days: int | None = Field(default=None, ge=1, le=3650)
    report_enabled: bool | None = None
    report_weekday: int | None = Field(default=None, ge=0, le=6)
