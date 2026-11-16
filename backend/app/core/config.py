"""Application settings, read from environment variables (and `.env` locally)."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Analytica Studio API"
    environment: str = "local"  # local | dev | prod | test
    log_level: str = "INFO"

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg://analytica:analytica@localhost:5432/analytica"
    redis_url: str = "redis://localhost:6379/0"

    # Object storage. "s3" (SeaweedFS locally, AWS S3 deployed) or "local" (tests).
    storage_backend: str = "s3"
    local_storage_dir: str = "/tmp/analytica-storage"
    # On AWS leave s3_endpoint_url empty: default endpoint + IAM role.
    s3_endpoint_url: str | None = "http://localhost:8333"
    s3_bucket: str = "analytica-data"
    s3_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # Local cache of immutable Parquet versions (safe to delete at any time).
    cache_dir: str = "/tmp/analytica-cache"

    # Auth
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14

    # Limits (design 1.7)
    max_upload_mb: int = 200
    max_rows: int = 2_000_000
    preview_sample_rows: int = 1000

    # Chat (Phase 4). Chat endpoints return 503 until a key is configured.
    gemini_api_key: str | None = None
    chat_model: str = "gemini-3.5-flash"
    chat_effort: str = "medium"  # low | medium | high | xhigh | max
    chat_max_tokens: int = 16000

    # OAuth sign-in. A provider is offered only when both values are set.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    # Public URL of the app (OAuth redirects come back to <this>/api/v1/auth/oauth/...).
    public_app_url: str = "http://localhost:5173"
    # Comma-separated emails that become admins when they sign in.
    admin_emails: str = ""
    # USD per million tokens, for the admin cost estimate.
    # Gemini 2.5 Flash paid-tier list price; on the free tier the real cost is zero.
    llm_price_in_per_mtok: float = 0.30
    llm_price_out_per_mtok: float = 2.50

    # Run Celery tasks inline (tests).
    celery_eager: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def is_local(self) -> bool:
        return self.environment in ("local", "test")

    # In AWS the password comes from the RDS-managed secret; the URL is assembled here.
    db_host: str | None = None
    db_name: str = "analytica"
    db_user: str = "analytica"
    db_password: str | None = None

    @model_validator(mode="after")
    def _assemble_database_url(self) -> "Settings":
        if self.db_host and self.db_password:
            from urllib.parse import quote

            self.database_url = (
                f"postgresql+psycopg://{quote(self.db_user)}:{quote(self.db_password, safe='')}"
                f"@{self.db_host}:5432/{self.db_name}?sslmode=require"
            )
        return self

    @model_validator(mode="after")
    def _no_dev_secret_outside_local(self) -> "Settings":
        if not self.is_local and self.jwt_secret == _DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set outside local/test environments")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
