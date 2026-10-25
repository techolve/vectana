"""Deliver new vulnerability matches as digests.

Targets:
- email: every active member assigned to the project, filtered by their prefs
- webhooks: each enabled Discord / Slack webhook of the project

Each (match, channel, target) is recorded in ``notification_deliveries`` once
sent; anything not recorded (e.g. a failed send) is retried on the next run
for matches seen within ``RETRY_WINDOW``.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationDelivery, NotificationPref
from app.models.package import MatchStatus, Package, VulnMatch, meets_threshold
from app.models.project import Project, ProjectMember, ProjectWebhook
from app.models.user import User
from app.services.mailer import mail_enabled
from app.services.notify import digest

logger = logging.getLogger(__name__)

RETRY_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class Target:
    channel: str  # email | discord | slack
    target: str  # email address or webhook id
    address: str  # where to actually send (email or webhook URL)


async def notify_pending(session: AsyncSession) -> int:
    since = datetime.now(UTC) - RETRY_WINDOW
    rows = (
        await session.exec(
            select(VulnMatch, Package, Project)
            .join(Package, col(Package.id) == VulnMatch.package_id)
            .join(Project, col(Project.id) == Package.project_id)
            .where(VulnMatch.status == MatchStatus.open, VulnMatch.first_seen_at >= since)
        )
    ).all()
    if not rows:
        return 0

    match_ids = [m.id for m, _, _ in rows]
    delivered = {
        (d.match_id, d.channel, d.target)
        for d in (
            await session.exec(
                select(NotificationDelivery).where(
                    col(NotificationDelivery.match_id).in_(match_ids)
                )
            )
        ).all()
    }

    project_ids = {p.id for _, _, p in rows}
    webhooks: dict[UUID, list[ProjectWebhook]] = defaultdict(list)
    for w in (
        await session.exec(
            select(ProjectWebhook).where(
                col(ProjectWebhook.project_id).in_(project_ids),
                col(ProjectWebhook.enabled).is_(True),
            )
        )
    ).all():
        webhooks[w.project_id].append(w)

    recipients: dict[UUID, list[tuple[User, NotificationPref | None]]] = defaultdict(list)
    for member, user, maybe_pref in (
        await session.exec(
            select(ProjectMember, User, NotificationPref)
            .join(User, col(User.id) == ProjectMember.user_id)
            .join(NotificationPref, col(NotificationPref.user_id) == User.id, isouter=True)
            .where(
                col(ProjectMember.project_id).in_(project_ids),
                col(User.is_active).is_(True),
            )
        )
    ).all():
        recipients[member.project_id].append((user, maybe_pref))

    can_email = mail_enabled()
    queue: dict[Target, list[digest.Item]] = defaultdict(list)
    for match, package, project in rows:
        item = digest.Item(match=match, package=package, project=project)
        for hook in webhooks.get(project.id, []):
            t = Target(hook.type, str(hook.id), hook.url)
            if (match.id, t.channel, t.target) not in delivered and meets_threshold(
                match.severity, hook.min_severity
            ):
                queue[t].append(item)
        if not can_email:
            continue
        for user, pref in recipients.get(project.id, []):
            if pref is not None and not pref.email_enabled:
                continue
            minimum = pref.min_severity if pref else "LOW"
            t = Target("email", user.email, user.email)
            if (match.id, "email", t.target) not in delivered and meets_threshold(
                match.severity, minimum
            ):
                queue[t].append(item)

    sent = 0
    for target, items in queue.items():
        try:
            await digest.send(target.channel, target.address, items)
        except Exception:
            logger.exception(
                "Notification to %s:%s failed; will retry",
                target.channel,
                target.target,
            )
            continue
        for item in items:
            session.add(
                NotificationDelivery(
                    match_id=item.match.id, channel=target.channel, target=target.target
                )
            )
        await session.commit()
        sent += 1
    logger.info("Sent %d digest(s)", sent)
    return sent
