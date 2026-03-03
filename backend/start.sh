#!/bin/bash
# Local development start script
# For production, Railway uses nixpacks.toml

set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
