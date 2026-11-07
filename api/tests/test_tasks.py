"""Tasks, security task automation, sprints, burndown and velocity."""

from datetime import date, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import utcnow
from app.models.eol import EolFinding, EolStatus, Runtime
from app.models.package import Package, VulnMatch
from app.models.task import Task
from app.services import tasks as security_tasks
from tests.conftest import Org, auth, make_project


async def add_vuln(
    session: AsyncSession,
    project_id: str,
    name: str,
    vuln_id: str,
    severity: str,
    version: str = "1.0.0",
    fixed: str | None = None,
) -> VulnMatch:
    pkg = (
        await session.exec(
            select(Package).where(
                Package.project_id == UUID(project_id),
                Package.name == name,
                Package.version == version,
            )
        )
    ).first()
    if pkg is None:
        pkg = Package(project_id=UUID(project_id), ecosystem="npm", name=name, version=version)
        session.add(pkg)
        await session.flush()
    match = VulnMatch(package_id=pkg.id, vuln_id=vuln_id, severity=severity, fixed_version=fixed)
    session.add(match)
    await session.commit()
    return match


@pytest.fixture
async def project(client: AsyncClient, org: Org) -> str:
    """Project with member (write) and bp (viewer)."""
    p = await make_project(client, org.group_admin, "app", org.dev1.id)
    for user, role in ((org.member, "member"), (org.bp, "viewer")):
        r = await client.post(
            f"/api/projects/{p['id']}/members",
            json={"user_id": str(user.id), "role": role},
            headers=auth(org.group_admin),
        )
        assert r.status_code == 201
    return str(p["id"])


