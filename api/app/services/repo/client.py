"""Small GitHub / GitLab REST clients that speak in the same terms: issues,
milestones, the file tree of a commit, and webhooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.models.repo import RepoLink, RepoProvider
from app.services.repo import secrets

GITHUB_API = "https://api.github.com"
GITLAB_URL = "https://gitlab.com"
TIMEOUT = 15.0
MAX_TREE_PAGES = 20

# Tests replace this with an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


class RepoError(Exception):
    """The provider refused or failed a request."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Milestone:
    number: int  # GitHub: number; GitLab: the milestone's id
    title: str
    state: str  # open | closed
    due_on: date | None = None
    description: str | None = None


@dataclass
class Issue:
    number: int  # GitHub: number; GitLab: iid
    title: str
    state: str  # open | closed
    url: str
    body: str | None = None
    assignees: list[str] = field(default_factory=list)  # logins / usernames
    labels: list[str] = field(default_factory=list)
    milestone: int | None = None
    is_pull_request: bool = False


@dataclass
class IssueChange:
    """What to set on an issue; None leaves a field as it is."""

    title: str | None = None
    body: str | None = None
    state: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: int | None = None
    clear_milestone: bool = False


class RepoClient(Protocol):
    async def default_branch(self) -> str: ...
    async def tree(self, ref: str) -> tuple[str, list[str]]: ...
    async def file(self, path: str, ref: str) -> bytes: ...
    async def get_issue(self, number: int) -> Issue: ...
    async def list_issues(self, limit: int = 500) -> list[Issue]: ...
    async def create_issue(self, change: IssueChange) -> Issue: ...
    async def update_issue(self, number: int, change: IssueChange) -> Issue: ...
    async def get_milestone(self, number: int) -> Milestone: ...
    async def list_milestones(self) -> list[Milestone]: ...
    async def create_milestone(self, m: Milestone) -> Milestone: ...
    async def update_milestone(self, m: Milestone) -> Milestone: ...
    async def create_webhook(self, url: str, secret: str) -> str: ...
    async def delete_webhook(self, hook_id: str) -> None: ...
    async def aclose(self) -> None: ...


def default_base_url(provider: str) -> str:
    return GITHUB_API if provider == RepoProvider.github else GITLAB_URL


def make_client(link: RepoLink, token: str | None = None) -> RepoClient:
    token = token if token is not None else secrets.decrypt(link.token_encrypted)
    if not token:
        raise RepoError("The access token cannot be read; enter it again")
    if link.provider == RepoProvider.github:
        return GitHubClient(link.base_url, link.repo, token)
    return GitLabClient(link.base_url, link.repo, token)


