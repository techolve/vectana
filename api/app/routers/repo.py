"""GitHub / GitLab repository links of a project, and the webhook they call.

Project managers link a repository with an access token. Vectana then imports
the repository's lockfiles and SBOMs (on push to the default branch, once a
day, or on demand) and keeps issues <-> tasks and milestones <-> sprints in
step. The webhook is registered automatically when the token may; otherwise
its URL and secret are shown for registering it by hand."""

import hashlib
import hmac
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import Actor, Level, accessible_project, get_actor, project_level
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_session
from app.models.base import utcnow
from app.models.repo import RepoLink, RepoProvider
from app.schemas.repo import (
    RepoImportFile,
    RepoImportOut,
    RepoLinkBody,
    RepoLinkOut,
    RepoLinkUpdate,
    RepoSyncOut,
)
from app.services.repo import secrets
from app.services.repo import sync as repo_sync
from app.services.repo.client import (
    GitHubClient,
    GitLabClient,
    RepoError,
    default_base_url,
    make_client,
)
from app.services.scanner import scan_and_notify

logger = logging.getLogger("vectana.repo")

router = APIRouter(prefix="/api", tags=["repositories"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


@asynccontextmanager
async def _new_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as s:
        yield s


# Background work opens its own session; tests swap this for theirs.
session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] = _new_session


def webhook_url(link: RepoLink) -> str:
    return f"{settings.web_url.rstrip('/')}/api/repo-hooks/{link.id}"


def html_url(link: RepoLink) -> str:
    base = link.base_url.rstrip("/")
    if link.provider == RepoProvider.github:
        host = "https://github.com" if base == default_base_url("github") else base
        host = host.removesuffix("/api/v3")
        return f"{host}/{link.repo}"
    return f"{base}/{link.repo}"


def _out(link: RepoLink, manager: bool) -> RepoLinkOut:
    return RepoLinkOut(
        id=link.id,
        project_id=link.project_id,
        provider=link.provider,
        base_url=link.base_url,
        repo=link.repo,
        html_url=html_url(link),
        default_branch=link.default_branch,
        sync_issues=link.sync_issues,
        security_issues=link.security_issues,
        import_paths=list(link.import_paths or []),
        webhook_url=webhook_url(link),
        webhook_registered=link.webhook_id is not None,
        webhook_secret=link.webhook_secret if manager else None,
        last_import_at=link.last_import_at,
        last_import_sha=link.last_import_sha,
        last_event_at=link.last_event_at,
        last_error=link.last_error,
        last_error_at=link.last_error_at,
        created_at=link.created_at,
    )


def _paths(paths: list[str]) -> list[str]:
    return [p.strip() for p in paths if p.strip()]


@router.get(
    "/projects/{project_id}/repo-links",
    response_model=list[RepoLinkOut],
    summary="リポジトリ連携の一覧",
)
async def list_links(project_id: UUID, actor: CurrentActor, session: Session) -> list[RepoLinkOut]:
    project = await accessible_project(project_id, actor, session)
    manager = (await project_level(project, actor, session)) == Level.manage
    rows = (
        await session.exec(
            select(RepoLink)
            .where(RepoLink.project_id == project_id)
            .order_by(col(RepoLink.created_at))
        )
    ).all()
    return [_out(link, manager) for link in rows]


@router.post(
    "/projects/{project_id}/repo-links",
    response_model=RepoLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="リポジトリを連携",
)
async def create_link(
    project_id: UUID,
    body: RepoLinkBody,
    tasks: BackgroundTasks,
    actor: CurrentActor,
    session: Session,
) -> RepoLinkOut:
    """Checks the token by reading the repository, registers the webhook when
    allowed, then imports dependency files and open issues in the background."""
    await accessible_project(project_id, actor, session, Level.manage)
    link = RepoLink(
        project_id=project_id,
        provider=body.provider,
        base_url=(body.base_url or default_base_url(body.provider)).rstrip("/"),
        repo=body.repo.strip("/"),
        token_encrypted=secrets.encrypt(body.token),
        webhook_secret=secrets.new_webhook_secret(),
        sync_issues=body.sync_issues,
        security_issues=body.security_issues,
        import_paths=_paths(body.import_paths),
        created_by=actor.user.id,
    )
    client = make_client(link, body.token)
    try:
        try:
            link.default_branch = await client.default_branch()
        except RepoError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Cannot read the repository: {exc}",
            ) from exc
        if body.register_webhook:
            try:
                link.webhook_id = await client.create_webhook(
                    webhook_url(link), link.webhook_secret
                )
            except RepoError as exc:
                link.last_error = f"Webhook not registered: {exc}"[:1000]
                link.last_error_at = utcnow()
    finally:
        await client.aclose()
    session.add(link)
    try:
        await session.commit()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This repository is already linked") from exc
    tasks.add_task(_initial_sync, link.id)
    return _out(link, True)