async def test_create_update_and_list(client: AsyncClient, org: Org, project: str) -> None:
    h = auth(org.member)
    r = await client.post(
        f"/api/projects/{project}/tasks",
        json={"title": " 設計 ", "start_date": "2026-11-01", "due_date": "2026-11-10"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    phase = r.json()
    assert phase["title"] == "設計" and phase["number"] == 1 and phase["kind"] == "development"

    r = await client.post(
        f"/api/projects/{project}/tasks",
        json={
            "title": "画面設計",
            "parent_id": phase["id"],
            "depends_on": [phase["id"]],
            "assignee_id": str(org.member.id),
            "due_date": "2000-01-01",
        },
        headers=h,
    )
    child = r.json()
    assert child["number"] == 2 and child["overdue"] is True

    # Viewer reads but cannot write.
    r = await client.get(f"/api/projects/{project}/tasks", headers=auth(org.bp))
    assert [t["number"] for t in r.json()] == [1, 2]
    r = await client.post(
        f"/api/projects/{project}/tasks", json={"title": "x"}, headers=auth(org.bp)
    )
    assert r.status_code == 403

    # Done sets completed_at and progress; reopening clears it.
    r = await client.patch(f"/api/tasks/{child['id']}", json={"status": "done"}, headers=h)
    body = r.json()
    assert body["completed_at"] and body["progress"] == 100 and body["overdue"] is False
    r = await client.patch(f"/api/tasks/{child['id']}", json={"status": "in_progress"}, headers=h)
    assert r.json()["completed_at"] is None

    # My tasks across projects.
    r = await client.get("/api/tasks?scope=mine", headers=h)
    assert [t["id"] for t in r.json()] == [child["id"]]
    r = await client.get("/api/tasks?scope=unassigned", headers=h)
    assert [t["id"] for t in r.json()] == [phase["id"]]

    # Deleting the phase detaches its child and dependency.
    r = await client.delete(f"/api/tasks/{phase['id']}", headers=h)
    assert r.status_code == 204
    r = await client.get(f"/api/tasks/{child['id']}", headers=h)
    assert r.json()["parent_id"] is None and r.json()["depends_on"] == []


async def test_reference_checks(client: AsyncClient, org: Org, project: str) -> None:
    h = auth(org.member)
    a = (await client.post(f"/api/projects/{project}/tasks", json={"title": "a"}, headers=h)).json()
    b = (
        await client.post(
            f"/api/projects/{project}/tasks", json={"title": "b", "parent_id": a["id"]}, headers=h
        )
    ).json()
    r = await client.patch(f"/api/tasks/{a['id']}", json={"parent_id": b["id"]}, headers=h)
    assert r.status_code == 422  # cycle
    r = await client.patch(f"/api/tasks/{a['id']}", json={"depends_on": [a["id"]]}, headers=h)
    assert r.status_code == 422
    r = await client.patch(
        f"/api/tasks/{a['id']}",
        json={"start_date": "2026-11-10", "due_date": "2026-11-01"},
        headers=h,
    )
    assert r.status_code == 422
    # Assignee must be able to work on the project.
    r = await client.patch(f"/api/tasks/{a['id']}", json={"assignee_id": str(org.bp.id)}, headers=h)
    assert r.status_code == 422
    other = await make_project(client, org.group_admin, "other")
    r = await client.post(
        f"/api/projects/{other['id']}/tasks",
        json={"title": "x", "parent_id": a["id"]},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 422


async def test_hidden_project_tasks_are_404(client: AsyncClient, org: Org, project: str) -> None:
    t = (
        await client.post(
            f"/api/projects/{project}/tasks", json={"title": "a"}, headers=auth(org.member)
        )
    ).json()
    r = await client.get(f"/api/tasks/{t['id']}", headers=auth(org.affiliate_admin))
    assert r.status_code == 404
    r = await client.get("/api/tasks?scope=team", headers=auth(org.affiliate_admin))
    assert r.json() == []


async def test_security_tasks_are_created_linked_and_completed(
    client: AsyncClient, session: AsyncSession, org: Org, project: str
) -> None:
    high = await add_vuln(session, project, "lodash", "GHSA-1", "HIGH", fixed="1.0.5")
    low = await add_vuln(session, project, "lodash", "GHSA-2", "LOW", fixed="1.2.0")
    medium = await add_vuln(session, project, "axios", "GHSA-3", "MEDIUM", fixed="2.0.0")

    assert await security_tasks.sync(session, [UUID(project)]) == 1
    h = auth(org.member)
    tasks = (await client.get(f"/api/projects/{project}/tasks", headers=h)).json()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["kind"] == "security" and task["title"] == "lodash" and task["auto_created"]
    sec = task["security"]
    assert sec["vuln_count"] == 2 and sec["max_severity"] == "HIGH"
    assert sec["upgrade"]["version"] == "1.2.0" and sec["installed"] == ["1.0.0"]
    # Due as the earliest SLA (HIGH = 30 days) when the task has none.
    assert task["effective_due"] == (utcnow().date() + timedelta(days=30)).isoformat()

    # The match carries its task; MEDIUM axios waits as a candidate.
    r = await client.get(f"/api/vulnerabilities?project_id={project}", headers=h)
    by_vuln = {m["vuln_id"]: m["task_id"] for m in r.json()}
    assert by_vuln == {"GHSA-1": task["id"], "GHSA-2": task["id"], "GHSA-3": None}
    r = await client.get(f"/api/projects/{project}/security/candidates", headers=h)
    assert [(c["name"], c["vuln_count"], c["max_severity"]) for c in r.json()] == [
        ("axios", 1, "MEDIUM")
    ]

    # タスク化
    r = await client.post(
        f"/api/projects/{project}/security/tasks",
        json={"subject": "package", "ecosystem": "npm", "name": "axios"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    axios = r.json()
    assert not axios["auto_created"] and [m["vuln_id"] for m in axios["matches"]] == ["GHSA-3"]
    r = await client.get(f"/api/projects/{project}/security/candidates", headers=h)
    assert r.json() == []
    r = await client.post(
        f"/api/projects/{project}/security/tasks",
        json={"subject": "package", "ecosystem": "npm", "name": "axios"},
        headers=h,
    )
    assert r.status_code == 404

    # A new lodash advisory joins the open task instead of creating another.
    await add_vuln(session, project, "lodash", "GHSA-4", "CRITICAL")
    assert await security_tasks.sync(session, [UUID(project)]) == 0
    detail = (await client.get(f"/api/tasks/{task['id']}", headers=h)).json()
    assert len(detail["matches"]) == 3

    # Ignoring the vulnerability through triage completes the axios task.
    r = await client.patch(
        f"/api/vulnerabilities/{medium.id}", json={"status": "ignored"}, headers=h
    )
    assert r.status_code == 200
    r = await client.get(f"/api/tasks/{axios['id']}", headers=h)
    assert r.json()["status"] == "done"

    # Upgrading lodash (the old package is removed) completes its task.
    pkg = await session.get(Package, high.package_id)
    assert pkg is not None and low.package_id == pkg.id
    r = await client.delete(f"/api/projects/{project}/packages/{pkg.id}", headers=h)
    assert r.status_code == 204
    r = await client.get(f"/api/tasks/{task['id']}", headers=h)
    assert r.json()["status"] == "done" and r.json()["completed_at"]


async def test_threshold_and_eol(
    client: AsyncClient, session: AsyncSession, org: Org, project: str
) -> None:
    pid = UUID(project)
    await add_vuln(session, project, "axios", "GHSA-3", "MEDIUM")
    rt = Runtime(project_id=pid, product="python", version="3.8")
    session.add(rt)
    await session.flush()
    session.add(
        EolFinding(
            project_id=pid,
            runtime_id=rt.id,
            product="python",
            product_label="Python",
            version="3.8",
            cycle="3.8",
            eol_date=date(2024, 10, 7),
            latest="3.8.20",
            status=EolStatus.eol,
        )
    )
    await session.commit()
    assert await security_tasks.sync(session, [pid]) == 1
    h = auth(org.member)
    tasks = (await client.get(f"/api/projects/{project}/tasks", headers=h)).json()
    assert [(t["title"], t["security"]["eol_status"], t["overdue"]) for t in tasks] == [
        ("Python", "eol", True)
    ]

    # Lowering the threshold (managers only) picks up the MEDIUM advisory.
    r = await client.patch(
        f"/api/projects/{project}", json={"security_threshold": "MEDIUM"}, headers=h
    )
    assert r.status_code == 403
    r = await client.patch(
        f"/api/projects/{project}",
        json={"security_threshold": "MEDIUM"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 200 and r.json()["security_threshold"] == "MEDIUM"
    tasks = (await client.get(f"/api/projects/{project}/tasks", headers=h)).json()
    assert sorted(t["title"] for t in tasks) == ["Python", "axios"]

    # Deleting a task returns its items to the candidates.
    python = next(t for t in tasks if t["title"] == "Python")
    r = await client.delete(f"/api/tasks/{python['id']}", headers=h)
    assert r.status_code == 204
    finding = (await session.exec(select(EolFinding))).one()
    await session.refresh(finding)
    assert finding.task_id is None


async def test_sprints_burndown_and_velocity(
    client: AsyncClient, session: AsyncSession, org: Org, project: str
) -> None:
    h = auth(org.member)
    start = utcnow().date() - timedelta(days=2)
    r = await client.post(
        f"/api/projects/{project}/sprints",
        json={
            "name": "Sprint 1",
            "starts_on": start.isoformat(),
            "ends_on": (start + timedelta(days=4)).isoformat(),
            "status": "active",
            "definition_of_done": [{"text": "レビュー済み"}],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    sprint = r.json()
    assert sprint["definition_of_done"] == [{"text": "レビュー済み", "done": False}]
    r = await client.post(
        f"/api/projects/{project}/sprints",
        json={
            "name": "Sprint 2",
            "starts_on": start.isoformat(),
            "ends_on": start.isoformat(),
            "status": "active",
        },
        headers=h,
    )
    assert r.status_code == 409  # one active sprint at a time

    ids = []
    for title, points in (("a", 3), ("b", 5), ("c", 2)):
        r = await client.post(
            f"/api/projects/{project}/tasks",
            json={"title": title, "sprint_id": sprint["id"], "points": points},
            headers=h,
        )
        ids.append(r.json()["id"])
    await client.patch(f"/api/tasks/{ids[0]}", json={"status": "done"}, headers=h)
    # Completed yesterday.
    t = await session.get(Task, UUID(ids[1]))
    assert t is not None
    t.status = "done"
    t.completed_at = utcnow() - timedelta(days=1)
    session.add(t)
    await session.commit()

    r = await client.get(f"/api/sprints/{sprint['id']}/burndown", headers=auth(org.bp))
    bd = r.json()
    assert bd["unit"] == "points" and bd["total"] == 10
    assert [p["remaining"] for p in bd["points"]] == [10, 5, 2, None, None]
    assert bd["points"][0]["ideal"] == 10 and bd["points"][-1]["ideal"] == 0

    # Closing freezes the commitment and sends unfinished work to the backlog.
    r = await client.patch(f"/api/sprints/{sprint['id']}", json={"status": "closed"}, headers=h)
    assert r.json()["task_count"] == 2
    r = await client.get(f"/api/projects/{project}/tasks?sprint_id=none", headers=h)
    assert [t["title"] for t in r.json()] == ["c"]
    r = await client.get(f"/api/projects/{project}/velocity", headers=h)
    assert [(v["name"], v["committed"], v["completed"]) for v in r.json()] == [("Sprint 1", 10, 8)]
