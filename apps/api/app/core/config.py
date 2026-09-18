from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
