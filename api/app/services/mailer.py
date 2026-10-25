"""Outbound email.

The backend is chosen by ``MAIL_BACKEND``:
- ``smtp``: any SMTP relay (Mailpit locally, Resend / other relays in production)
- ``cloudflare``: Cloudflare Email Service REST API
- ``none``: log and drop (useful before mail is set up)

``send_email`` raises on failure so callers decide whether to surface or retry.
"""

import logging
from email.message import EmailMessage
from email.utils import parseaddr

import aiosmtplib
import httpx

from app.core.config import settings

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


async def _send_smtp(to: str, subject: str, text: str, html: str | None) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    if html is not None:
        message.add_alternative(html, subtype="html")

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


async def send_invitation_email(*, to: str, company_name: str, accept_url: str) -> bool:
    """Never raises; returns True if the email was sent."""
    subject = "[Vectana] アカウント招待"
    text = (
        f"{company_name} のメンバーとして Vectana に招待されました。\n\n"
        f"次のリンクからパスワードを設定してください:\n{accept_url}\n\n"
        f"リンクの有効期限は {settings.invitation_expire_days} 日です。"
        "心当たりがない場合はこのメールを無視してください。"
    )
    html = (
        f"<p><strong>{company_name}</strong> のメンバーとして Vectana に招待されました。</p>"
        f'<p><a href="{accept_url}">パスワードを設定する</a></p>'
        f'<p style="color:#666;font-size:12px">リンクが開けない場合は次のURLを'
        f"ブラウザに貼り付けてください:<br>{accept_url}</p>"
    )
    try:
        await send_email(to=to, subject=subject, text=text, html=html)
        return True
    except Exception:
        logger.exception("Failed to send invitation email to %s", to)
        return False
