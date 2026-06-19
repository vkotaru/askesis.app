# syntax=docker/dockerfile:1
# Single image: builds the SvelteKit SPA, then serves it + the FastAPI API
# from one Python process (same-origin), mirroring the Railway/nixpacks build.

# ---- Stage 1: build the frontend (static SPA) ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
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
# FastAPI serves the built SPA from backend/static (see app/main.py).
COPY --from=frontend /app/frontend/build ./static

EXPOSE 8000

# Migrate, seed the shared food list (best-effort), then serve.
# --proxy-headers + --forwarded-allow-ips=* so HTTPS-only cookies and the
# OAuth redirect URL honor the X-Forwarded-Proto/Host set by Tailscale Serve
# (or any TLS-terminating reverse proxy) in front of the container.
CMD ["sh", "-c", "python -m alembic upgrade head && (python seed_foods.py || echo 'seed skipped') && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