async def _initial_sync(link_id: UUID) -> None:
    async with session_factory() as session:
        link = await session.get(RepoLink, link_id)
        if link is None:
            return
        await _run_import(session, link)
        if link.sync_issues:
            try:
                await repo_sync.pull_issues(session, link)
            except RepoError as exc:
                await repo_sync.record_error(session, link, exc)


async def _run_import(session: AsyncSession, link: RepoLink) -> repo_sync.RepoImport | None:
    try:
        done = await repo_sync.import_repo(session, link)
    except RepoError as exc:
        await repo_sync.record_error(session, link, exc)
        return None
    if settings.scan_on_change and (done.added_package_ids or done.runtimes_changed):
        await scan_and_notify(
            done.added_package_ids or None, [link.project_id] if done.runtimes_changed else None
        )
    return done


async def _manage_link(link_id: UUID, actor: Actor, session: AsyncSession) -> RepoLink:
    link = await session.get(RepoLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository link not found")
    await accessible_project(link.project_id, actor, session, Level.manage)
    return link


@router.patch("/repo-links/{link_id}", response_model=RepoLinkOut, summary="リポジトリ連携の更新")
async def update_link(
    link_id: UUID, body: RepoLinkUpdate, actor: CurrentActor, session: Session
) -> RepoLinkOut:
    link = await _manage_link(link_id, actor, session)
    if body.token is not None:
        client = make_client(link, body.token)
        try:
            await client.default_branch()
        except RepoError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Cannot read the repository: {exc}"
            ) from exc
        finally:
            await client.aclose()
        link.token_encrypted = secrets.encrypt(body.token)
        link.last_error = None
    if body.default_branch is not None:
        link.default_branch = body.default_branch.strip()
    if body.sync_issues is not None:
        link.sync_issues = body.sync_issues
    if body.security_issues is not None:
        link.security_issues = body.security_issues
    if body.import_paths is not None:
        link.import_paths = _paths(body.import_paths)
    session.add(link)
    await session.commit()
    return _out(link, True)


@router.delete(
    "/repo-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT, summary="連携の解除"
)
async def delete_link(link_id: UUID, actor: CurrentActor, session: Session) -> None:
    """Removes the webhook when Vectana registered it. Tasks keep their issue
    links as plain URLs; imported packages stay until the next upload."""
    link = await _manage_link(link_id, actor, session)
    if link.webhook_id:
        try:
            client = make_client(link)
            try:
                await client.delete_webhook(link.webhook_id)
            finally:
                await client.aclose()
        except RepoError as exc:
            logger.warning("Could not remove the webhook of %s: %s", link.repo, exc)
    await session.delete(link)
    await session.commit()


@router.post("/repo-links/{link_id}/import", response_model=RepoImportOut, summary="今すぐ取り込む")
async def import_now(link_id: UUID, actor: CurrentActor, session: Session) -> RepoImportOut:
    link = await _manage_link(link_id, actor, session)
    done = await _run_import(session, link)
    if done is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, link.last_error or "Import failed")
    return RepoImportOut(
        sha=done.sha,
        files=[RepoImportFile(path=f.path, result=f.result, error=f.error) for f in done.files],
        removed_sources=done.removed_sources,
    )


