"""GitHub / GitLab links: issues <-> tasks, milestones <-> sprints, webhooks and
dependency-file import. The providers are faked with an httpx.MockTransport."""

import hashlib
import hmac
import json
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.package import Package
from app.models.repo import RepoLink
from app.models.task import Sprint, Task
from app.models.user import User
from app.routers import repo as repo_router
from app.services.repo import client as repo_client
from tests.conftest import Org, auth, make_project
from tests.test_tasks import add_vuln

LOCK = json.dumps(
    {
        "name": "app",
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "app"},
            "node_modules/lodash": {"version": "4.17.20"},
        },
    }
).encode()


class FakeGitHub:
    """Enough of the GitHub REST API for the sync code."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.milestones: dict[int, dict[str, Any]] = {}
        self.files: dict[str, bytes] = {"package-lock.json": LOCK}
        self.hooks: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_hooks = False
        self.token_ok = True

    def _issue(self, n: int, body: dict[str, Any]) -> dict[str, Any]:
        ms = body.get("milestone")
        return {
            "number": n,
            "title": body.get("title", ""),
            "body": body.get("body"),
            "state": body.get("state", "open"),
            "html_url": f"https://github.com/o/r/issues/{n}",
            "labels": [{"name": lb} for lb in body.get("labels", [])],
            "assignees": [{"login": a} for a in body.get("assignees", [])],
            "milestone": self.milestones.get(ms) if ms else None,
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        self.calls.append((method, path))
        if not self.token_ok:
            return httpx.Response(401, json={"message": "Bad credentials"})
        data = json.loads(request.content) if request.content else {}
        if path == "/repos/o/r":
            return httpx.Response(200, json={"default_branch": "main"})
        if path == "/repos/o/r/hooks" and method == "POST":
            if self.fail_hooks:
                return httpx.Response(404, json={"message": "Not Found"})
            self.hooks[7] = data
            return httpx.Response(201, json={"id": 7})
        if m := re.fullmatch(r"/repos/o/r/hooks/(\d+)", path):
            self.hooks.pop(int(m.group(1)), None)
            return httpx.Response(204)
        if path == "/repos/o/r/commits/main":
            return httpx.Response(200, json={"sha": "abc123"})
        if path == "/repos/o/r/git/trees/abc123":
            tree = [{"path": p, "type": "blob"} for p in self.files]
            tree.append({"path": "node_modules/x/package-lock.json", "type": "blob"})
            return httpx.Response(200, json={"tree": tree})
        if path.startswith("/repos/o/r/contents/"):
            name = path.removeprefix("/repos/o/r/contents/")
            return httpx.Response(200, content=self.files[name])
        if path == "/repos/o/r/issues":
            if method == "GET":
                return httpx.Response(
                    200, json=[i for i in self.issues.values() if i["state"] == "open"]
                )
            n = max([*self.issues, *self.milestones, 0]) + 1
            self.issues[n] = self._issue(n, data)
            return httpx.Response(201, json=self.issues[n])
        if m := re.fullmatch(r"/repos/o/r/issues/(\d+)", path):
            n = int(m.group(1))
            if method == "PATCH":
                cur = self.issues[n]
                merged = {
                    "title": cur["title"],
                    "body": cur["body"],
                    "state": cur["state"],
                    "labels": [lb["name"] for lb in cur["labels"]],
                    "assignees": [a["login"] for a in cur["assignees"]],
                    "milestone": (cur["milestone"] or {}).get("number"),
                    **data,
                }
                self.issues[n] = self._issue(n, merged)
            return httpx.Response(200, json=self.issues[n])
        if path == "/repos/o/r/milestones":
            if method == "GET":
                return httpx.Response(200, json=list(self.milestones.values()))
            n = max([*self.issues, *self.milestones, 0]) + 1
            self.milestones[n] = {"number": n, **data}
            return httpx.Response(201, json=self.milestones[n])
        if m := re.fullmatch(r"/repos/o/r/milestones/(\d+)", path):
            n = int(m.group(1))
            if method == "PATCH":
                self.milestones[n].update(data)
            return httpx.Response(200, json=self.milestones[n])
        return httpx.Response(404, json={"message": f"no route {method} {path}"})


@pytest.fixture
def gh(session: AsyncSession) -> Iterator[FakeGitHub]:
    fake = FakeGitHub()
    repo_client.transport = httpx.MockTransport(fake.handle)

    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield session

    old = repo_router.session_factory
    repo_router.session_factory = same_session
    yield fake
    repo_client.transport = None
    repo_router.session_factory = old


@pytest.fixture
async def project(client: AsyncClient, org: Org) -> str:
    p = await make_project(client, org.group_admin, "app", org.dev1.id)
    r = await client.post(
        f"/api/projects/{p['id']}/members",
        json={"user_id": str(org.member.id), "role": "member"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 201
    return str(p["id"])


async def link_repo(client: AsyncClient, org: Org, project: str, **extra: Any) -> dict[str, Any]:
    r = await client.post(
        f"/api/projects/{project}/repo-links",
        json={"provider": "github", "repo": "o/r", "token": "ghp_x", **extra},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def signed(link: dict[str, Any], event: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload).encode()
    digest = hmac.new(link["webhook_secret"].encode(), raw, hashlib.sha256).hexdigest()
    return {
        "content": raw,
        "headers": {
            "x-github-event": event,
            "x-hub-signature-256": f"sha256={digest}",
            "content-type": "application/json",
        },
    }


async def test_link_registers_webhook_and_imports(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub, session: AsyncSession
) -> None:
    gh.issues[1] = gh._issue(1, {"title": "既存の Issue", "labels": ["priority: high"]})
    link = await link_repo(client, org, project)
    assert link["webhook_registered"] and link["default_branch"] == "main"
    assert link["html_url"] == "https://github.com/o/r"
    assert gh.hooks[7]["config"]["url"].endswith(f"/api/repo-hooks/{link['id']}")
    stored = await session.get(RepoLink, UUID(link["id"]))
    assert stored is not None and "ghp_x" not in stored.token_encrypted

    # Background: lockfile imported (vendored dirs skipped) and the open issue pulled in.
    pkgs = (await session.exec(select(Package).where(Package.project_id == UUID(project)))).all()
    assert [(p.name, p.source) for p in pkgs] == [("lodash", "lockfile:git:o/r/package-lock.json")]
    task = (await session.exec(select(Task).where(Task.issue_number == 1))).one()
    assert task.title == "既存の Issue" and task.priority == "high"

    # Readers see the link but not the secret; viewers cannot manage it.
    r = await client.get(f"/api/projects/{project}/repo-links", headers=auth(org.member))
    assert r.status_code == 200 and r.json()[0]["webhook_secret"] is None
    r = await client.post(
        f"/api/projects/{project}/repo-links",
        json={"provider": "github", "repo": "o/r2", "token": "x"},
        headers=auth(org.member),
    )
    assert r.status_code == 403

    # Same repository twice -> 409.
    r = await client.post(
        f"/api/projects/{project}/repo-links",
        json={"provider": "github", "repo": "o/r", "token": "ghp_x"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 409


async def test_bad_token_and_webhook_failure(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub
) -> None:
    gh.token_ok = False
    r = await client.post(
        f"/api/projects/{project}/repo-links",
        json={"provider": "github", "repo": "o/r", "token": "bad"},
        headers={**auth(org.group_admin), "Accept-Language": "en"},
    )
    assert r.status_code == 422 and "Bad credentials" in r.json()["detail"]

    gh.token_ok = True
    gh.fail_hooks = True
    link = await link_repo(client, org, project)
    assert not link["webhook_registered"]
    assert link["last_error"].startswith("Webhook not registered")
    assert link["webhook_secret"]  # shown so it can be registered by hand


async def test_task_changes_reach_the_issue(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub, session: AsyncSession
) -> None:
    org.member.github_login = "Member-GH"
    session.add(org.member)
    await session.commit()
    await link_repo(client, org, project)
    h = auth(org.member)
    r = await client.post(
        f"/api/projects/{project}/tasks",
        json={"title": "ログイン画面", "assignee_id": str(org.member.id), "priority": "high"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["issue_number"] and task["issue_url"].startswith("https://github.com/o/r/issues/")
    issue = gh.issues[task["issue_number"]]
    assert issue["title"] == "ログイン画面"
    assert [lb["name"] for lb in issue["labels"]] == ["priority: high"]
    assert [a["login"] for a in issue["assignees"]] == ["Member-GH"]
    assert f"<!-- vectana:task:{task['id']} -->" in issue["body"]

    # A label added on GitHub survives; done closes the issue.
    issue["labels"].append({"name": "frontend"})
    r = await client.patch(
        f"/api/tasks/{task['id']}", json={"status": "done", "priority": None}, headers=h
    )
    assert r.status_code == 200, r.text
    issue = gh.issues[task["issue_number"]]
    assert issue["state"] == "closed"
    assert [lb["name"] for lb in issue["labels"]] == ["frontend"]

    # Fields Vectana keeps to itself do not call the provider.
    before = len(gh.calls)
    r = await client.patch(f"/api/tasks/{task['id']}", json={"points": 3}, headers=h)
    assert r.status_code == 200 and len(gh.calls) == before

    # Sprints become milestones; the issue joins it.
    r = await client.post(
        f"/api/projects/{project}/sprints",
        json={"name": "Sprint 1", "starts_on": "2026-11-02", "ends_on": "2026-11-13"},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 201, r.text
    sprint = await session.get(Sprint, UUID(r.json()["id"]))
    assert sprint is not None and sprint.milestone_number is not None
    assert gh.milestones[sprint.milestone_number]["title"] == "Sprint 1"
    r = await client.patch(
        f"/api/tasks/{task['id']}", json={"sprint_id": str(sprint.id)}, headers=h
    )
    assert gh.issues[task["issue_number"]]["milestone"]["number"] == sprint.milestone_number


async def test_tasks_made_before_link_get_no_issue(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub
) -> None:
    r = await client.post(
        f"/api/projects/{project}/tasks", json={"title": "前から"}, headers=auth(org.member)
    )
    old = r.json()
    await link_repo(client, org, project)
    r = await client.patch(
        f"/api/tasks/{old['id']}", json={"title": "改名"}, headers=auth(org.member)
    )
    assert r.json()["issue_number"] is None
    assert not gh.issues


async def test_issue_webhook(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub, session: AsyncSession
) -> None:
    org.member.github_login = "member-gh"
    session.add(org.member)
    await session.commit()
    link = await link_repo(client, org, project)
    url = f"/api/repo-hooks/{link['id']}"

    # Wrong signature -> 401.
    r = await client.post(
        url, content=b"{}", headers={"x-github-event": "issues", "x-hub-signature-256": "sha256=0"}
    )
    assert r.status_code == 401

    gh.milestones[50] = {"number": 50, "title": "v1.0", "state": "open", "due_on": None}
    issue = {
        "number": 42,
        "title": "検索が遅い",
        "state": "open",
        "html_url": "https://github.com/o/r/issues/42",
        "body": "詳細",
        "labels": [{"name": "Priority: Low"}, {"name": "other"}],
        "assignees": [{"login": "MEMBER-GH"}],
        "milestone": {"number": 50, "title": "v1.0", "state": "open"},
    }
    r = await client.post(url, **signed(link, "issues", {"action": "opened", "issue": issue}))
    assert r.status_code == 200 and r.json()["handled"], r.text
    task = (await session.exec(select(Task).where(Task.issue_number == 42))).one()
    assert (task.title, task.kind, task.priority) == ("検索が遅い", "other", "low")
    assert task.assignee_id == org.member.id
    sprint = await session.get(Sprint, task.sprint_id)
    assert sprint is not None and sprint.name == "v1.0" and sprint.milestone_number == 50

    # Closing the issue completes the task; an unknown assignee leaves it alone.
    issue |= {"state": "closed", "assignees": [{"login": "stranger"}], "title": "検索を速く"}
    r = await client.post(url, **signed(link, "issues", {"action": "closed", "issue": issue}))
    await session.refresh(task)
    assert task.status == "done" and task.title == "検索を速く"
    assert task.assignee_id == org.member.id

    # An issue Vectana opened is matched by its marker, not duplicated.
    r = await client.post(
        f"/api/projects/{project}/tasks", json={"title": "API"}, headers=auth(org.member)
    )
    mine = r.json()
    echo = gh.issues[mine["issue_number"]] | {"number": 99}
    await client.post(url, **signed(link, "issues", {"action": "opened", "issue": echo}))
    count = len((await session.exec(select(Task).where(Task.title == "API"))).all())
    assert count == 1


async def test_merged_pull_request_completes_tasks(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub, session: AsyncSession
) -> None:
    link = await link_repo(client, org, project)
    r = await client.post(
        f"/api/projects/{project}/tasks", json={"title": "修正"}, headers=auth(org.member)
    )
    task = r.json()
    payload = {
        "action": "closed",
        "pull_request": {"merged": True, "title": "Fix", "body": f"Closes #{task['issue_number']}"},
    }
    r = await client.post(f"/api/repo-hooks/{link['id']}", **signed(link, "pull_request", payload))
    assert r.json()["handled"]
    row = await session.get(Task, UUID(task["id"]))
    assert row is not None and row.status == "done"


async def test_push_imports_and_removes_deleted_files(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub, session: AsyncSession
) -> None:
    link = await link_repo(client, org, project)
    gh.files = {"web/package-lock.json": LOCK}
    r = await client.post(
        f"/api/repo-hooks/{link['id']}", **signed(link, "push", {"ref": "refs/heads/feature"})
    )
    assert not r.json()["handled"]
    r = await client.post(
        f"/api/repo-hooks/{link['id']}", **signed(link, "push", {"ref": "refs/heads/main"})
    )
    assert r.json()["handled"]
    pkgs = (await session.exec(select(Package).where(Package.project_id == UUID(project)))).all()
    assert [p.source for p in pkgs] == ["lockfile:git:o/r/web/package-lock.json"]

    # Import paths limit what is read.
    r = await client.patch(
        f"/api/repo-links/{link['id']}",
        json={"import_paths": ["api/**"]},
        headers=auth(org.group_admin),
    )
    assert r.status_code == 200
    r = await client.post(f"/api/repo-links/{link['id']}/import", headers=auth(org.group_admin))
    assert r.status_code == 200 and r.json()["files"] == [] and r.json()["removed_sources"] == 1


async def test_auto_security_task_opens_issue(
    client: AsyncClient, org: Org, project: str, gh: FakeGitHub, session: AsyncSession
) -> None:
    from app.services import tasks as security_tasks

    await link_repo(client, org, project, sync_issues=False)
    await add_vuln(session, project, "lodash", "GHSA-1", "CRITICAL", "4.17.20", "4.17.21")
    await security_tasks.sync(session, [UUID(project)])
    task = (await session.exec(select(Task).where(Task.kind == "security"))).one()
    assert task.issue_number is not None
    issue = gh.issues[task.issue_number]
    assert issue["title"] == "lodash を 4.17.21 に更新"
    assert [lb["name"] for lb in issue["labels"]] == ["security"]

    # With sync_issues off, hand-made tasks stay in Vectana.
    r = await client.post(
        f"/api/projects/{project}/tasks", json={"title": "手作業"}, headers=auth(org.member)
    )
    assert r.json()["issue_number"] is None


async def test_gitlab_issue_hook(
    client: AsyncClient, org: Org, project: str, session: AsyncSession
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "git.example.com"
        if request.url.raw_path == b"/api/v4/projects/grp%2Fapp":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.url.path.endswith("/hooks"):
            return httpx.Response(201, json={"id": 3})
        return httpx.Response(404, json={"message": "404 Not Found"})

    repo_client.transport = httpx.MockTransport(handle)
    old = repo_router.session_factory
    repo_router.session_factory = lambda: _noop_session()  # skip the initial import
    try:
        r = await client.post(
            f"/api/projects/{project}/repo-links",
            json={
                "provider": "gitlab",
                "base_url": "https://git.example.com/",
                "repo": "grp/app",
                "token": "glpat",
            },
            headers=auth(org.group_admin),
        )
        assert r.status_code == 201, r.text
        link = r.json()
        assert link["html_url"] == "https://git.example.com/grp/app"
        payload = {
            "object_kind": "issue",
            "object_attributes": {
                "iid": 5,
                "title": "障害対応",
                "state": "opened",
                "url": "https://git.example.com/grp/app/-/issues/5",
                "description": "",
            },
            "labels": [{"title": "security"}],
            "assignees": [],
        }
        url = f"/api/repo-hooks/{link['id']}"
        r = await client.post(
            url, json=payload, headers={"x-gitlab-event": "Issue Hook", "x-gitlab-token": "no"}
        )
        assert r.status_code == 401
        r = await client.post(
            url,
            json=payload,
            headers={"x-gitlab-event": "Issue Hook", "x-gitlab-token": link["webhook_secret"]},
        )
        assert r.status_code == 200 and r.json()["handled"], r.text
    finally:
        repo_client.transport = None
        repo_router.session_factory = old
    task = (await session.exec(select(Task).where(Task.issue_number == 5))).one()
    assert task.kind == "security" and task.issue_url.endswith("/-/issues/5")


@asynccontextmanager
async def _noop_session() -> AsyncIterator[AsyncSession]:
    class Empty:
        async def get(self, *_: object) -> None:
            return None

    yield Empty()  # type: ignore[misc]


async def test_account_names(client: AsyncClient, org: Org, session: AsyncSession) -> None:
    r = await client.put(
        "/api/auth/accounts",
        json={"github_login": " @Octo ", "gitlab_username": ""},
        headers=auth(org.member),
    )
    assert r.status_code == 200 and r.json() == {"github_login": "Octo", "gitlab_username": None}
    me = (await client.get("/api/auth/me", headers=auth(org.member))).json()
    assert me["github_login"] == "Octo"
    r = await client.put(
        "/api/auth/accounts", json={"github_login": "octo"}, headers=auth(org.head)
    )
    assert r.status_code == 409
    user = await session.get(User, org.head.id)
    assert user is not None and user.github_login is None
