"""Outbound email.

The backend is chosen by ``MAIL_BACKEND``:
- ``smtp``: any SMTP relay (Mailpit locally, Resend / other relays in production)
- ``cloudflare``: Cloudflare Email Service REST API
- ``none``: log and drop (useful before mail is set up)

``send_email`` raises on failure so callers decide whether to surface or retry.
"""

import logging
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from html import escape

import aiosmtplib
import httpx

from app.core.config import settings
from app.i18n import t

logger = logging.getLogger(__name__)


class MailNotConfigured(RuntimeError):
    pass


def mail_enabled() -> bool:
    if settings.mail_backend == "smtp":
        return bool(settings.smtp_host)
    if settings.mail_backend == "cloudflare":
        return bool(settings.cloudflare_account_id and settings.cloudflare_api_token)
    return False


async def send_email(*, to: str, subject: str, text: str, html: str | None = None) -> None:
    backend = settings.mail_backend
    if backend == "none":
        logger.info("[mail:none] to=%s subject=%s", to, subject)
        return
    if not mail_enabled():
        raise MailNotConfigured(f"Mail backend {backend!r} is not configured")
    if backend == "smtp":
        await _send_smtp(to, subject, text, html)
    elif backend == "cloudflare":
        await _send_cloudflare(to, subject, text, html)
    else:
        raise MailNotConfigured(f"Unknown mail backend {backend!r}")


def build_message(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    # Date and Message-ID are required; strict relays (e.g. amavis) reject mail without them.
    _, sender = parseaddr(settings.mail_from)
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    message.set_content(text)
    if html is not None:
        message.add_alternative(html, subtype="html")
    return message


async def _send_smtp(to: str, subject: str, text: str, html: str | None) -> None:
    message = build_message(to, subject, text, html)
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        use_tls=settings.smtp_use_tls,
        start_tls=settings.smtp_start_tls if not settings.smtp_use_tls else False,
    )


async def _send_cloudflare(to: str, subject: str, text: str, html: str | None) -> None:
    # The REST API documents "from" as a bare address.
    _, address = parseaddr(settings.mail_from)
    payload: dict[str, object] = {
        "from": address,
        "to": to,
        "subject": subject,
        "text": text,
    }
    if html is not None:
        payload["html"] = html
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/email/sending/send"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"},
        )
    response.raise_for_status()


async def send_invitation_email(
    *, to: str, company_name: str, accept_url: str, locale: str
) -> bool:
    """Never raises; returns True if the email was sent."""
    days = settings.invitation_expire_days
    text = "\n\n".join(
        [
            t(locale, "invite.body", company=company_name),
            f"{t(locale, 'invite.link_hint', days=days)}\n{accept_url}",
            t(locale, "invite.ignore"),
        ]
    )
    html = (
        f"<p>{escape(t(locale, 'invite.body', company=company_name))}</p>"
        f'<p><a href="{escape(accept_url)}">{escape(t(locale, "invite.action"))}</a></p>'
        f'<p style="color:#666;font-size:12px">{escape(t(locale, "invite.fallback"))}'
        f"<br>{escape(accept_url)}</p>"
        f'<p style="color:#666;font-size:12px">{escape(t(locale, "invite.ignore"))}</p>'
    )
    try:
        await send_email(to=to, subject=t(locale, "invite.subject"), text=text, html=html)
        return True
    except Exception:
        logger.exception("Failed to send invitation email to %s", to)
        return False
