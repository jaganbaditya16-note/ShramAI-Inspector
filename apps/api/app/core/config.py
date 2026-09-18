import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_IS_VERCEL = bool(os.getenv("VERCEL"))


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./shramai.db"
    upload_dir: str = "./storage"
    max_upload_mb: int = Field(default=25, ge=1, le=100)
    allowed_origins: str = "http://localhost:3000"
    demo_auth_token: str = ""
    max_request_body_mb: int = Field(default=30, ge=1, le=100)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    vercel_runtime: bool = _IS_VERCEL

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
    )


settings = Settings()

if settings.vercel_runtime:
    if settings.database_url.startswith("sqlite:///./"):
        settings.database_url = "sqlite:////tmp/shramai.db"
    if settings.upload_dir == "./storage":
        settings.upload_dir = "/tmp/shramai-storage"
    settings.app_env = "production"
    if settings.allowed_origins == "http://localhost:3000":
        settings.allowed_origins = "*"
