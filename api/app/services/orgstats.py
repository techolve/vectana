"""Cross-organization figures: open vulnerabilities, overdue items and EOL per
company and department, limited to the projects a viewer can see.

"Overdue" means an open or acknowledged vulnerability past its remediation
deadline: its own ``due_date`` when one is set, otherwise ``first_seen_at`` +
the SLA days for its severity (system settings).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, visible_projects_clause
from app.models.eol import AppSettings, EolFinding, EolStatus
from app.models.organization import Company, Department
from app.models.package import MatchStatus, Package, Severity, VulnMatch
from app.models.project import Project
from app.schemas.project import EolCounts, SeverityCounts
from app.schemas.report import EolItemOut, OrgDashboardOut, OrgRow, OverdueItem

UNRESOLVED = (MatchStatus.open, MatchStatus.ack)
DEFAULT_SLA = {
    Severity.CRITICAL: 7,
    Severity.HIGH: 30,
    Severity.MEDIUM: 90,
    Severity.LOW: 180,
    Severity.UNKNOWN: 90,
}
LIST_LIMIT = 50


async def sla_days(session: AsyncSession) -> dict[str, int]:
    row = await session.get(AppSettings, 1)
    if row is None:
        return {s.value: d for s, d in DEFAULT_SLA.items()}
    return {
        Severity.CRITICAL.value: row.sla_critical_days,
        Severity.HIGH.value: row.sla_high_days,
        Severity.MEDIUM.value: row.sla_medium_days,
        Severity.LOW.value: row.sla_low_days,
        Severity.UNKNOWN.value: row.sla_unknown_days,
    }


def _aware(ts: datetime) -> datetime:
    # SQLite hands back naive datetimes; they are stored as UTC.
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def due_date(severity: str, first_seen_at: datetime, sla: dict[str, int]) -> date:
    days = sla.get(severity, sla[Severity.UNKNOWN.value])
    return (_aware(first_seen_at) + timedelta(days=days)).astimezone(UTC).date()


def effective_due(match: VulnMatch, sla: dict[str, int]) -> date:
    """The match's own due date, or the SLA deadline when none is set."""
    return match.due_date or due_date(match.severity, match.first_seen_at, sla)


def overdue_clause(sla: dict[str, int], today: date) -> ColumnElement[bool]:
    """SQL condition on ``VulnMatch``: unresolved and past its effective due date.

    Same rule as ``effective_due(...) < today``: an SLA deadline has passed
    once ``first_seen_at`` is earlier than today's UTC midnight minus the SLA."""
    midnight = datetime.combine(today, time.min, tzinfo=UTC)
    known = [s.value for s in Severity]
    by_severity = [
        and_(
            col(VulnMatch.severity) == s,
            col(VulnMatch.first_seen_at) < midnight - timedelta(days=d),
        )
        for s, d in sla.items()
    ]
    unknown_cutoff = midnight - timedelta(days=sla[Severity.UNKNOWN.value])
    by_severity.append(
        and_(
            col(VulnMatch.severity).not_in(known),
            col(VulnMatch.first_seen_at) < unknown_cutoff,
        )
    )
    return and_(
        col(VulnMatch.status).in_(UNRESOLVED),
        or_(
            and_(col(VulnMatch.due_date).is_not(None), col(VulnMatch.due_date) < today),
            and_(col(VulnMatch.due_date).is_(None), or_(*by_severity)),
        ),
    )


@dataclass
class _Stats:
    project_count: int = 0
    open_counts: SeverityCounts = field(default_factory=SeverityCounts)
    overdue: int = 0
    oldest_overdue_days: int | None = None
    eol_counts: EolCounts = field(default_factory=EolCounts)
    nearest_eol_date: date | None = None

    def add(self, other: _Stats) -> None:
        self.project_count += other.project_count
        for key in SeverityCounts.model_fields:
            setattr(
                self.open_counts,
                key,
                getattr(self.open_counts, key) + getattr(other.open_counts, key),
            )
        self.overdue += other.overdue
        self.oldest_overdue_days = _max(self.oldest_overdue_days, other.oldest_overdue_days)
        self.eol_counts.eol += other.eol_counts.eol
        self.eol_counts.approaching += other.eol_counts.approaching
        self.nearest_eol_date = _min(self.nearest_eol_date, other.nearest_eol_date)


