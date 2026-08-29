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
# 3.12, not 3.11: garminconnect requires >=3.12 from 0.3.3 onward, and pinning
# back to 0.3.2 to stay on 3.11 would mean an older client of a library that
# already tracks a moving target (see app/garmin.py). Keep this in step with
# backend/venv — the checks in scripts/release.sh run against that venv, so a
# version skew between the two means "verified locally" says nothing about
# whether the image can even build.
FROM python:3.12-slim AS app
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

# Documentation only — nothing is published, and the bind below is loopback.
EXPOSE 8000

# Migrate, seed the shared food list (best-effort), then serve.
#
# --host 127.0.0.1, NOT 0.0.0.0. This container shares the Tailscale sidecar's
# network namespace (network_mode: service:tailscale in docker-compose.yml), so
# 0.0.0.0 binds the *tailnet interface* too — which put a second, plain-HTTP
# door on the app at http://<tailnet-ip>:8000, alongside the intended HTTPS one
# that Serve proxies to loopback on 443. Both doors required a login, but only
# one was meant to exist. Serve reaches us over loopback, so binding loopback
# costs nothing and closes the other one.
#
# --forwarded-allow-ips is loopback for the same reason. It tells uvicorn whose
# X-Forwarded-* headers to believe, and those headers decide what the app thinks
# the scheme, host and client IP are. It used to be '*', justified by the claim
# that only the loopback Serve proxy could reach this port — which the bind above
# made untrue. Naming loopback explicitly makes the justification true by
# construction rather than by assumption.
CMD ["sh", "-c", "python -m alembic upgrade head && (python seed_foods.py || echo 'seed skipped') && exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='127.0.0.1'"]
