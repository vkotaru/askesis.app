from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite:///./askesis.db"
    secret_key: str = "change-me-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_emails: list[str] = []
    dev_mode: bool = True  # Skip OAuth in development

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
