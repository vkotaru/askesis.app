from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite:///./askesis.db"
    secret_key: str = "change-me-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_emails: list[str] = []
    dev_mode: bool = False  # Must explicitly enable in .env for development
    cors_origins: list[str] = ["http://localhost:5173"]  # Override in production
    token_expire_hours: int = 2  # Short-lived tokens

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
