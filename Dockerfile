# syntax=docker/dockerfile:1
# Single image: builds the SvelteKit SPA, then serves it + the FastAPI API
# from one Python process (same-origin). This is the only supported deployment.

# ---- Stage 1: build the frontend (static SPA) ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Single source of truth for the version; vite.config.ts inlines it at build
# time. .git is not in the build context, so this file is the only way in.
COPY VERSION /app/VERSION
# Served same-origin by the backend, so no API host needs baking in here.
RUN npm run build   # -> /app/frontend/build  (adapter-static, SPA fallback)

# ---- Stage 2: Python runtime (API + built frontend) ----
FROM python:3.11-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app/backend

# psycopg2-binary and Pillow/pillow-heif ship manylinux wheels, so no apt build deps needed.
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ ./
# Same VERSION file the frontend was built with — app/main.py reads it for the
# OpenAPI version and GET /api/version.
COPY VERSION ./VERSION
# FastAPI serves the built SPA from backend/static (see app/main.py).
COPY --from=frontend /app/frontend/build ./static

# Which commit this image is. Declared this late on purpose: an ARG invalidates
# every layer after it, and these change on every deploy — keeping them below
# the pip install and the COPYs preserves the expensive cache.
ARG GIT_SHA=unknown
ARG GIT_REF=unknown
ENV GIT_SHA=$GIT_SHA \
    GIT_REF=$GIT_REF

EXPOSE 8000

# Migrate, seed the shared food list (best-effort), then serve.
# --proxy-headers + --forwarded-allow-ips=* so HTTPS-only cookies and the
# OAuth redirect URL honor the X-Forwarded-Proto/Host set by Tailscale Serve
# (or any TLS-terminating reverse proxy) in front of the container.
CMD ["sh", "-c", "python -m alembic upgrade head && (python seed_foods.py || echo 'seed skipped') && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
