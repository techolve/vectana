from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.repo import RepoProvider
from app.schemas.project import ImportResult

REPO_PATTERN = r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+$"


class RepoLinkBody(BaseModel):
    provider: RepoProvider
    # API root. Default: https://api.github.com / https://gitlab.com. For GitHub
    # Enterprise use https://HOST/api/v3; for GitLab the server's URL.
    base_url: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    repo: str = Field(max_length=300, pattern=REPO_PATTERN, description="owner/name, group/project")
    token: str = Field(min_length=1, max_length=500)
    sync_issues: bool = True
    security_issues: bool = True
    import_paths: list[str] = Field(default_factory=list, max_length=50)
    register_webhook: bool = True


class RepoLinkUpdate(BaseModel):
    token: str | None = Field(default=None, min_length=1, max_length=500)
    default_branch: str | None = Field(default=None, min_length=1, max_length=200)
    sync_issues: bool | None = None
    security_issues: bool | None = None
    import_paths: list[str] | None = Field(default=None, max_length=50)


class RepoLinkOut(BaseModel):
    id: UUID
    project_id: UUID
    provider: str
    base_url: str
    repo: str
    html_url: str
    default_branch: str
    sync_issues: bool
    security_issues: bool
    import_paths: list[str]
    webhook_url: str
    webhook_registered: bool
    # Only for project managers (to register the webhook by hand).
    webhook_secret: str | None
    last_import_at: datetime | None
    last_import_sha: str | None
    last_event_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    created_at: datetime


class RepoImportFile(BaseModel):
    path: str
    result: ImportResult | None
    error: str | None


class RepoImportOut(BaseModel):
    sha: str
    files: list[RepoImportFile]
    removed_sources: int


class RepoSyncOut(BaseModel):
    tasks: int
    sprints: int
