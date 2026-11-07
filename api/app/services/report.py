"""Weekly organization report by email.

Recipients are group admins, company admins and department heads. Each gets
the organization dashboard as they would see it in the app (same visibility
rules), once per ISO week, on the weekday set in system settings at or after
``REPORT_HOUR`` in ``REPORT_TIMEZONE``. ``report_deliveries`` records each
send, so restarts or frequent worker runs never send twice in a week, and a
failed send is retried on the next run.
"""

import logging
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import load_actor
from app.core.config import settings
from app.i18n import t
from app.models.eol import AppSettings
from app.models.notification import NotificationPref
from app.models.organization import UserDepartment
from app.models.report import ReportDelivery
from app.models.user import User, UserRole
from app.schemas.report import OrgDashboardOut, OrgRow
from app.services.mailer import mail_enabled, send_email
from app.services.orgstats import org_dashboard

logger = logging.getLogger(__name__)

TOP = 10


def period_of(now: datetime) -> str:
    year, week, _ = now.astimezone(ZoneInfo(settings.report_timezone)).isocalendar()
    return f"{year}-W{week:02d}"


def is_due(now: datetime, weekday: int) -> bool:
    local = now.astimezone(ZoneInfo(settings.report_timezone))
    return local.weekday() == weekday and local.hour >= settings.report_hour


async def recipients(session: AsyncSession) -> list[User]:
    heads = select(UserDepartment.user_id).where(col(UserDepartment.is_head).is_(True))
    rows = (
        await session.exec(
            select(User, NotificationPref)
            .join(NotificationPref, col(NotificationPref.user_id) == User.id, isouter=True)
            .where(
                col(User.is_active).is_(True),
                or_(
                    col(User.role).in_([UserRole.group_admin, UserRole.company_admin]),
                    col(User.id).in_(heads),
                ),
            )
            .order_by(User.email)
        )
    ).all()
    return [user for user, pref in rows if pref is None or pref.email_enabled]


def org_url(locale: str) -> str:
    return f"{settings.web_url.rstrip('/')}/{locale}/org/"


def _unit_label(row: OrgRow, locale: str) -> str:
    name = t(locale, "report.unassigned") if row.kind == "unassigned" else row.name
    return ("  " * row.depth) + name + ("" if row.complete else " *")


def _open_total(row: OrgRow) -> int:
    c = row.open_counts
    return c.CRITICAL + c.HIGH + c.MEDIUM + c.LOW + c.UNKNOWN


def _eol_when(days: int | None, locale: str) -> str:
    if days is None:
        return "-"
    if days < 0:
        return t(locale, "report.days_over", days=-days)
    return t(locale, "report.days_left", days=days)


def subject(data: OrgDashboardOut, period: str, locale: str) -> str:
    return t(locale, "report.subject", period=period, overdue=data.totals.overdue)


def _summary(data: OrgDashboardOut, locale: str) -> str:
    total = data.totals
    return t(
        locale,
        "report.summary",
        projects=total.project_count,
        open=_open_total(total),
        critical=total.open_counts.CRITICAL,
        high=total.open_counts.HIGH,
        overdue=total.overdue,
        eol=total.eol_counts.eol,
        approaching=total.eol_counts.approaching,
    )


def _intro(data: OrgDashboardOut, locale: str, whole_group: bool) -> str:
    scope = t(locale, "report.scope.group" if whole_group else "report.scope.mine")
    return t(locale, "report.intro", scope=scope, today=data.today.isoformat())


def render_text(data: OrgDashboardOut, locale: str, whole_group: bool) -> str:
    lines = [_intro(data, locale, whole_group), _summary(data, locale), ""]
    lines.append(t(locale, "report.units"))
    for row in data.rows:
        lines.append(
            f"{_unit_label(row, locale)}: "
            f"{t(locale, 'report.col.projects')} {row.project_count} / "
            f"{t(locale, 'report.col.open')} {_open_total(row)} / "
            f"{t(locale, 'report.col.overdue')} {row.overdue} / "
            f"EOL {row.eol_counts.eol}+{row.eol_counts.approaching} "
            f"({_eol_when(row.nearest_eol_days, locale)})"
        )
    if any(not r.complete for r in data.rows):
        lines.append(t(locale, "report.partial_note"))
    lines += ["", t(locale, "report.overdue", count=TOP)]
    if not data.overdue:
        lines.append(t(locale, "report.none"))
    for i in data.overdue[:TOP]:
        lines.append(
            f"[{i.severity}] {i.project_name}: {i.package_name}@{i.package_version} {i.vuln_id} "
            f"— {t(locale, 'report.days_over', days=i.days_overdue)}"
        )
    lines += ["", t(locale, "report.upcoming_eol", count=TOP)]
    if not data.upcoming_eol:
        lines.append(t(locale, "report.none"))
    for e in data.upcoming_eol[:TOP]:
        lines.append(
            f"{e.project_name}: {e.product_label} {e.cycle or e.version} — "
            f"{e.eol_date.isoformat()} ({_eol_when(e.days_left, locale)})"
        )
    lines += ["", f"{t(locale, 'report.open_link')}: {org_url(locale)}"]
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (
        '<table border="1" cellpadding="6" style="border-collapse:collapse;font-size:13px">'
        f"<tr>{head}</tr>{body}</table>"
    )


