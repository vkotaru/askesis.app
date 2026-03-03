import logging
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, daily_log, nutrition, activities, settings, measurements, photos, sharing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("askesis")

# Note: Database schema is managed by Alembic migrations
# Run `alembic upgrade head` before starting the server

app_settings = get_settings()
app = FastAPI(title="Askesis", version="0.1.0")


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
app.include_router(measurements.router, prefix="/api/measurements", tags=["measurements"])
app.include_router(photos.router, prefix="/api/photos", tags=["photos"])
app.include_router(sharing.router, prefix="/api/sharing", tags=["sharing"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# Serve frontend static files (must be last - catches all unmatched routes)
STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