def _max(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else max(a, b)


def _min(a: date | None, b: date | None) -> date | None:
    return b if a is None else a if b is None else min(a, b)


def _row(
    stats: _Stats,
    today: date,
    *,
    kind: str,
    id: UUID | None,
    company_id: UUID | None,
    parent_id: UUID | None,
    name: str,
    depth: int,
    complete: bool,
) -> OrgRow:
    return OrgRow(
        kind=kind,  # type: ignore[arg-type]
        id=id,
        company_id=company_id,
        parent_id=parent_id,
        name=name,
        depth=depth,
        complete=complete,
        project_count=stats.project_count,
        open_counts=stats.open_counts,
        overdue=stats.overdue,
        oldest_overdue_days=stats.oldest_overdue_days,
        eol_counts=stats.eol_counts,
        nearest_eol_date=stats.nearest_eol_date,
        nearest_eol_days=(stats.nearest_eol_date - today).days if stats.nearest_eol_date else None,
    )


async def org_dashboard(
    actor: Actor,
    session: AsyncSession,
    company_id: UUID | None = None,
    today: date | None = None,
) -> OrgDashboardOut:
    today = today or datetime.now(UTC).date()
    sla = await sla_days(session)

    query = select(Project).where(visible_projects_clause(actor))
    if company_id is not None:
        query = query.where(Project.company_id == company_id)
    projects = {p.id: p for p in (await session.exec(query)).all()}
    ids = list(projects)

    per_project: dict[UUID, _Stats] = defaultdict(_Stats)
    for pid in ids:
        per_project[pid].project_count = 1
    overdue_items: list[OverdueItem] = []
    eol_items: list[EolItemOut] = []

    if ids:
        for pid, severity, n in (
            await session.exec(
                select(Package.project_id, VulnMatch.severity, func.count())
                .join(Package, col(Package.id) == VulnMatch.package_id)
                .where(col(Package.project_id).in_(ids), VulnMatch.status == MatchStatus.open)
                .group_by(col(Package.project_id), col(VulnMatch.severity))
            )
        ).all():
            setattr(per_project[pid].open_counts, severity, n)

        for match, package in (
            await session.exec(
                select(VulnMatch, Package)
                .join(Package, col(Package.id) == VulnMatch.package_id)
                .where(col(Package.project_id).in_(ids), col(VulnMatch.status).in_(UNRESOLVED))
            )
        ).all():
            due = effective_due(match, sla)
            if due >= today:
                continue
            late = (today - due).days
            stats = per_project[package.project_id]
            stats.overdue += 1
            stats.oldest_overdue_days = _max(stats.oldest_overdue_days, late)
            project = projects[package.project_id]
            overdue_items.append(
                OverdueItem(
                    match_id=match.id,
                    company_id=project.company_id,
                    project_id=project.id,
                    project_name=project.name,
                    package_name=package.name,
                    package_version=package.version,
                    vuln_id=match.vuln_id,
                    severity=match.severity,
                    status=match.status,
                    first_seen_at=_aware(match.first_seen_at),
                    due_date=due,
                    days_overdue=late,
                )
            )

        for finding in (
            await session.exec(
                select(EolFinding).where(
                    col(EolFinding.project_id).in_(ids),
                    col(EolFinding.status).in_([EolStatus.eol, EolStatus.approaching]),
                )
            )
        ).all():
            stats = per_project[finding.project_id]
            setattr(stats.eol_counts, finding.status, getattr(stats.eol_counts, finding.status) + 1)
            if finding.eol_date is None:
                continue
            stats.nearest_eol_date = _min(stats.nearest_eol_date, finding.eol_date)
            project = projects[finding.project_id]
            eol_items.append(
                EolItemOut(
                    finding_id=finding.id,
                    company_id=project.company_id,
                    project_id=project.id,
                    project_name=project.name,
                    product=finding.product,
                    product_label=finding.product_label,
                    version=finding.version,
                    cycle=finding.cycle,
                    eol_date=finding.eol_date,
                    days_left=(finding.eol_date - today).days,
                )
            )

    rows, totals = await _tree(actor, session, projects, per_project, today)
    overdue_items.sort(key=lambda i: (-i.days_overdue, i.project_name, i.package_name))
    eol_items.sort(key=lambda i: (i.eol_date, i.project_name, i.product))
    return OrgDashboardOut(
        today=today,
        sla_days=sla,
        totals=totals,
        rows=rows,
        overdue=overdue_items[:LIST_LIMIT],
        upcoming_eol=eol_items[:LIST_LIMIT],
    )


async def _tree(
    actor: Actor,
    session: AsyncSession,
    projects: dict[UUID, Project],
    per_project: dict[UUID, _Stats],
    today: date,
) -> tuple[list[OrgRow], OrgRow]:
    company_ids = {p.company_id for p in projects.values()}
    companies = (
        sorted(
            (await session.exec(select(Company).where(col(Company.id).in_(company_ids)))).all(),
            key=lambda c: c.name,
        )
        if company_ids
        else []
    )
    departments = (
        list(
            (
                await session.exec(
                    select(Department).where(col(Department.company_id).in_(company_ids))
                )
            ).all()
        )
        if company_ids
        else []
    )
    children: dict[UUID | None, list[Department]] = defaultdict(list)
    by_company: dict[UUID, list[Department]] = defaultdict(list)
    for d in departments:
        by_company[d.company_id].append(d)
    for d in departments:
        children[d.parent_id].append(d)
    for siblings in children.values():
        siblings.sort(key=lambda d: d.name)

    own: dict[UUID, _Stats] = defaultdict(_Stats)  # projects directly in a department
    unassigned: dict[UUID, _Stats] = defaultdict(_Stats)
    for pid, project in projects.items():
        target = (
            own[project.department_id] if project.department_id else unassigned[project.company_id]
        )
        target.add(per_project[pid])

    rows: list[OrgRow] = []
    totals = _Stats()

    def walk(dept: Department, depth: int, company_complete: bool) -> tuple[_Stats, list[OrgRow]]:
        stats = _Stats()
        stats.add(own.get(dept.id, _Stats()))
        sub_rows: list[OrgRow] = []
        for child in children.get(dept.id, []):
            child_stats, child_rows = walk(child, depth + 1, company_complete)
            stats.add(child_stats)
            sub_rows += child_rows
        if stats.project_count == 0:
            return stats, []
        complete = company_complete or dept.id in actor.managed_department_ids
        row = _row(
            stats,
            today,
            kind="department",
            id=dept.id,
            company_id=dept.company_id,
            parent_id=dept.parent_id,
            name=dept.name,
            depth=depth,
            complete=complete,
        )
        return stats, [row, *sub_rows]

    for company in companies:
        company_complete = actor.can_manage_company(company.id)
        company_stats = _Stats()
        company_rows: list[OrgRow] = []
        for dept in sorted(
            (d for d in by_company[company.id] if d.parent_id is None), key=lambda d: d.name
        ):
            stats, dept_rows = walk(dept, 1, company_complete)
            company_stats.add(stats)
            company_rows += dept_rows
        if company.id in unassigned:
            stats = unassigned[company.id]
            company_stats.add(stats)
        # A "no department" row only helps next to department rows.
        if company.id in unassigned and company_rows:
            company_rows.append(
                _row(
                    unassigned[company.id],
                    today,
                    kind="unassigned",
                    id=None,
                    company_id=company.id,
                    parent_id=None,
                    name="",
                    depth=1,
                    complete=company_complete,
                )
            )
        rows.append(
            _row(
                company_stats,
                today,
                kind="company",
                id=company.id,
                company_id=company.id,
                parent_id=None,
                name=company.name,
                depth=0,
                complete=company_complete,
            )
        )
        rows += company_rows
        totals.add(company_stats)

    total_row = _row(
        totals,
        today,
        kind="total",
        id=None,
        company_id=None,
        parent_id=None,
        name="",
        depth=0,
        complete=actor.is_group_admin,
    )
    return rows, total_row
