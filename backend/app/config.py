import sys
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

    # File upload limits (in bytes)
    max_image_size: int = 50 * 1024 * 1024  # 50MB (iPhone photos can be 25MB+)
    max_csv_size: int = 10 * 1024 * 1024  # 10MB

    # Google Drive storage
    drive_folder_name: str = "Askesis Progress Photos"  # Folder name in user's Drive

    class Config:
        env_file = ".env"

    def validate_production(self) -> list[str]:
        """Validate settings for production deployment. Returns list of errors."""
        errors = []

        # Check for placeholder secret key
        if self.secret_key == "change-me-in-production":
            errors.append("SECRET_KEY is still the default placeholder - generate a secure key with: openssl rand -hex 32")

        # Warn about SQLite in production (but don't block - user might be testing)
        if not self.dev_mode and self.database_url.startswith("sqlite"):
            errors.append("WARNING: Using SQLite in production. Data will be lost on redeploy. Set DATABASE_URL to PostgreSQL.")

        return errors


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # Validate in production mode
    if not settings.dev_mode:
        errors = settings.validate_production()
        for error in errors:
            if error.startswith("WARNING:"):
                print(f"[CONFIG] {error}", file=sys.stderr)
            else:
                print(f"[CONFIG ERROR] {error}", file=sys.stderr)
                # Exit on critical errors (like missing secret key)
                if "SECRET_KEY" in error:
                    sys.exit(1)

    return settings
