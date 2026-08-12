import logging
import os
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import (
    auth,
    daily_log,
    nutrition,
    activities,
    settings,
    measurements,
    photos,
    sharing,
    import_router,
    export,
    sync,
    report,
    training,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("askesis")

# Note: Database schema is managed by Alembic migrations
# Run `alembic upgrade head` before starting the server

app_settings = get_settings()


def _read_version() -> str:
    """Read the repo-root VERSION file — the single source of truth.

    The frontend inlines the same file at build time (see vite.config.ts), so
    the UI and the API can never disagree about what is deployed. Nothing
    derives this from git: .git is excluded from the Docker build context.
    """
    for candidate in (
        Path(__file__).parent.parent / "VERSION",  # in the image (COPY VERSION)
        Path(__file__).parent.parent.parent / "VERSION",  # repo checkout
    ):
        try:
            return candidate.read_text().strip()
        except OSError:
            continue
    return "unknown"


APP_VERSION = _read_version()

# Which commit/ref this image was built from. Baked in as build args by
# deploy.sh (see docker-compose.yml + Dockerfile) because .git is excluded from
# the build context. "unknown" whenever the image was built by hand or the app
# is running straight from a dev checkout.
GIT_SHA = os.environ.get("GIT_SHA") or "unknown"
GIT_REF = os.environ.get("GIT_REF") or "unknown"

app = FastAPI(title="Askesis", version=APP_VERSION)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing."""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    # Log request (skip health checks to reduce noise)
    if request.url.path != "/health":
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration_ms:.0f}ms"
        )

    return response


# CORS for frontend - origins configured via CORS_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(daily_log.router, prefix="/api/daily-log", tags=["daily-log"])
app.include_router(nutrition.router, prefix="/api/nutrition", tags=["nutrition"])
app.include_router(activities.router, prefix="/api/activities", tags=["activities"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(
    measurements.router, prefix="/api/measurements", tags=["measurements"]
)
app.include_router(photos.router, prefix="/api/photos", tags=["photos"])
app.include_router(sharing.router, prefix="/api/sharing", tags=["sharing"])
app.include_router(import_router.router, prefix="/api/import", tags=["import"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(report.router, prefix="/api/report", tags=["report"])
app.include_router(training.router, prefix="/api/training", tags=["training"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/version")
def version():
    """What is actually deployed. Unauthenticated on purpose — it exposes
    nothing but the version string, and being able to check it without a
    session is the entire point.

    `ref` is the git ref deploy.sh checked out: "v0.2.0" for a release,
    "main" for a deliberate continuous deploy, "unknown" for a hand-built
    image. The UI uses it to mark anything that is not exactly v<VERSION>.
    """
    return {"version": APP_VERSION, "commit": GIT_SHA, "ref": GIT_REF}


# Serve frontend static files with SPA fallback
STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    from fastapi.responses import FileResponse, JSONResponse

    # Mount static assets directories if they exist
    _app_dir = STATIC_DIR / "_app"
    if _app_dir.exists():
        app.mount("/_app", StaticFiles(directory=_app_dir), name="app-assets")

    # SPA fallback: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Never let an unmatched backend path fall through to the SPA shell.
        # Returning index.html with a 200 turns "this endpoint doesn't exist"
        # into "HTML where JSON was expected", which is a much harder bug to
        # read from the client side.
        first_segment = full_path.split("/", 1)[0]
        if first_segment in ("api", "auth"):
            return JSONResponse(
                status_code=404, content={"detail": f"Not Found: /{full_path}"}
            )

        # Security: prevent path traversal
        try:
            file_path = (STATIC_DIR / full_path).resolve()
            if not str(file_path).startswith(str(STATIC_DIR.resolve())):
                return FileResponse(STATIC_DIR / "index.html")
        except (ValueError, OSError):
            return FileResponse(STATIC_DIR / "index.html")

        # Try to serve the exact file first
        if file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(STATIC_DIR / "index.html")
