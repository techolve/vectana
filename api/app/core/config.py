from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Vectana"
    debug: bool = False
    # Public base URL of the app, used to build links in outbound email.
    web_url: str = "http://localhost:8000"
    # Display name of the group that owns this instance (グループ名).
    group_name: str = "Vectana Group"
    # Directory holding the exported Next.js build. Served at "/" when present.
    static_dir: Path = Path(__file__).resolve().parents[2] / "static"
    # Extra CORS origins (only needed when running `next dev` separately).
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Database
    database_url: str = "postgresql+asyncpg://vectana:vectana@db:5432/vectana"

    # JWT
    secret_key: str = "change-me-in-production"  # openssl rand -hex 32
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    invitation_expire_days: int = 7

    # OSV
    osv_base_url: str = "https://api.osv.dev"
    osv_timeout_seconds: float = 30.0
    osv_max_retries: int = 3

    # endoflife.date
    eol_base_url: str = "https://endoflife.date/api/v1"
    eol_timeout_seconds: float = 20.0
    eol_cache_ttl_seconds: float = 6 * 3600

    # Worker
    scan_interval_minutes: int = 360
    # Scan packages right after they are added (in the API process).
    scan_on_change: bool = True

    # Mail: "smtp" | "cloudflare" | "none"
    mail_backend: str = "smtp"
    mail_from: str = "Vectana <vectana@example.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False  # implicit TLS (SMTPS, usually port 465)
    smtp_start_tls: bool = True  # STARTTLS (usually port 587)
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""

    # Outbound webhooks (Discord / Slack)
    webhook_timeout_seconds: float = 10.0


settings = Settings()