def render_html(data: OrgDashboardOut, locale: str, whole_group: bool) -> str:
    def col_(key: str) -> str:
        return t(locale, f"report.col.{key}")

    parts = [
        f"<p>{escape(_intro(data, locale, whole_group))}</p>",
        f"<p><b>{escape(_summary(data, locale))}</b></p>",
        f"<h3>{escape(t(locale, 'report.units'))}</h3>",
    ]
    unit_rows = []
    for row in data.rows:
        label = escape(_unit_label(row, locale).strip())
        indent = row.depth * 16
        weight = "bold" if row.kind == "company" else "normal"
        unit_rows.append(
            [
                f'<span style="padding-left:{indent}px;font-weight:{weight}">{label}</span>',
                str(row.project_count),
                str(_open_total(row)),
                str(row.open_counts.CRITICAL),
                str(row.open_counts.HIGH),
                f'<span style="color:#b91c1c">{row.overdue}</span>' if row.overdue else "0",
                str(row.eol_counts.eol),
                str(row.eol_counts.approaching),
                escape(_eol_when(row.nearest_eol_days, locale)),
            ]
        )
    headers = ["unit", "projects", "open", "critical", "high", "overdue", "eol", "eol_approaching"]
    parts.append(_table([col_(h) for h in headers] + [col_("nearest_eol_days")], unit_rows))
    if any(not r.complete for r in data.rows):
        parts.append(f"<p><small>{escape(t(locale, 'report.partial_note'))}</small></p>")

    parts.append(f"<h3>{escape(t(locale, 'report.overdue', count=TOP))}</h3>")
    if data.overdue:
        parts.append(
            _table(
                [t(locale, f"digest.col.{c}") for c in ("severity", "project", "package", "vuln")]
                + [col_("due"), col_("days_over")],
                [
                    [
                        escape(i.severity),
                        escape(i.project_name),
                        f"{escape(i.package_name)}@{escape(i.package_version)}",
                        f'<a href="https://osv.dev/vulnerability/{escape(i.vuln_id)}">'
                        f"{escape(i.vuln_id)}</a>",
                        i.due_date.isoformat(),
                        str(i.days_overdue),
                    ]
                    for i in data.overdue[:TOP]
                ],
            )
        )
    else:
        parts.append(f"<p>{escape(t(locale, 'report.none'))}</p>")

    parts.append(f"<h3>{escape(t(locale, 'report.upcoming_eol', count=TOP))}</h3>")
    if data.upcoming_eol:
        parts.append(
            _table(
                [t(locale, f"digest.col.{c}") for c in ("project", "product", "eol_date")]
                + [col_("days_left")],
                [
                    [
                        escape(e.project_name),
                        f"{escape(e.product_label)} {escape(e.cycle or e.version)}",
                        e.eol_date.isoformat(),
                        escape(_eol_when(e.days_left, locale)),
                    ]
                    for e in data.upcoming_eol[:TOP]
                ],
            )
        )
    else:
        parts.append(f"<p>{escape(t(locale, 'report.none'))}</p>")
    parts.append(f'<p><a href="{org_url(locale)}">{escape(t(locale, "report.open_link"))}</a></p>')
    return "".join(parts)


async def send_weekly_reports(
    session: AsyncSession, now: datetime | None = None, force: bool = False
) -> int:
    """Send this week's report to every recipient who hasn't had it yet.
    ``force`` skips the weekday/enabled check (manual runs). Returns sends."""
    now = now or datetime.now(UTC)
    app_settings = await session.get(AppSettings, 1) or AppSettings(id=1)
    if not force and (
        not app_settings.report_enabled or not is_due(now, app_settings.report_weekday)
    ):
        return 0
    if not mail_enabled() and settings.mail_backend != "none":
        logger.info("Mail is not configured; skipping the weekly report")
        return 0

    period = period_of(now)
    already = set(
        (
            await session.exec(
                select(ReportDelivery.user_id).where(ReportDelivery.period == period)
            )
        ).all()
    )
    sent = 0
    for user in await recipients(session):
        if user.id in already:
            continue
        actor = await load_actor(user, session)
        data = await org_dashboard(actor, session, today=now.astimezone(UTC).date())
        if data.totals.project_count == 0:
            continue
        locale = user.locale
        try:
            await send_email(
                to=user.email,
                subject=subject(data, period, locale),
                text=render_text(data, locale, actor.is_group_admin),
                html=render_html(data, locale, actor.is_group_admin),
            )
        except Exception:
            logger.exception("Weekly report to %s failed; will retry", user.email)
            continue
        session.add(ReportDelivery(user_id=user.id, period=period))
        await session.commit()
        sent += 1
    logger.info("Sent %d weekly report(s) for %s", sent, period)
    return sent