class _Base:
    def __init__(self, base_url: str, headers: dict[str, str]) -> None:
        self.http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"User-Agent": "Vectana", **headers},
            timeout=TIMEOUT,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _call(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            r = await self.http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise RepoError(f"{method} {path}: {exc}") from exc
        if r.status_code >= 400:
            try:
                detail = r.json().get("message") or r.text
            except ValueError:
                detail = r.text
            raise RepoError(f"{method} {path}: {r.status_code} {str(detail)[:200]}", r.status_code)
        return r

    async def _json(self, method: str, path: str, **kw: Any) -> Any:
        r = await self._call(method, path, **kw)
        return r.json() if r.content else None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


# --- GitHub ------------------------------------------------------------------------


class GitHubClient(_Base):
    def __init__(self, base_url: str, repo: str, token: str) -> None:
        super().__init__(
            base_url or GITHUB_API,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        self.r = f"/repos/{repo}"

    @staticmethod
    def issue(d: dict[str, Any]) -> Issue:
        return Issue(
            number=d["number"],
            title=d.get("title") or "",
            state="closed" if d.get("state") == "closed" else "open",
            url=d.get("html_url") or "",
            body=d.get("body"),
            assignees=[a["login"] for a in d.get("assignees") or [] if a.get("login")],
            labels=[
                lb["name"] if isinstance(lb, dict) else str(lb) for lb in d.get("labels") or []
            ],
            milestone=(d.get("milestone") or {}).get("number"),
            is_pull_request="pull_request" in d,
        )

    @staticmethod
    def milestone(d: dict[str, Any]) -> Milestone:
        return Milestone(
            number=d["number"],
            title=d.get("title") or "",
            state="closed" if d.get("state") == "closed" else "open",
            due_on=_date(d.get("due_on")),
            description=d.get("description"),
        )

    async def default_branch(self) -> str:
        return str((await self._json("GET", self.r))["default_branch"])

    async def tree(self, ref: str) -> tuple[str, list[str]]:
        sha = (await self._json("GET", f"{self.r}/commits/{quote(ref, safe='')}"))["sha"]
        data = await self._json("GET", f"{self.r}/git/trees/{sha}", params={"recursive": "1"})
        return sha, [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"]

    async def file(self, path: str, ref: str) -> bytes:
        r = await self._call(
            "GET",
            f"{self.r}/contents/{quote(path)}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw"},
        )
        return r.content

    async def get_issue(self, number: int) -> Issue:
        return self.issue(await self._json("GET", f"{self.r}/issues/{number}"))

    async def list_issues(self, limit: int = 500) -> list[Issue]:
        out: list[Issue] = []
        page = 1
        while len(out) < limit:
            rows = await self._json(
                "GET", f"{self.r}/issues", params={"state": "open", "per_page": 100, "page": page}
            )
            out += [self.issue(d) for d in rows if "pull_request" not in d]
            if len(rows) < 100:
                break
            page += 1
        return out[:limit]

    def _body(self, c: IssueChange) -> dict[str, Any]:
        body: dict[str, Any] = {}
        for key in ("title", "body", "state", "labels", "assignees"):
            value = getattr(c, key)
            if value is not None:
                body[key] = value
        if c.milestone is not None:
            body["milestone"] = c.milestone
        elif c.clear_milestone:
            body["milestone"] = None
        return body

    async def create_issue(self, change: IssueChange) -> Issue:
        return self.issue(await self._json("POST", f"{self.r}/issues", json=self._body(change)))

    async def update_issue(self, number: int, change: IssueChange) -> Issue:
        return self.issue(
            await self._json("PATCH", f"{self.r}/issues/{number}", json=self._body(change))
        )

    async def get_milestone(self, number: int) -> Milestone:
        return self.milestone(await self._json("GET", f"{self.r}/milestones/{number}"))

    async def list_milestones(self) -> list[Milestone]:
        rows = await self._json(
            "GET", f"{self.r}/milestones", params={"state": "all", "per_page": 100}
        )
        return [self.milestone(d) for d in rows]

    def _ms(self, m: Milestone) -> dict[str, Any]:
        return {
            "title": m.title,
            "state": m.state,
            "description": m.description or "",
            "due_on": f"{m.due_on.isoformat()}T23:59:59Z" if m.due_on else None,
        }

    async def create_milestone(self, m: Milestone) -> Milestone:
        return self.milestone(await self._json("POST", f"{self.r}/milestones", json=self._ms(m)))

    async def update_milestone(self, m: Milestone) -> Milestone:
        return self.milestone(
            await self._json("PATCH", f"{self.r}/milestones/{m.number}", json=self._ms(m))
        )

    async def create_webhook(self, url: str, secret: str) -> str:
        d = await self._json(
            "POST",
            f"{self.r}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": ["push", "issues", "milestone", "pull_request"],
                "config": {"url": url, "content_type": "json", "secret": secret},
            },
        )
        return str(d["id"])

    async def delete_webhook(self, hook_id: str) -> None:
        await self._call("DELETE", f"{self.r}/hooks/{hook_id}")


# --- GitLab ------------------------------------------------------------------------


class GitLabClient(_Base):
    def __init__(self, base_url: str, repo: str, token: str) -> None:
        super().__init__(f"{(base_url or GITLAB_URL).rstrip('/')}/api/v4", {"PRIVATE-TOKEN": token})
        self.p = f"/projects/{quote(repo, safe='')}"
        self._user_ids: dict[str, int | None] = {}

    @staticmethod
    def issue(d: dict[str, Any]) -> Issue:
        ms = d.get("milestone") or {}
        return Issue(
            number=d["iid"],
            title=d.get("title") or "",
            state="closed" if d.get("state") == "closed" else "open",
            url=d.get("web_url") or d.get("url") or "",
            body=d.get("description"),
            assignees=[a["username"] for a in d.get("assignees") or [] if a.get("username")],
            labels=[
                lb["title"] if isinstance(lb, dict) else str(lb) for lb in d.get("labels") or []
            ],
            milestone=ms.get("id") if ms else d.get("milestone_id"),
        )

    @staticmethod
    def milestone(d: dict[str, Any]) -> Milestone:
        return Milestone(
            number=d["id"],
            title=d.get("title") or "",
            state="closed" if d.get("state") == "closed" else "open",
            due_on=_date(d.get("due_date")),
            description=d.get("description"),
        )

    async def default_branch(self) -> str:
        return str((await self._json("GET", self.p))["default_branch"])

    async def tree(self, ref: str) -> tuple[str, list[str]]:
        sha = (await self._json("GET", f"{self.p}/repository/commits/{quote(ref, safe='')}"))["id"]
        paths: list[str] = []
        for page in range(1, MAX_TREE_PAGES + 1):
            rows = await self._json(
                "GET",
                f"{self.p}/repository/tree",
                params={"ref": sha, "recursive": "true", "per_page": 100, "page": page},
            )
            paths += [e["path"] for e in rows if e.get("type") == "blob"]
            if len(rows) < 100:
                break
        return sha, paths

    async def file(self, path: str, ref: str) -> bytes:
        r = await self._call(
            "GET", f"{self.p}/repository/files/{quote(path, safe='')}/raw", params={"ref": ref}
        )
        return r.content

    async def get_issue(self, number: int) -> Issue:
        return self.issue(await self._json("GET", f"{self.p}/issues/{number}"))

    async def list_issues(self, limit: int = 500) -> list[Issue]:
        out: list[Issue] = []
        page = 1
        while len(out) < limit:
            rows = await self._json(
                "GET",
                f"{self.p}/issues",
                params={"state": "opened", "per_page": 100, "page": page},
            )
            out += [self.issue(d) for d in rows]
            if len(rows) < 100:
                break
            page += 1
        return out[:limit]

    async def _user_id(self, username: str) -> int | None:
        if username not in self._user_ids:
            rows = await self._json("GET", "/users", params={"username": username})
            self._user_ids[username] = rows[0]["id"] if rows else None
        return self._user_ids[username]

    async def _body(self, c: IssueChange) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if c.title is not None:
            body["title"] = c.title
        if c.body is not None:
            body["description"] = c.body
        if c.state is not None:
            body["state_event"] = "close" if c.state == "closed" else "reopen"
        if c.labels is not None:
            body["labels"] = ",".join(c.labels)
        if c.assignees is not None:
            ids = [i for u in c.assignees if (i := await self._user_id(u)) is not None]
            body["assignee_ids"] = ids or [0]  # [0] unassigns
        if c.milestone is not None:
            body["milestone_id"] = c.milestone
        elif c.clear_milestone:
            body["milestone_id"] = 0
        return body

    async def create_issue(self, change: IssueChange) -> Issue:
        body = await self._body(change)
        body.pop("state_event", None)
        issue = self.issue(await self._json("POST", f"{self.p}/issues", json=body))
        if change.state == "closed":
            issue = await self.update_issue(issue.number, IssueChange(state="closed"))
        return issue

    async def update_issue(self, number: int, change: IssueChange) -> Issue:
        return self.issue(
            await self._json("PUT", f"{self.p}/issues/{number}", json=await self._body(change))
        )

    async def get_milestone(self, number: int) -> Milestone:
        return self.milestone(await self._json("GET", f"{self.p}/milestones/{number}"))

    async def list_milestones(self) -> list[Milestone]:
        rows = await self._json("GET", f"{self.p}/milestones", params={"per_page": 100})
        return [self.milestone(d) for d in rows]

    async def create_milestone(self, m: Milestone) -> Milestone:
        d = await self._json(
            "POST",
            f"{self.p}/milestones",
            json={
                "title": m.title,
                "description": m.description or "",
                "due_date": m.due_on.isoformat() if m.due_on else None,
            },
        )
        created = self.milestone(d)
        if m.state == "closed":
            created.state = "closed"
            created = await self.update_milestone(created)
        return created

    async def update_milestone(self, m: Milestone) -> Milestone:
        return self.milestone(
            await self._json(
                "PUT",
                f"{self.p}/milestones/{m.number}",
                json={
                    "title": m.title,
                    "description": m.description or "",
                    "due_date": m.due_on.isoformat() if m.due_on else None,
                    "state_event": "close" if m.state == "closed" else "activate",
                },
            )
        )

    async def create_webhook(self, url: str, secret: str) -> str:
        d = await self._json(
            "POST",
            f"{self.p}/hooks",
            json={
                "url": url,
                "token": secret,
                "push_events": True,
                "issues_events": True,
                "merge_requests_events": True,
                "enable_ssl_verification": True,
            },
        )
        return str(d["id"])

    async def delete_webhook(self, hook_id: str) -> None:
        await self._call("DELETE", f"{self.p}/hooks/{hook_id}")
