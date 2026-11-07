"""Cross-organization dashboard (per company and department) and its CSV export."""

import csv
import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, get_actor
from app.core.database import get_session
from app.i18n import request_locale, t
from app.schemas.report import OrgDashboardOut, OrgRow
from app.services import orgstats

router = APIRouter(prefix="/api", tags=["reports"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


@router.get("/org-dashboard", response_model=OrgDashboardOut, summary="組織別ダッシュボード")
async def org_dashboard(
    actor: CurrentActor,
    session: Session,
    company_id: Annotated[UUID | None, Query()] = None,
) -> OrgDashboardOut:
    return await orgstats.org_dashboard(actor, session, company_id)


def unit_paths(rows: list[OrgRow], locale: str) -> list[tuple[str, str]]:
    """(company, department path) per row, e.g. ("親会社", "開発本部 / 第1開発部")."""
    out: list[tuple[str, str]] = []
    company = ""
    trail: list[str] = []
    for row in rows:
        if row.kind == "company":
            company, trail = row.name, []
            out.append((company, ""))
        elif row.kind == "unassigned":
            out.append((company, t(locale, "report.unassigned")))
        else:
            trail = [*trail[: row.depth - 1], row.name]
            out.append((company, " / ".join(trail)))
    return out


CSV_COLUMNS = (
    "company",
    "department",
    "projects",
    "critical",
    "high",
    "medium",
    "low",
    "unknown",
    "overdue",
    "oldest_overdue_days",
    "eol",
    "eol_approaching",
    "nearest_eol_date",
    "nearest_eol_days",
    "partial",
)


def render_csv(data: OrgDashboardOut, locale: str) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([t(locale, f"report.col.{c}") for c in CSV_COLUMNS])
    for row, (company, department) in zip(data.rows, unit_paths(data.rows, locale), strict=True):
        c = row.open_counts
        writer.writerow(
            [
                company,
                department,
                row.project_count,
                c.CRITICAL,
                c.HIGH,
                c.MEDIUM,
                c.LOW,
                c.UNKNOWN,
                row.overdue,
                "" if row.oldest_overdue_days is None else row.oldest_overdue_days,
                row.eol_counts.eol,
                row.eol_counts.approaching,
                row.nearest_eol_date.isoformat() if row.nearest_eol_date else "",
                "" if row.nearest_eol_days is None else row.nearest_eol_days,
                "" if row.complete else "1",
            ]
        )
    return buf.getvalue()


@router.get("/org-dashboard.csv", summary="組織別ダッシュボード（CSV）")
async def org_dashboard_csv(
    request: Request,
    actor: CurrentActor,
    session: Session,
    company_id: Annotated[UUID | None, Query()] = None,
) -> Response:
    data = await orgstats.org_dashboard(actor, session, company_id)
    locale = request_locale(request)
    # BOM so Excel opens UTF-8 (Japanese names) correctly.
    body = "﻿" + render_csv(data, locale)
    filename = f"vectana-org-{data.today.isoformat()}.csv"
    return Response(
        body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
