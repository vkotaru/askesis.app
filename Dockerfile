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

# Documentation only — nothing is published, and in the deployed configuration
# there is no TCP listener at all (see the CMD below).
EXPOSE 8000

# Migrate, seed the shared food list (best-effort), then serve.
#
#   APP_SOCKET set   -> listen on a Unix socket; no TCP port exists anywhere.
#   APP_SOCKET unset -> the old loopback TCP bind, kept so the image still runs
#                       standalone (plain `docker run`) for debugging.
#
# WHY A SOCKET. This container shares the Tailscale sidecar's network namespace
# (network_mode: service:tailscale), and in userspace mode tailscaled's netstack
# rewrites every inbound tailnet connection to 127.0.0.1 with the PORT UNCHANGED
# and no allowlist. The bind address therefore cannot close a port — loopback is
# exactly where it forwards. v1.2.5 changed 0.0.0.0 -> 127.0.0.1 for that reason
# and http://<tailnet-ip>:8000 still answered. The only way to close it is to
# have nothing listening on TCP, so netstack's dial fails and the peer gets RST.
#
# [ -S ] GUARDS THE rm. uvicorn unlinks the socket itself on a clean shutdown, so
# this only matters when a SIGKILL or power loss leaves a stale file that
# create_unix_server() would refuse to bind over. Unguarded, `rm -f $APP_SOCKET`
# is an unbounded delete running on every boot, in a container that also mounts
# ./data/uploads — so test that it IS a socket before unlinking.
#
# --forwarded-allow-ips MUST be '*' on the socket path. Over a UDS getpeername()
# returns a str, so uvicorn's get_remote_addr() returns None and
# ProxyHeadersMiddleware evaluates `None in {"127.0.0.1"}` -> False, silently
# dropping every X-Forwarded-* header with no error and no log line (uvicorn
# 0.27.0 has no "unix" sentinel for this flag). '*' is safe HERE because the only
# thing that can open the socket is a process with filesystem access to the
# mount, and Tailscale Serve Sets — not appends — the forwarded headers.
#   PRECONDITION: Serve sets X-Forwarded-Proto only when the inbound leg is TLS,
#   and never Dels it. That holds while serve.json declares only TCP.443.HTTPS;
#   adding a plain-HTTP handler would let a client's own value through.
#
# Serve also rewrites Host to "localhost" for unix targets (the real value stays
# in X-Forwarded-Host). Nothing reads Host today — anything added later that
# does, e.g. TrustedHostMiddleware, needs to know.
CMD ["sh", "-c", "python -m alembic upgrade head && (python seed_foods.py || echo 'seed skipped') && if [ -n \"$APP_SOCKET\" ]; then if [ -S \"$APP_SOCKET\" ]; then rm -f \"$APP_SOCKET\"; fi; exec python -m uvicorn app.main:app --uds \"$APP_SOCKET\" --proxy-headers --forwarded-allow-ips='*'; else exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='127.0.0.1'; fi"]
