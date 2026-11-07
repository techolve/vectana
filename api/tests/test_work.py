"""Timesheet, estimate vs actual, activity notes and invoices."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models.base import utcnow
from app.models.user import User
from tests.conftest import Org, auth, make_project

WEEK = "2026-11-04"  # a Wednesday; the week starts on 2026-11-02


@pytest.fixture
async def project(client: AsyncClient, org: Org) -> str:
    """Project in 第1開発部 with member (write) and bp (member)."""
    p = await make_project(client, org.company_admin, "物流", org.dev1.id)
    for user in (org.member, org.bp):
        r = await client.post(
            f"/api/projects/{p['id']}/members",
            json={"user_id": str(user.id), "role": "member"},
            headers=auth(org.company_admin),
        )
        assert r.status_code == 201, r.text
    return str(p["id"])


async def _task(client: AsyncClient, user: User, project: str, title: str, **extra: object) -> dict:  # type: ignore[type-arg]
    r = await client.post(
        f"/api/projects/{project}/tasks", json={"title": title, **extra}, headers=auth(user)
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _hours(*values: float | None) -> list[float | None]:
    return [*values, *([None] * (7 - len(values)))]


async def test_timesheet_week(client: AsyncClient, org: Org, project: str) -> None:
    h = {**auth(org.member), "Accept-Language": "en"}
    task = await _task(client, org.member, project, "画面設計", estimate_hours=16)

    r = await client.get(f"/api/timesheet?week={WEEK}", headers=h)
    assert r.status_code == 200
    sheet = r.json()
    assert sheet["week_start"] == "2026-11-02" and sheet["rows"] == [] and sheet["can_edit"]

    body = {
        "week_start": WEEK,
        "rows": [
            {"task_id": task["id"], "hours": _hours(4, 6)},
            {"project_id": project, "hours": _hours(2)},
            {"label": " 社内会議 ", "hours": _hours(None, 1)},
        ],
    }
    r = await client.put("/api/timesheet", json=body, headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert [row["hours"][:2] for row in rows] == [[4, 6], [2, None], [None, 1]]
    assert rows[0]["project_id"] == project and rows[0]["task_number"] == 1
    assert rows[0]["estimate_hours"] == 16 and rows[0]["actual_hours"] == 10
    assert rows[2]["label"] == "社内会議" and rows[2]["project_id"] is None

    # Saving again replaces the week.
    body["rows"] = body["rows"][:1]
    r = await client.put("/api/timesheet", json=body, headers=h)
    assert len(r.json()["rows"]) == 1

    # Validation.
    for rows_, msg in (
        ([{"label": "a", "hours": _hours(20)}, {"label": "b", "hours": _hours(5)}], "24"),
        ([{"label": "a", "hours": _hours(1)}, {"label": "a", "hours": _hours(1)}], "twice"),
        ([{"hours": _hours(1)}], "needs"),
    ):
        r = await client.put("/api/timesheet", json={"week_start": WEEK, "rows": rows_}, headers=h)
        assert r.status_code == 422 and msg in r.json()["detail"], r.text
    # A project the person cannot see.
    other = await make_project(client, org.affiliate_admin, "他社")
    r = await client.put(
        "/api/timesheet",
        json={"week_start": WEEK, "rows": [{"project_id": other["id"], "hours": _hours(1)}]},
        headers=h,
    )
    assert r.status_code == 422

    # Submit and undo.
    r = await client.post(f"/api/timesheet/submit?week={WEEK}", headers=h)
    assert r.json()["submitted_at"] is not None
    r = await client.delete(f"/api/timesheet/submit?week={WEEK}", headers=h)
    assert r.json()["submitted_at"] is None


async def test_timesheet_permissions(client: AsyncClient, org: Org, project: str) -> None:
    uid = org.member.id
    await client.put(
        "/api/timesheet",
        json={"week_start": WEEK, "rows": [{"project_id": project, "hours": _hours(8)}]},
        headers=auth(org.member),
    )
    # Department head reads but cannot edit; the company admin can do both.
    r = await client.get(f"/api/timesheet?week={WEEK}&user_id={uid}", headers=auth(org.head))
    assert r.status_code == 200 and not r.json()["can_edit"]
    assert r.json()["rows"][0]["hours"][0] == 8
    r = await client.post(
        f"/api/timesheet/submit?week={WEEK}&user_id={uid}", headers=auth(org.head)
    )
    assert r.status_code == 403
    r = await client.get(
        f"/api/timesheet?week={WEEK}&user_id={uid}", headers=auth(org.company_admin)
    )
    assert r.json()["can_edit"]
    r = await client.put(
        "/api/timesheet",
        json={"week_start": WEEK, "user_id": str(uid), "rows": []},
        headers=auth(org.company_admin),
    )
    assert r.status_code == 200 and r.json()["rows"] == []
    # Others cannot see it.
    for user in (org.seller, org.affiliate_admin, org.bp):
        r = await client.get(f"/api/timesheet?week={WEEK}&user_id={uid}", headers=auth(user))
        assert r.status_code == 403, user.email


async def test_actuals(client: AsyncClient, org: Org, project: str) -> None:
    r = await client.post(
        f"/api/projects/{project}/estimates",
        json={
            "title": "初回開発",
            "amount": 1_000_000,
            "status": "won",
            "lines": [{"label": "開発", "days": 10, "unit_cost": 40000}],
        },
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201, r.text
    phase = await _task(client, org.member, project, "設計")
    child = await _task(
        client, org.member, project, "画面設計", parent_id=phase["id"], estimate_hours=24
    )
    await client.put(
        "/api/timesheet",
        json={
            "week_start": WEEK,
            "rows": [
                {"task_id": child["id"], "hours": _hours(8, 8)},
                {"project_id": project, "hours": _hours(None, None, 4)},
            ],
        },
        headers=auth(org.member),
    )
    r = await client.get(f"/api/projects/{project}/actuals", headers=auth(org.company_admin))
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["estimate_days"] == 10 and a["estimate_amount"] == 1_000_000
    assert a["actual_hours"] == 20 and a["actual_days"] == 2.5
    phases = {p["title"]: p for p in a["phases"]}
    assert phases["設計"]["estimate_days"] == 3 and phases["設計"]["actual_days"] == 2
    assert phases[None]["actual_days"] == 0.5
    assert a["people"][0]["actual_days"] == 2.5
    assert a["actual_cost"] is not None  # admins see costs

    r = await client.get(f"/api/projects/{project}/actuals", headers=auth(org.member))
    assert r.status_code == 200 and r.json()["actual_cost"] is None
    r = await client.get(f"/api/projects/{project}/actuals", headers=auth(org.bp))
    assert r.status_code == 403


async def test_activity_next_action_becomes_task(
    client: AsyncClient, org: Org, project: str
) -> None:
    r = await client.post(
        f"/api/projects/{project}/activities",
        json={
            "kind": "meeting",
            "occurred_on": "2026-11-05",
            "participants": "先方 山田様",
            "body": "要件の確認",
            "next_action": "見積を再提出",
            "next_action_assignee_id": str(org.member.id),
            "next_action_due": "2000-01-01",
        },
        headers=auth(org.company_admin),
    )
    assert r.status_code == 201, r.text
    act = r.json()
    assert act["task"]["title"] == "見積を再提出" and act["task"]["overdue"] is True
    assert act["task"]["assignee"]["id"] == str(org.member.id)

    # It is the member's task and the project's next action.
    mine = (await client.get("/api/tasks?scope=mine", headers=auth(org.member))).json()
    assert [t["title"] for t in mine] == ["見積を再提出"]
    p = (await client.get(f"/api/projects/{project}", headers=auth(org.company_admin))).json()
    assert p["next_action"] == "見積を再提出" and p["next_action_on"] == "2000-01-01"

    # Completing the task shows on the note.
    await client.patch(
        f"/api/tasks/{act['task']['id']}", json={"status": "done"}, headers=auth(org.member)
    )
    rows = (
        await client.get(f"/api/projects/{project}/activities", headers=auth(org.member))
    ).json()
    assert rows[0]["task"]["status"] == "done" and rows[0]["task"]["overdue"] is False

    # Members with write access add notes; partners never see them.
    r = await client.post(
        f"/api/projects/{project}/activities",
        json={"kind": "phone", "occurred_on": "2026-11-06", "body": "電話"},
        headers=auth(org.member),
    )
    assert r.status_code == 201 and r.json()["task"] is None
    r = await client.get(f"/api/projects/{project}/activities", headers=auth(org.bp))
    assert r.status_code == 403
    rows = (
        await client.get(f"/api/projects/{project}/activities", headers=auth(org.member))
    ).json()
    assert [x["kind"] for x in rows] == ["phone", "meeting"]

    # Assignee must be able to work on the project.
    r = await client.post(
        f"/api/projects/{project}/activities",
        json={
            "occurred_on": "2026-11-06",
            "body": "x",
            "next_action": "y",
            "next_action_assignee_id": str(org.affiliate_admin.id),
        },
        headers=auth(org.company_admin),
    )
    assert r.status_code == 422

    r = await client.patch(
        f"/api/activities/{act['id']}",
        json={"body": "要件の確認（修正）"},
        headers=auth(org.member),
    )
    assert r.json()["body"] == "要件の確認（修正）"
    r = await client.delete(f"/api/activities/{act['id']}", headers=auth(org.member))
    assert r.status_code == 204
    r = await client.get(f"/api/tasks/{act['task']['id']}", headers=auth(org.member))
    assert r.status_code == 200  # the task stays


async def test_invoices(client: AsyncClient, org: Org, project: str) -> None:
    est = (
        await client.post(
            f"/api/projects/{project}/estimates",
            json={"title": "初回開発", "amount": 1_000_000, "status": "submitted"},
            headers=auth(org.company_admin),
        )
    ).json()
    plan = {
        "items": [
            {"label": "納品時", "planned_on": "2027-01-31", "amount": 700_000},
            {"label": "着手金", "planned_on": "2026-11-30", "amount": 300_000},
        ]
    }
    url = f"/api/estimates/{est['id']}/invoices"
    r = await client.put(url, json=plan, headers=auth(org.company_admin))
    assert r.status_code == 422  # not won yet
    await client.patch(
        f"/api/estimates/{est['id']}", json={"status": "won"}, headers=auth(org.company_admin)
    )
    r = await client.put(url, json=plan, headers=auth(org.member))
    assert r.status_code == 403
    r = await client.put(url, json=plan, headers=auth(org.seller))
    assert r.status_code == 200, r.text
    inv = r.json()
    assert [(i["seq"], i["label"], i["count"]) for i in inv] == [
        (1, "着手金", 2),
        (2, "納品時", 2),
    ]
    first = inv[0]["id"]

    # Sales cannot record; accounting can. Due defaults to the end of next month.
    r = await client.patch(
        f"/api/invoices/{first}", json={"status": "invoiced"}, headers=auth(org.seller)
    )
    assert r.status_code == 403
    r = await client.patch(
        f"/api/invoices/{first}",
        json={"status": "invoiced", "invoiced_on": "2026-11-30"},
        headers=auth(org.accounting),
    )
    assert r.status_code == 200, r.text
    assert r.json()["due_on"] == "2026-12-31" and r.json()["can_record"]
    # Invoiced ones can no longer be changed by sales.
    r = await client.patch(f"/api/invoices/{first}", json={"amount": 1}, headers=auth(org.seller))
    assert r.status_code == 409

    # Re-planning keeps the invoiced one and replaces the rest.
    r = await client.put(
        url,
        json={
            "items": [
                {"label": "中間", "planned_on": "2026-12-31", "amount": 300_000},
                {"label": "納品時", "planned_on": "2027-01-31", "amount": 400_000},
            ]
        },
        headers=auth(org.seller),
    )
    assert [(i["seq"], i["label"], i["status"]) for i in r.json()] == [
        (1, "着手金", "invoiced"),
        (2, "中間", "planned"),
        (3, "納品時", "planned"),
    ]

    # Overdue once past due; paying clears it.
    past = (utcnow().date() - timedelta(days=40)).isoformat()
    r = await client.patch(
        f"/api/invoices/{first}",
        json={
            "invoiced_on": past,
            "due_on": (date.fromisoformat(past) + timedelta(days=30)).isoformat(),
        },
        headers=auth(org.accounting),
    )
    assert r.json()["overdue"] is True
    r = await client.get("/api/invoices?status=overdue", headers=auth(org.accounting))
    assert [i["id"] for i in r.json()] == [first]
    r = await client.get("/api/invoices?month=2026-12", headers=auth(org.accounting))
    assert {i["label"] for i in r.json()} == {"着手金", "中間"}  # overdue stays visible
    r = await client.get(
        "/api/invoices.csv?status=overdue",
        headers={**auth(org.accounting), "Accept-Language": "ja"},
    )
    assert r.text.startswith("﻿請求予定日,") and "入金遅れ" in r.text
    r = await client.patch(
        f"/api/invoices/{first}", json={"status": "paid"}, headers=auth(org.accounting)
    )
    assert r.json()["paid_on"] is not None and r.json()["overdue"] is False

    # Who sees what.
    for user in (org.seller, org.member):
        r = await client.get("/api/invoices", headers=auth(user))
        assert r.status_code == 403, user.email
    r = await client.get("/api/invoices", headers=auth(org.affiliate_admin))
    assert r.json() == []
    r = await client.get(f"/api/projects/{project}/invoices", headers=auth(org.member))
    assert r.status_code == 200 and not r.json()[0]["can_record"]
    r = await client.get(f"/api/projects/{project}/invoices", headers=auth(org.bp))
    assert r.status_code == 403
