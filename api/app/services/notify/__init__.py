"""Deliver new vulnerability matches and EOL changes as digests.

Targets:
- email: every active member assigned to the project, filtered by their prefs,
  written in the member's language
- webhooks: each enabled Discord / Slack webhook of the project, in its language

Each delivered item is recorded per (channel, target) — ``notification_deliveries``
for vulnerabilities, ``eol_deliveries`` per EOL stage — so nothing is sent twice
and anything that failed is retried on the next run (within ``RETRY_WINDOW``).
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.eol import EolDelivery, EolFinding, EolStatus
from app.models.notification import NotificationDelivery, NotificationPref
from app.models.package import MatchStatus, Package, VulnMatch, meets_threshold
from app.models.project import Project, ProjectMember, ProjectWebhook
from app.models.user import User
from app.services.mailer import mail_enabled
from app.services.notify import digest

logger = logging.getLogger(__name__)

RETRY_WINDOW = timedelta(days=7)
# EOL notices are sent for these stages, once each.
EOL_STAGES = (EolStatus.approaching, EolStatus.eol)


@dataclass(frozen=True)
class Target:
    channel: str  # email | discord | slack
    target: str  # email address or webhook id
    address: str  # where to actually send (email or webhook URL)
    locale: str


@dataclass(frozen=True)
class Recipient:
    target: Target
    min_severity: str


async def _recipients(session: AsyncSession, project_ids: set[UUID]) -> dict[UUID, list[Recipient]]:
    out: dict[UUID, list[Recipient]] = defaultdict(list)
    if not project_ids:
        return out
    for w in (
        await session.exec(
            select(ProjectWebhook).where(
                col(ProjectWebhook.project_id).in_(project_ids),
                col(ProjectWebhook.enabled).is_(True),
            )
        )
    ).all():
        out[w.project_id].append(
            Recipient(Target(w.type, str(w.id), w.url, w.locale), w.min_severity)
        )

    if not mail_enabled():
        return out
    for member, user, pref in (
        await session.exec(
            select(ProjectMember, User, NotificationPref)
            .join(User, col(User.id) == ProjectMember.user_id)
            .join(NotificationPref, col(NotificationPref.user_id) == User.id, isouter=True)
            .where(col(ProjectMember.project_id).in_(project_ids), col(User.is_active).is_(True))
        )
    ).all():
        if pref is not None and not pref.email_enabled:
            continue
        target = Target("email", user.email, user.email, user.locale)
        out[member.project_id].append(Recipient(target, pref.min_severity if pref else "LOW"))
    return out


async def notify_pending(session: AsyncSession) -> int:
    since = datetime.now(UTC) - RETRY_WINDOW
    vuln_rows = (
        await session.exec(
            select(VulnMatch, Package, Project)
            .join(Package, col(Package.id) == VulnMatch.package_id)
            .join(Project, col(Project.id) == Package.project_id)
            .where(VulnMatch.status == MatchStatus.open, VulnMatch.first_seen_at >= since)
        )
    ).all()
    eol_rows = (
        await session.exec(
            select(EolFinding, Project)
            .join(Project, col(Project.id) == EolFinding.project_id)
            .where(col(EolFinding.status).in_(EOL_STAGES), EolFinding.status_changed_at >= since)
        )
    ).all()
    if not vuln_rows and not eol_rows:
        return 0

    sent_vulns = (
        {
            (d.match_id, d.channel, d.target)
            for d in (
                await session.exec(
                    select(NotificationDelivery).where(
                        col(NotificationDelivery.match_id).in_([m.id for m, _, _ in vuln_rows])
                    )
                )
            ).all()
        }
        if vuln_rows
        else set()
    )
    sent_eol = (
        {
            (d.finding_id, d.stage, d.channel, d.target)
            for d in (
                await session.exec(
                    select(EolDelivery).where(
                        col(EolDelivery.finding_id).in_([f.id for f, _ in eol_rows])
                    )
                )
            ).all()
        }
        if eol_rows
        else set()
    )

    project_ids = {p.id for _, _, p in vuln_rows} | {p.id for _, p in eol_rows}
    recipients = await _recipients(session, project_ids)

    queue: dict[Target, digest.Digest] = defaultdict(digest.Digest)
    for match, package, project in vuln_rows:
        for r in recipients.get(project.id, []):
            t = r.target
            if (match.id, t.channel, t.target) not in sent_vulns and meets_threshold(
                match.severity, r.min_severity
            ):
                queue[t].vulns.append(digest.Item(match=match, package=package, project=project))
    for finding, project in eol_rows:
        for r in recipients.get(project.id, []):
            t = r.target
            if (finding.id, finding.status, t.channel, t.target) not in sent_eol:
                queue[t].eol.append(digest.EolItem(finding=finding, project=project))

    sent = 0
    for target, d in queue.items():
        try:
            await digest.send(target.channel, target.address, d, target.locale)
        except Exception:
            logger.exception(
                "Notification to %s:%s failed; will retry", target.channel, target.target
            )
            continue
        for item in d.vulns:
            session.add(
                NotificationDelivery(
                    match_id=item.match.id, channel=target.channel, target=target.target
                )
            )
        for e in d.eol:
            session.add(
                EolDelivery(
                    finding_id=e.finding.id,
                    stage=e.finding.status,
                    channel=target.channel,
                    target=target.target,
                )
            )
        await session.commit()
        sent += 1
    logger.info("Sent %d digest(s)", sent)
    return sent