@router.post("/repo-links/{link_id}/sync", response_model=RepoSyncOut, summary="Issue を取り込む")
async def sync_now(link_id: UUID, actor: CurrentActor, session: Session) -> RepoSyncOut:
    """Bring in open issues and milestones as tasks and sprints."""
    link = await _manage_link(link_id, actor, session)
    try:
        count, sprints = await repo_sync.pull_issues(session, link)
    except RepoError as exc:
        await repo_sync.record_error(session, link, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return RepoSyncOut(tasks=count, sprints=sprints)


# --- Webhook --------------------------------------------------------------------------


def _verified(link: RepoLink, request: Request, raw: bytes) -> bool:
    if link.provider == RepoProvider.github:
        sent = request.headers.get("x-hub-signature-256", "")
        digest = hmac.new(link.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sent, f"sha256={digest}")
    return hmac.compare_digest(request.headers.get("x-gitlab-token", ""), link.webhook_secret)


@router.post("/repo-hooks/{link_id}", summary="GitHub / GitLab の Webhook 受信")
async def receive_hook(
    link_id: UUID, request: Request, tasks: BackgroundTasks, session: Session
) -> dict[str, Any]:
    link = await session.get(RepoLink, link_id)
    raw = await request.body()
    if link is None or not _verified(link, request, raw):
        # The same answer either way: do not reveal which links exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON") from exc
    link.last_event_at = utcnow()
    session.add(link)

    if link.provider == RepoProvider.github:
        event = request.headers.get("x-github-event", "")
        handled = await _github(session, link, event, payload, tasks)
    else:
        event = request.headers.get("x-gitlab-event", "")
        handled = await _gitlab(session, link, event, payload, tasks)
    await session.commit()
    return {"event": event, "handled": handled}


def _schedule_import(tasks: BackgroundTasks, link: RepoLink, ref: str) -> bool:
    if ref != f"refs/heads/{link.default_branch}":
        return False
    tasks.add_task(_import_in_background, link.id)
    return True


async def _import_in_background(link_id: UUID) -> None:
    async with session_factory() as session:
        link = await session.get(RepoLink, link_id)
        if link is not None:
            await _run_import(session, link)


async def _github(
    session: AsyncSession,
    link: RepoLink,
    event: str,
    payload: dict[str, Any],
    tasks: BackgroundTasks,
) -> bool:
    if event == "push":
        return _schedule_import(tasks, link, payload.get("ref", ""))
    if event == "issues" and "issue" in payload:
        if payload.get("action") == "deleted":
            return False
        client = make_client(link)
        try:
            task = await repo_sync.apply_issue(
                session, link, GitHubClient.issue(payload["issue"]), client
            )
        finally:
            await client.aclose()
        return task is not None
    if event == "milestone" and "milestone" in payload and link.sync_issues:
        if payload.get("action") == "deleted":
            return False
        await repo_sync.apply_milestone(session, link, GitHubClient.milestone(payload["milestone"]))
        return True
    if event == "pull_request":
        pr = payload.get("pull_request") or {}
        if payload.get("action") == "closed" and pr.get("merged"):
            text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
            return await repo_sync.apply_merged(session, link, text) > 0
    return False


async def _gitlab(
    session: AsyncSession,
    link: RepoLink,
    event: str,
    payload: dict[str, Any],
    tasks: BackgroundTasks,
) -> bool:
    attrs = payload.get("object_attributes") or {}
    if event == "Push Hook":
        return _schedule_import(tasks, link, payload.get("ref", ""))
    if event == "Issue Hook":
        issue = GitLabClient.issue(
            {
                **attrs,
                "labels": payload.get("labels") or attrs.get("labels") or [],
                "assignees": payload.get("assignees") or [],
                "web_url": attrs.get("url"),
            }
        )
        client = make_client(link)
        try:
            task = await repo_sync.apply_issue(session, link, issue, client)
        finally:
            await client.aclose()
        return task is not None
    if event == "Merge Request Hook" and attrs.get("action") == "merge":
        text = f"{attrs.get('title') or ''}\n{attrs.get('description') or ''}"
        return await repo_sync.apply_merged(session, link, text) > 0
    return False


# --- Daily import (worker) ------------------------------------------------------------


async def import_due_links() -> int:
    """Import every link not imported in the last 20 hours (the push webhook
    can be missed). Returns how many were imported."""
    async with session_factory() as session:
        cutoff = utcnow() - timedelta(hours=20)
        links = (
            await session.exec(
                select(RepoLink).where(
                    (col(RepoLink.last_import_at).is_(None))
                    | (col(RepoLink.last_import_at) < cutoff)
                )
            )
        ).all()
        count = 0
        for link in links:
            if await _run_import(session, link) is not None:
                count += 1
        return count
