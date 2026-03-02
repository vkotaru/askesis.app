#!/bin/bash
# Railway deployment start script
# Runs migrations before starting the server

set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
