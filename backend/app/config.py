import sys
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# backend/ — the default uploads dir sits next to app/, and the Docker image
# bind-mounts the host's ./data/uploads over it.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./askesis.db"
    secret_key: str = "change-me-in-production"
    dev_mode: bool = False  # Must explicitly enable in .env for development
    # CORS allowed origins. The web app is served same-origin with the API, so
    # this only needs to cover local web dev (Vite). Production can extend it
    # via the CORS_ORIGINS env var if a cross-origin client is ever added.
    cors_origins: list[str] = [
        "http://localhost:5173",
    ]
    token_expire_hours: int = 720  # 30 days - stay logged in longer

    # External food databases
    usda_api_key: str = (
        ""  # Get free key at https://fdc.nal.usda.gov/api-key-signup.html
    )

    # File upload limits (in bytes)
    max_image_size: int = 50 * 1024 * 1024  # 50MB (iPhone photos can be 25MB+)
    max_csv_size: int = 10 * 1024 * 1024  # 10MB

    # Directory holding the cached Garmin Connect session (garmin_tokens.json,
    # written 0600 inside a 0700 dir by the client). An operator creates it once
    # with `scripts/garmin_sync.py --login`; syncs afterwards need no password,
    # so no Garmin credential is ever stored in .env or the database. Must be on
    # a persisted volume in Docker or every rebuild forces a re-login — and
    # Garmin rate-limits logins.
    garmin_tokenstore: str = str(_BACKEND_DIR / ".garminconnect")

    # Where progress/meal photos are written. Override with UPLOADS_DIR when the
    # container mounts storage elsewhere. app/storage.py resolves this once at
    # import and every stored path is relative to it.
    uploads_dir: str = str(_BACKEND_DIR / "uploads")

    class Config:
        env_file = ".env"
        # Tolerate keys we no longer read. pydantic-settings rejects unknown
        # keys from a dotenv file by default (unknown *env vars* it ignores),
        # so an operator .env still carrying GOOGLE_CLIENT_ID or ENCRYPTION_KEY
        # from before the Google removal would otherwise crash the app at
        # import time rather than being ignored.
        extra = "ignore"

    def validate_production(self) -> list[str]:
        """Validate settings for production deployment. Returns list of errors."""
        errors = []

        # Check for placeholder secret key
        if self.secret_key == "change-me-in-production":
            errors.append(
                "SECRET_KEY is still the default placeholder - generate a secure key with: openssl rand -hex 32"
            )

        # Warn about SQLite in production (but don't block - user might be testing)
        if not self.dev_mode and self.database_url.startswith("sqlite"):
            errors.append(
                "WARNING: Using SQLite in production. Data will be lost on redeploy. Set DATABASE_URL to PostgreSQL."
            )

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
