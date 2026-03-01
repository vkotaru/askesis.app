from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import auth, daily_log, nutrition, activities, settings

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Askesis", version="0.1.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(daily_log.router, prefix="/api/daily-log", tags=["daily-log"])
app.include_router(nutrition.router, prefix="/api/nutrition", tags=["nutrition"])
app.include_router(activities.router, prefix="/api/activities", tags=["activities"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])


@app.get("/health")
def health_check():
    return {"status": "healthy"}
