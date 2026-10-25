"""Render and send one digest to one target."""

from dataclasses import dataclass
from html import escape

import httpx

from app.core.config import settings
from app.models.package import SEVERITY_RANK, Package, Severity, VulnMatch
from app.models.project import Project
from app.services.mailer import send_email

MAX_LINES = 25
EMOJI = {"CRITICAL": "🟥", "HIGH": "🟧", "MEDIUM": "🟨", "LOW": "🟦", "UNKNOWN": "⬜"}


@dataclass(frozen=True)
class Item:
    match: VulnMatch
    package: Package
    project: Project


def _sorted(items: list[Item]) -> list[Item]:
    return sorted(
        items,
        key=lambda i: (
            -SEVERITY_RANK.get(Severity(i.match.severity), 0),
            i.project.name,
            i.package.name,
        ),
    )


def vuln_url(vuln_id: str) -> str:
    return f"https://osv.dev/vulnerability/{vuln_id}"


def _line(i: Item) -> str:
    m, p = i.match, i.package
    fixed = f" → {m.fixed_version}" if m.fixed_version else ""
    summary = f" — {m.summary}" if m.summary else ""
    return (
        f"{EMOJI.get(m.severity, '')} [{m.severity}] {i.project.name}: "
        f"{p.name}@{p.version}{fixed} {m.vuln_id}{summary}"
    )


def _title(items: list[Item]) -> str:
    return f"[Vectana] 新しい脆弱性が {len(items)} 件見つかりました"


def render_text(items: list[Item], link_style: str = "plain") -> str:
    ordered = _sorted(items)
    lines = []
    for i in ordered[:MAX_LINES]:
        line = _line(i)
        url = vuln_url(i.match.vuln_id)
        if link_style == "slack":
            line = line.replace(i.match.vuln_id, f"<{url}|{i.match.vuln_id}>")
        elif link_style == "discord":
            line = line.replace(i.match.vuln_id, f"[{i.match.vuln_id}](<{url}>)")
        lines.append(line)
    if len(ordered) > MAX_LINES:
        lines.append(f"…ほか {len(ordered) - MAX_LINES} 件")
    lines.append(f"ダッシュボード: {settings.web_url.rstrip('/')}/")
    return "\n".join(lines)


def render_html(items: list[Item]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(i.match.severity)}</td>"
        f"<td>{escape(i.project.name)}</td>"
        f"<td>{escape(i.package.ecosystem)} "
        f"{escape(i.package.name)}@{escape(i.package.version)}</td>"
        f"<td>{escape(i.match.fixed_version or '-')}</td>"
        f'<td><a href="{vuln_url(i.match.vuln_id)}">{escape(i.match.vuln_id)}</a><br>'
        f"<small>{escape(i.match.summary or '')}</small></td>"
        "</tr>"
        for i in _sorted(items)
    )
    return (
        f"<p>{escape(_title(items))}</p>"
        '<table border="1" cellpadding="6" style="border-collapse:collapse;font-size:13px">'
        "<tr><th>重大度</th><th>プロジェクト</th><th>パッケージ</th><th>修正版</th><th>脆弱性</th></tr>"
        f"{rows}</table>"
        f'<p><a href="{settings.web_url.rstrip("/")}/">Vectana を開く</a></p>'
    )


async def _post(url: str, payload: dict[str, object]) -> None:
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        response = await client.post(url, json=payload)
    response.raise_for_status()


async def send(channel: str, address: str, items: list[Item]) -> None:
    if channel == "email":
        await send_email(
            to=address,
            subject=_title(items),
            text=render_text(items),
            html=render_html(items),
        )
    elif channel == "discord":
        content = f"**{_title(items)}**\n{render_text(items, 'discord')}"
        await _post(address, {"content": content[:1990], "allowed_mentions": {"parse": []}})
    elif channel == "slack":
        await _post(address, {"text": f"*{_title(items)}*\n{render_text(items, 'slack')}"})
    else:
        raise ValueError(f"Unknown channel {channel!r}")


async def send_test(channel: str, address: str) -> None:
    text = "Vectana からのテスト通知です。この通知が届いていれば設定は正しく動いています。"
    if channel == "email":
        await send_email(to=address, subject="[Vectana] テスト通知", text=text)
    elif channel == "discord":
        await _post(address, {"content": text})
    elif channel == "slack":
        await _post(address, {"text": text})
