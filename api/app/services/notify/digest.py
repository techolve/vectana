"""Render and send one digest (new vulnerabilities + EOL changes) to one target."""

from dataclasses import dataclass, field
from html import escape

import httpx

from app.core.config import settings
from app.i18n import t
from app.models.eol import EolFinding
from app.models.package import SEVERITY_RANK, Package, Severity, VulnMatch
from app.models.project import Project
from app.services.mailer import send_email

MAX_LINES = 25
EMOJI = {"CRITICAL": "🟥", "HIGH": "🟧", "MEDIUM": "🟨", "LOW": "🟦", "UNKNOWN": "⬜"}
EOL_EMOJI = {"eol": "⛔", "approaching": "⏳"}


@dataclass(frozen=True)
class Item:
    match: VulnMatch
    package: Package
    project: Project


@dataclass(frozen=True)
class EolItem:
    finding: EolFinding
    project: Project


@dataclass
class Digest:
    vulns: list[Item] = field(default_factory=list)
    eol: list[EolItem] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.vulns) + len(self.eol)


def _sorted_vulns(items: list[Item]) -> list[Item]:
    return sorted(
        items,
        key=lambda i: (
            -SEVERITY_RANK.get(Severity(i.match.severity), 0),
            i.project.name,
            i.package.name,
        ),
    )


def _sorted_eol(items: list[EolItem]) -> list[EolItem]:
    return sorted(
        items, key=lambda i: (i.finding.status != "eol", i.project.name, i.finding.product)
    )


def vuln_url(vuln_id: str) -> str:
    return f"https://osv.dev/vulnerability/{vuln_id}"


def eol_url(product: str) -> str:
    return f"https://endoflife.date/{product}"


def dashboard_url(locale: str) -> str:
    return f"{settings.web_url.rstrip('/')}/{locale}/"


def _vuln_line(i: Item, link_style: str) -> str:
    m, p = i.match, i.package
    fixed = f" → {m.fixed_version}" if m.fixed_version else ""
    summary = f" — {m.summary}" if m.summary else ""
    vid = m.vuln_id
    if link_style == "slack":
        vid = f"<{vuln_url(vid)}|{vid}>"
    elif link_style == "discord":
        vid = f"[{vid}](<{vuln_url(vid)}>)"
    head = f"{EMOJI.get(m.severity, '')} [{m.severity}] {i.project.name}"
    return f"{head}: {p.name}@{p.version}{fixed} {vid}{summary}"


def _eol_line(i: EolItem, locale: str, link_style: str) -> str:
    f = i.finding
    when = t(locale, f"eol.line.{f.status}", date=f.eol_date.isoformat() if f.eol_date else "-")
    label = f"{f.product_label} {f.cycle or f.version}"
    if link_style == "slack":
        label = f"<{eol_url(f.product)}|{label}>"
    elif link_style == "discord":
        label = f"[{label}](<{eol_url(f.product)}>)"
    latest = t(locale, "eol.latest", version=f.latest) if f.latest else ""
    return f"{EOL_EMOJI.get(f.status, '')} {i.project.name}: {label} — {when}{latest}"


def subject(d: Digest, locale: str) -> str:
    return t(locale, "digest.subject", count=d.count)


def render_text(d: Digest, locale: str, link_style: str = "plain") -> str:
    lines: list[str] = []
    if d.vulns:
        vulns = _sorted_vulns(d.vulns)
        lines.append(t(locale, "digest.vulns", count=len(vulns)))
        lines += [_vuln_line(i, link_style) for i in vulns[:MAX_LINES]]
        if len(vulns) > MAX_LINES:
            lines.append(t(locale, "digest.more", count=len(vulns) - MAX_LINES))
    if d.eol:
        if lines:
            lines.append("")
        eol = _sorted_eol(d.eol)
        lines.append(t(locale, "digest.eol", count=len(eol)))
        lines += [_eol_line(i, locale, link_style) for i in eol[:MAX_LINES]]
        if len(eol) > MAX_LINES:
            lines.append(t(locale, "digest.more", count=len(eol) - MAX_LINES))
    lines.append("")
    lines.append(f"{t(locale, 'digest.dashboard')}: {dashboard_url(locale)}")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (
        '<table border="1" cellpadding="6" style="border-collapse:collapse;font-size:13px">'
        f"<tr>{head}</tr>{body}</table>"
    )


def render_html(d: Digest, locale: str) -> str:
    parts = [f"<p>{escape(subject(d, locale))}</p>"]
    if d.vulns:
        parts.append(f"<h3>{escape(t(locale, 'digest.vulns', count=len(d.vulns)))}</h3>")
        rows = [
            [
                escape(i.match.severity),
                escape(i.project.name),
                f"{escape(i.package.ecosystem)} "
                f"{escape(i.package.name)}@{escape(i.package.version)}",
                escape(i.match.fixed_version or "-"),
                f'<a href="{vuln_url(i.match.vuln_id)}">{escape(i.match.vuln_id)}</a><br>'
                f"<small>{escape(i.match.summary or '')}</small>",
            ]
            for i in _sorted_vulns(d.vulns)
        ]
        cols = ["severity", "project", "package", "fixed", "vuln"]
        parts.append(_table([t(locale, f"digest.col.{c}") for c in cols], rows))
    if d.eol:
        parts.append(f"<h3>{escape(t(locale, 'digest.eol', count=len(d.eol)))}</h3>")
        rows = [
            [
                escape(t(locale, f"eol.status.{i.finding.status}")),
                escape(i.project.name),
                f'<a href="{eol_url(i.finding.product)}">{escape(i.finding.product_label)}</a> '
                f"{escape(i.finding.cycle or i.finding.version)}",
                escape(i.finding.eol_date.isoformat() if i.finding.eol_date else "-"),
            ]
            for i in _sorted_eol(d.eol)
        ]
        cols = ["status", "project", "product", "eol_date"]
        parts.append(_table([t(locale, f"digest.col.{c}") for c in cols], rows))
    parts.append(f'<p><a href="{dashboard_url(locale)}">{escape(t(locale, "digest.open"))}</a></p>')
    return "".join(parts)


async def _post(url: str, payload: dict[str, object]) -> None:
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        response = await client.post(url, json=payload)
    response.raise_for_status()


async def send(channel: str, address: str, digest: Digest, locale: str) -> None:
    title = subject(digest, locale)
    if channel == "email":
        await send_email(
            to=address,
            subject=title,
            text=render_text(digest, locale),
            html=render_html(digest, locale),
        )
    elif channel == "discord":
        content = f"**{title}**\n{render_text(digest, locale, 'discord')}"
        await _post(address, {"content": content[:1990], "allowed_mentions": {"parse": []}})
    elif channel == "slack":
        await _post(address, {"text": f"*{title}*\n{render_text(digest, locale, 'slack')}"})
    else:
        raise ValueError(f"Unknown channel {channel!r}")


async def send_test(channel: str, address: str, locale: str) -> None:
    text = t(locale, "test.body")
    if channel == "email":
        await send_email(to=address, subject=t(locale, "test.subject"), text=text)
    elif channel == "discord":
        await _post(address, {"content": text})
    elif channel == "slack":
        await _post(address, {"text": text})
