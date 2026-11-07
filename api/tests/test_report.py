"""Organization dashboard (per company/department), SLA overdue, CSV, weekly report."""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.eol import EolFinding
from app.models.notification import NotificationPref
from app.models.package import Package, VulnMatch
from app.services import report
from app.services.orgstats import due_date
from tests.conftest import Org, auth, make_project

NOW = datetime.now(UTC)
TODAY = NOW.date()


async def _vuln(
    session: AsyncSession,
    project_id: str,
    severity: str,
    days_ago: int,
    status: str = "open",
) -> None:
    pkg = Package(
        project_id=UUID(project_id),
        ecosystem="npm",
        name=f"pkg-{severity.lower()}-{days_ago}",
        version="1.0.0",
    )
    session.add(pkg)
    await session.flush()
    session.add(
        VulnMatch(
            package_id=pkg.id,
            vuln_id=f"GHSA-{severity}-{days_ago}",
            severity=severity,
            status=status,
            first_seen_at=NOW - timedelta(days=days_ago),
        )
    )
    await session.commit()


async def _eol(session: AsyncSession, project_id: str, eol_date: date, status: str) -> None:
    session.add(
        EolFinding(
            project_id=UUID(project_id),
            product="python",
            product_label="Python",
            version="3.10.4",
            cycle="3.10",
            eol_date=eol_date,
            status=status,
        )
    )
    await session.commit()


@pytest.fixture
async def data(client: AsyncClient, org: Org, session: AsyncSession) -> dict[str, Any]:
    a = await make_project(client, org.group_admin, "A", org.dev1.id)
    b = await make_project(client, org.group_admin, "B", org.sales.id)
    c = await make_project(client, org.group_admin, "C")
    d = await make_project(client, org.affiliate_admin, "D")
    # A (第1開発部): CRITICAL 3 days overdue; HIGH acknowledged within SLA; ignored LOW.
    await _vuln(session, a["id"], "CRITICAL", 10)
    await _vuln(session, a["id"], "HIGH", 29, status="ack")
    await _vuln(session, a["id"], "LOW", 400, status="ignored")
    # B (営業部): HIGH 1 day overdue; MEDIUM due today (not overdue yet); EOL passed 5 days ago.
    await _vuln(session, b["id"], "HIGH", 31)
    await _vuln(session, b["id"], "MEDIUM", 90)
    await _eol(session, b["id"], TODAY - timedelta(days=5), "eol")
    # C (no department): EOL in 20 days.
    await _eol(session, c["id"], TODAY + timedelta(days=20), "approaching")
    # D (affiliate): CRITICAL long overdue.
    await _vuln(session, d["id"], "CRITICAL", 100)
    return {"A": a, "B": b, "C": c, "D": d}


def _rows(body: dict[str, Any]) -> list[tuple[str, str, bool]]:
    return [(r["kind"], r["name"], r["complete"]) for r in body["rows"]]


def _by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["name"] or r["kind"]: r for r in body["rows"]}


def test_due_date_uses_severity_sla() -> None:
    sla = {"CRITICAL": 7, "HIGH": 30, "MEDIUM": 90, "LOW": 180, "UNKNOWN": 90}
    seen = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    assert due_date("CRITICAL", seen, sla) == date(2026, 11, 8)
    assert due_date("LOW", seen, sla) == date(2027, 4, 30)
    # Unknown severities fall back to the UNKNOWN deadline; naive timestamps are UTC.
    assert due_date("WHATEVER", seen.replace(tzinfo=None), sla) == date(2027, 1, 30)


async def test_group_admin_sees_every_unit(client: AsyncClient, org: Org, data: dict) -> None:  # type: ignore[type-arg]
    r = await client.get("/api/org-dashboard", headers=auth(org.group_admin))
    assert r.status_code == 200
    body = r.json()
    assert _rows(body) == [
        ("company", "親会社", True),
        ("department", "営業部", True),
        ("department", "開発本部", True),
        ("department", "第1開発部", True),
        ("unassigned", "", True),
        ("company", "関連会社", True),
    ]
    rows = _by_name(body)
    parent = rows["親会社"]
    assert parent["project_count"] == 3
    assert parent["overdue"] == 2
    assert parent["oldest_overdue_days"] == 3
    assert parent["open_counts"] == {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1, "LOW": 0, "UNKNOWN": 0}
    assert parent["eol_counts"] == {"eol": 1, "approaching": 1}
    assert parent["nearest_eol_days"] == -5
    # Sub-department rolls up into its parent.
    assert rows["開発本部"]["overdue"] == rows["第1開発部"]["overdue"] == 1
    assert rows["開発本部"]["depth"] == 1 and rows["第1開発部"]["depth"] == 2
    assert rows["営業部"]["overdue"] == 1
    assert rows["営業部"]["oldest_overdue_days"] == 1
    assert rows["unassigned"]["nearest_eol_days"] == 20
    assert rows["関連会社"]["oldest_overdue_days"] == 93

    totals = body["totals"]
    assert totals["kind"] == "total" and totals["complete"] is True
    assert totals["project_count"] == 4
    assert totals["overdue"] == 3
    # Overdue list: longest overdue first; ack counts, ignored and not-yet-due don't.
    assert [i["vuln_id"] for i in body["overdue"]] == [
        "GHSA-CRITICAL-100",
        "GHSA-CRITICAL-10",
        "GHSA-HIGH-31",
    ]
    assert [e["days_left"] for e in body["upcoming_eol"]] == [-5, 20]


