"""Application configuration.

All runtime configuration is environment-driven. Nothing in this module reads
secrets from source code. See .env.example and docs/deployment.md for the
documented variables.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "development", "demo", "staging", "production"]
AuthMode = Literal["demo", "required"]
PipelineMode = Literal["background", "inline"]

_IS_VERCEL = bool(os.getenv("VERCEL"))


class Settings(BaseSettings):
    """Typed application settings (pydantic-settings, env prefix optional)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    # --- Application identity -------------------------------------------------
    app_name: str = "ShramAI Inspector API"
    app_version: str = "1.0.0"
    app_env: Environment = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # --- Persistence ----------------------------------------------------------
    # Production must use a durable PostgreSQL URL; SQLite is for local/demo.
    database_url: str = "sqlite:///./shramai.db"
    # Convenience for ephemeral/demo deployments: create tables at startup
    # instead of running migrations. Must stay False in production.
    db_auto_create: bool | None = None  # None => auto (True for sqlite only)

    # --- Storage --------------------------------------------------------------
    # local: development/demo only (demo-grade durability). s3: private
    # S3-compatible object storage (AWS S3, MinIO, R2, ...) for production.
    # Credentials are read from the environment only — never hard-coded.
    storage_dir: str = "./storage"
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = ""  # empty = AWS; set for MinIO/R2/Spaces endpoints
    s3_region: str = ""  # empty = botocore default resolution
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""  # env only; never logged, never serialised
    s3_session_token: str = ""
    s3_server_side_encryption: str = ""  # e.g. AES256 or aws:kms
    # Downloads stream through the authorised API by default (no URLs at all).
    # When true, the download endpoint redirects to a short-lived presigned GET.
    s3_presigned_downloads: bool = False
    s3_presign_ttl_seconds: int = Field(default=300, ge=30, le=3600)

    # --- Upload and extraction limits ------------------------------------------
    max_upload_mb: int = Field(default=25, ge=1, le=200)
    max_request_body_mb: int = Field(default=30, ge=1, le=250)
    max_pdf_pages_text: int = Field(default=60, ge=1, le=500)
    max_pages_ocr: int = Field(default=15, ge=1, le=60)
    ocr_dpi_scale: float = Field(default=2.0, ge=1.0, le=4.0)
    max_extract_chars: int = Field(default=500_000, ge=10_000)

    # --- HTTP -------------------------------------------------------------------
    allowed_origins: str = ""  # comma-separated; empty => same-origin only
    trust_proxy_headers: bool = False  # enable behind a TLS-terminating proxy

    # --- Authentication ---------------------------------------------------------
    # demo: a virtual demo principal is injected on every request (public demo).
    # required: cookie sessions with organisational users and roles.
    # oidc: cookie sessions created via SSO (authorization-code flow + PKCE);
    # the session/authorisation machinery below is identical to `required`.
    auth_mode: AuthMode = "demo"
    session_ttl_minutes: int = Field(default=7 * 24 * 60, ge=10)
    bootstrap_admin_email: str = ""
    bootstrap_admin_name: str = "Chief Inspector"
    bootstrap_admin_password: str = ""
    demo_org_name: str = "Inspectorate Demo Organisation"
    demo_user_name: str = "Demo Inspector"

    # --- OIDC / enterprise SSO (auth_mode=oidc) ---------------------------------
    # Provider-agnostic (Keycloak, Entra ID, Okta, Google, Auth0, ...). Secrets
    # come from the environment only — never source, never logs.
    oidc_issuer: str = ""  # e.g. https://idp.example.com/realms/shramai
    oidc_client_id: str = ""
    oidc_client_secret: str = ""  # confidential client; env only
    oidc_redirect_uri: str = ""  # absolute callback URL, https in production
    oidc_scopes: str = "openid email profile"
    # New SSO users join this organisation with this role (claim-based role
    # mapping is a deliberate extension point, not silently trusted).
    oidc_org_name: str = "Inspectorate Organisation"
    oidc_default_role: str = "inspector"
    # Signs the OIDC state/nonce/PKCE challenge cookie. Empty = derived from
    # the client secret with domain separation (still env-only).
    oidc_state_secret: str = ""
    # Keep the password login endpoint as a break-glass admin path.
    oidc_local_login_fallback: bool = True
    # Where the callback sends the browser (relative path only, no open redirect).
    oidc_post_login_redirect: str = "/"
    oidc_http_timeout_seconds: float = Field(default=10, ge=1, le=60)
    oidc_token_leeway_seconds: int = Field(default=60, ge=0, le=600)

    # --- Malware scanning -----------------------------------------------------
    # off: explicit development/demo mode (documents marked skipped; forbidden
    # in production via a startup check). enforcing: a clamd scanner must be
    # configured and reachable; failures fail CLOSED (uploads rejected).
    malware_scan_mode: Literal["off", "enforcing"] = "off"
    clamd_host: str = ""  # clamd TCP host; empty = not configured
    clamd_port: int = Field(default=3310, ge=1, le=65535)
    malware_scan_timeout_seconds: float = Field(default=10, ge=1, le=120)
    malware_scan_stream_chunk: int = Field(default=65536, ge=4096, le=1048576)

    # --- Background pipeline -----------------------------------------------------
    pipeline_mode: PipelineMode = "background"
    pipeline_concurrency: int = Field(default=2, ge=1, le=16)

    # --- Rate limiting (per instance; use a gateway/Redis for multi-instance) ----
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = Field(default=240, ge=10)
    rate_limit_upload_per_minute: int = Field(default=30, ge=1)
    rate_limit_auth_per_minute: int = Field(default=10, ge=1)

    # --- AI provider ---------------------------------------------------------------
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_timeout_seconds: float = Field(default=45, ge=1, le=300)
    ai_input_char_limit: int = Field(default=60_000, ge=1_000)
    retrieval_char_limit: int = Field(default=6_000, ge=100)

    # --- Knowledge base --------------------------------------------------------------
    knowledge_dir: str = ""  # empty => repo-relative data/knowledge when present

    @field_validator("log_level")
    @classmethod
    def _norm_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production or (self.trust_proxy_headers and _IS_VERCEL)

    @property
    def effective_auto_create(self) -> bool:
        if self.db_auto_create is not None:
            return self.db_auto_create
        return self.is_sqlite

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]


def _apply_ephemeral_overrides(settings: Settings) -> Settings:
    """Ephemeral platforms (e.g. Vercel containers) get writable /tmp paths."""
    if not _IS_VERCEL:
        return settings
    if settings.database_url.startswith("sqlite:///./"):
        settings.database_url = "sqlite:////tmp/shramai.db"
    if settings.storage_dir == "./storage":
        settings.storage_dir = "/tmp/shramai-storage"
    return settings


@lru_cache
def get_settings() -> Settings:
    return _apply_ephemeral_overrides(Settings())


settings = get_settings()