async def test_explicit_due_date_wins_over_sla(
    client: AsyncClient,
    org: Org,
    session: AsyncSession,
    data: dict,  # type: ignore[type-arg]
) -> None:
    from sqlmodel import select

    matches = {m.vuln_id: m for m in (await session.exec(select(VulnMatch))).all()}
    # Past its SLA, but the team agreed on a later date: not overdue.
    matches["GHSA-HIGH-31"].due_date = TODAY + timedelta(days=14)
    # Within its SLA, but its own date has passed: overdue.
    matches["GHSA-MEDIUM-90"].due_date = TODAY - timedelta(days=2)
    session.add_all(matches.values())
    await session.commit()

    body = (await client.get("/api/org-dashboard", headers=auth(org.group_admin))).json()
    items = {i["vuln_id"]: i for i in body["overdue"]}
    assert "GHSA-HIGH-31" not in items
    assert items["GHSA-MEDIUM-90"]["due_date"] == (TODAY - timedelta(days=2)).isoformat()
    assert items["GHSA-MEDIUM-90"]["days_overdue"] == 2
    assert body["totals"]["overdue"] == 3


async def test_company_admin_sees_own_company(client: AsyncClient, org: Org, data: dict) -> None:  # type: ignore[type-arg]
    body = (await client.get("/api/org-dashboard", headers=auth(org.company_admin))).json()
    assert [n for _, n, _ in _rows(body)] == ["親会社", "営業部", "開発本部", "第1開発部", ""]
    assert body["totals"]["overdue"] == 2
    assert body["totals"]["complete"] is False
    assert all(i["project_name"] != "D" for i in body["overdue"])

    other = await client.get(
        "/api/org-dashboard",
        params={"company_id": str(org.affiliate.id)},
        headers=auth(org.company_admin),
    )
    assert other.json()["rows"] == []


async def test_department_head_sees_own_subtree(client: AsyncClient, org: Org, data: dict) -> None:  # type: ignore[type-arg]
    body = (await client.get("/api/org-dashboard", headers=auth(org.head))).json()
    # The company row only covers what the head can see, so it is marked partial.
    assert _rows(body) == [
        ("company", "親会社", False),
        ("department", "開発本部", True),
        ("department", "第1開発部", True),
    ]
    assert body["totals"]["overdue"] == 1
    assert body["upcoming_eol"] == []


async def test_assigned_member_gets_partial_rows(
    client: AsyncClient,
    org: Org,
    data: dict,  # type: ignore[type-arg]
) -> None:
    r = await client.post(
        f"/api/projects/{data['B']['id']}/members",
        json={"user_id": str(org.member.id), "role": "viewer"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 201
    body = (await client.get("/api/org-dashboard", headers=auth(org.member))).json()
    assert _rows(body) == [("company", "親会社", False), ("department", "営業部", False)]
    assert (await client.get("/api/org-dashboard", headers=auth(org.bp))).json()["rows"] == []


async def test_sla_settings_change_overdue(client: AsyncClient, org: Org, data: dict) -> None:  # type: ignore[type-arg]
    r = await client.put(
        "/api/settings", json={"sla_critical_days": 30}, headers=auth(org.company_admin)
    )
    assert r.status_code == 403
    r = await client.put(
        "/api/settings",
        json={"sla_critical_days": 30, "sla_high_days": 60},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 200
    assert r.json()["sla_critical_days"] == 30
    assert r.json()["eol_warning_days"] == 90  # untouched
    body = (await client.get("/api/org-dashboard", headers=auth(org.group_admin))).json()
    assert body["sla_days"]["CRITICAL"] == 30
    assert [i["vuln_id"] for i in body["overdue"]] == ["GHSA-CRITICAL-100"]


async def test_csv_export(client: AsyncClient, org: Org, data: dict) -> None:  # type: ignore[type-arg]
    r = await client.get(
        "/api/org-dashboard.csv",
        headers={**auth(org.company_admin), "Accept-Language": "ja"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.removeprefix("﻿"))))
    assert rows[0][:3] == ["会社", "部署", "プロジェクト数"]
    units = [(row[0], row[1]) for row in rows[1:]]
    assert units == [
        ("親会社", ""),
        ("親会社", "営業部"),
        ("親会社", "開発本部"),
        ("親会社", "開発本部 / 第1開発部"),
        ("親会社", "（部署未設定）"),
    ]
    en = await client.get(
        "/api/org-dashboard.csv", headers={**auth(org.head), "Accept-Language": "en"}
    )
    header, first = list(csv.reader(io.StringIO(en.content.decode("utf-8-sig"))))[:2]
    assert header[0] == "Company" and header[-1] == "Partial"
    assert first[-1] == "1"  # company row is partial for a department head


# --- Weekly report --------------------------------------------------------------

# 2026-11-09 is a Monday; 00:30 UTC = 09:30 in Tokyo.
MONDAY_MORNING = datetime(2026, 11, 9, 0, 30, tzinfo=UTC)


def test_period_and_schedule() -> None:
    assert report.period_of(MONDAY_MORNING) == "2026-W46"
    assert report.is_due(MONDAY_MORNING, 0)
    assert not report.is_due(MONDAY_MORNING, 1)
    # 08:30 in Tokyo is before REPORT_HOUR.
    assert not report.is_due(MONDAY_MORNING - timedelta(hours=1), 0)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    sent: list[dict[str, str]] = []

    async def fake_send(**kwargs: str) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(report, "send_email", fake_send)
    return sent


async def test_weekly_report_recipients_and_scope(
    session: AsyncSession,
    org: Org,
    data: dict,  # type: ignore[type-arg]
    outbox: list[dict[str, str]],
) -> None:
    org.affiliate_admin.locale = "en"
    session.add(org.affiliate_admin)
    session.add(NotificationPref(user_id=org.company_admin.id, email_enabled=False))
    await session.commit()

    # Not the configured weekday: nothing goes out.
    assert await report.send_weekly_reports(session, MONDAY_MORNING + timedelta(days=1)) == 0

    assert await report.send_weekly_reports(session, MONDAY_MORNING) == 3
    by_to = {m["to"]: m for m in outbox}
    # Members aren't recipients; the company admin opted out of email.
    assert set(by_to) == {"ga@example.com", "aa@example.com", "head@example.com"}
    # (Overdue counts are as of the report day, two days after the fixture's "now".)
    assert by_to["ga@example.com"]["subject"].startswith(
        "[Vectana] 週次レポート（2026-W46）期限超過"
    )
    assert "グループ全体" in by_to["ga@example.com"]["text"]
    # The head only gets their own subtree.
    head = by_to["head@example.com"]
    assert "第1開発部" in head["text"] and "営業部" not in head["text"]
    assert "GHSA-HIGH-31" not in head["html"]
    # Recipient's language.
    assert by_to["aa@example.com"]["subject"].startswith("[Vectana] Weekly report (2026-W46)")
    assert "/en/org/" in by_to["aa@example.com"]["text"]

    # Once per week, even if the worker runs again.
    assert await report.send_weekly_reports(session, MONDAY_MORNING + timedelta(hours=5)) == 0
    # Next week goes out again.
    assert await report.send_weekly_reports(session, MONDAY_MORNING + timedelta(days=7)) == 3


async def test_weekly_report_can_be_disabled_or_forced(
    client: AsyncClient,
    session: AsyncSession,
    org: Org,
    data: dict,  # type: ignore[type-arg]
    outbox: list[dict[str, str]],
) -> None:
    r = await client.put(
        "/api/settings", json={"report_enabled": False}, headers=auth(org.group_admin)
    )
    assert r.json()["report_enabled"] is False
    assert await report.send_weekly_reports(session, MONDAY_MORNING) == 0
    # A manual run (python -m app.worker --report) still sends.
    assert await report.send_weekly_reports(session, MONDAY_MORNING, force=True) == 4


async def test_overdue_matches_across_screens(
    client: AsyncClient,
    org: Org,
    session: AsyncSession,
    data: dict,  # type: ignore[type-arg]
) -> None:
    """The organization page, the vulnerabilities list and the dashboard count
    the same overdue items: own due date first, SLA otherwise."""
    from sqlmodel import select

    matches = {m.vuln_id: m for m in (await session.exec(select(VulnMatch))).all()}
    matches["GHSA-HIGH-31"].due_date = TODAY + timedelta(days=14)
    matches["GHSA-MEDIUM-90"].due_date = TODAY - timedelta(days=2)
    session.add_all(matches.values())
    await session.commit()

    for user in (org.group_admin, org.company_admin, org.head, org.affiliate_admin):
        h = auth(user)
        org_view = (await client.get("/api/org-dashboard", headers=h)).json()
        listed = (
            await client.get(
                "/api/vulnerabilities", params={"status": "", "overdue": "true"}, headers=h
            )
        ).json()
        dash = (await client.get("/api/dashboard", headers=h)).json()
        expected = {i["vuln_id"] for i in org_view["overdue"]}
        assert {m["vuln_id"] for m in listed} == expected, user.email
        assert dash["triage"]["overdue"] == org_view["totals"]["overdue"] == len(expected)

    listed = (
        await client.get(
            "/api/vulnerabilities", params={"status": ""}, headers=auth(org.group_admin)
        )
    ).json()
    by_id = {m["vuln_id"]: m for m in listed}
    # Without its own date, the SLA deadline is shown; with one, it isn't.
    crit = by_id["GHSA-CRITICAL-10"]
    assert crit["due_date"] is None
    assert crit["sla_due_date"] == (NOW - timedelta(days=3)).date().isoformat()
    assert by_id["GHSA-HIGH-31"]["sla_due_date"] is None
