#!/usr/bin/env bash
# Deploy / update Askesis on your home server.
#
# By default this deploys the LATEST RELEASE TAG (vX.Y.Z), not the tip of main —
# unreleased work must never reach the server by accident. Pass a ref to override.
#
#   ./deploy.sh            # highest vX.Y.Z tag  (the normal case)
#   ./deploy.sh v0.2.0     # a specific release  (the rollback path)
#   ./deploy.sh main       # tip of main, deliberately (continuous deploy)
#
# First-time setup:
#   cp .env.example .env && $EDITOR .env     # fill in secrets + TS_AUTHKEY
#   ./deploy.sh
#   # → https://askesis.<your-tailnet>.ts.net  (the Tailscale sidecar serves HTTPS)
#
# Rollback caveat: this runs `alembic upgrade head` on every start (see the
# Dockerfile CMD). Rolling the CONTAINER back does NOT roll the DATABASE back.
# Read RELEASING.md before rolling back across a migration.
set -euo pipefail
cd "$(dirname "$0")"

REQUESTED="${1:-}"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run: cp .env.example .env  (then edit it)" >&2
  exit 1
fi

# docker compose (v2) vs legacy docker-compose
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: Docker Compose not found." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Refuse to clobber local edits. This box is a real machine someone may have
# poked at; `git checkout --detach` would silently discard staged/unstaged work.
# ---------------------------------------------------------------------------
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree is dirty — refusing to deploy." >&2
  echo "       Commit, stash or discard these first:" >&2
  git status --short >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# What is running right now (captured BEFORE anything moves).
# ---------------------------------------------------------------------------
CURRENT_SHA="$(git rev-parse HEAD)"
CURRENT_REF="$(git describe --tags --exact-match 2>/dev/null || git symbolic-ref --short -q HEAD || echo 'detached')"

echo "==> Fetching refs and tags"
git fetch --all --tags --prune

# ---------------------------------------------------------------------------
# Resolve what to deploy.
#   REF   — the human name we deploy under (a tag, or "main")
#   SHA   — the commit it points at
# ---------------------------------------------------------------------------
# Highest vX.Y.Z tag. `--sort=v:refname` is git's own version sort, so
# v0.10.0 > v0.9.0 (a lexical sort gets this backwards). The grep keeps
# release tags only — the historical v0.1.0-pre-simplify / v0.2.0-simplified
# checkpoints carry suffixes and are deliberately not release candidates.
# The trailing `|| true` matters: with `set -o pipefail`, grep finding nothing
# fails the whole pipeline, and `set -e` would kill the script before the
# "no release tag exists" message below ever printed.
release_tags() {
  git tag -l 'v*' --sort=v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true
}

latest_release_tag() {
  release_tags | tail -n 1
}

if [ -z "$REQUESTED" ]; then
  REF="$(latest_release_tag)"
  if [ -z "$REF" ]; then
    echo "ERROR: no release tag (vX.Y.Z) exists in this repo." >&2
    echo "       Cut one with ./scripts/release.sh X.Y.Z, or deploy main explicitly:" >&2
    echo "         ./deploy.sh main" >&2
    exit 1
  fi
  echo "==> No ref given; using the latest release tag: $REF"
elif [ "$REQUESTED" = "main" ]; then
  REF="main"
  echo "==> Deploying the tip of main (explicitly requested — this is NOT a release)"
elif git rev-parse -q --verify "refs/tags/$REQUESTED^{commit}" >/dev/null; then
  REF="$REQUESTED"
else
  echo "ERROR: tag '$REQUESTED' does not exist (after fetching)." >&2
  echo "       Known release tags:" >&2
  known="$(release_tags)"
  if [ -n "$known" ]; then
    printf '%s\n' "$known" | sed 's/^/         /' >&2
  else
    echo "         (none)" >&2
  fi
  echo "       Or deploy the tip of main with: ./deploy.sh main" >&2
  exit 1
fi

if [ "$REF" = "main" ]; then
  RESOLVE="origin/main"
else
  RESOLVE="refs/tags/$REF"
fi

SHA="$(git rev-parse --verify "${RESOLVE}^{commit}")"
SHORT_SHA="$(git rev-parse --short "$SHA")"
TARGET_VERSION="$(git show "${SHA}:VERSION" 2>/dev/null | tr -d '[:space:]' || echo 'unknown')"

# ---------------------------------------------------------------------------
# Say exactly what is about to happen, before anything destructive.
# ---------------------------------------------------------------------------
echo
echo "    deploying:  $REF  ($SHORT_SHA)  VERSION=$TARGET_VERSION"
if [ "$SHA" = "$CURRENT_SHA" ]; then
  echo "    currently:  same commit — this is a rebuild, not a change"
else
  echo "    currently:  $CURRENT_REF  ($(git rev-parse --short "$CURRENT_SHA"))"
fi
echo

echo "==> Checking out $REF"
# Detached on purpose: a tag is not a branch, and `git pull` fails on a detached
# HEAD. Everything above fetches explicitly so there is never anything to pull.
git checkout --detach "$SHA" --

# Read by docker-compose.yml as build args and baked into the image as env, so
# the running container can report its own commit via GET /api/version.
export GIT_SHA="$SHA"
export GIT_REF="$REF"

# Build BEFORE stopping anything. A failed build then leaves the current
# deployment running instead of taking the site down and stranding it on a
# freshly checked-out commit with no automatic recovery.
echo "==> Building  (GIT_REF=$GIT_REF GIT_SHA=$SHORT_SHA)"
if ! $DC build; then
  echo
  echo "ERROR: build failed. The running deployment was left untouched." >&2
  echo "       The working tree is now at $REF ($SHORT_SHA); re-run with a" >&2
  echo "       known-good tag to put it back." >&2
  exit 1
fi

echo "==> Restarting"
$DC down
$DC up -d

# ---------------------------------------------------------------------------
# Smoke test.
#
# Nothing else in this repo makes an HTTP request: CI, scripts/release.sh and
# the image build all stop at `import app.main` + `alembic upgrade head`, and
# release.sh overrides the CMD entirely — so the uvicorn invocation is never
# executed by any gate. A wrong socket path, a sidecar too old for `unix:`
# targets, or an APP_SOCKET that never reached the container would all produce
# a 502 on every request with nothing anywhere saying so, and be discovered by
# a human opening the app. Two assertions close that gap.
# ---------------------------------------------------------------------------
echo "==> Smoke test"

smoke_fail() {
  echo >&2
  echo "ERROR: $1" >&2
  echo >&2
  echo "  Logs:       $DC logs --tail=50 app" >&2
  echo "              $DC logs --tail=50 tailscale" >&2
  echo "  Serve tgt:  $DC exec tailscale tailscale serve status" >&2
  if [ "$CURRENT_REF" != "detached" ]; then
    echo "  Roll back:  ./deploy.sh $CURRENT_REF" >&2
  else
    echo "  Roll back:  ./deploy.sh <last-good-tag>" >&2
  fi
  echo >&2
  echo "  NOTE: APP_SOCKET (docker-compose.yml) and the Proxy target in" >&2
  echo "  tailscale/serve.json are one setting in two files — reverting either" >&2
  echo "  alone still 502s. And if you hand-edit them, deploy.sh will refuse to" >&2
  echo "  run while the tree is dirty, so undo them before rolling back:" >&2
  echo "      git checkout -- docker-compose.yml tailscale/serve.json" >&2
  exit 1
}

# 1. The HTTPS front door serves the commit we just deployed.
#
# PUBLIC_URL is the tailnet origin (same hostname already written into
# CORS_ORIGINS). Optional: a fresh box may not have it yet and a deploy should
# still finish, so an unset value downgrades to a warning rather than failing.
PUBLIC_URL="$(grep -E '^[[:space:]]*PUBLIC_URL=' .env 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d "\"' " || true)"

if [ -n "${PUBLIC_URL:-}" ]; then
  got=""
  ok=""
  for _ in $(seq 1 30); do
    got="$(curl -fsS --max-time 5 "$PUBLIC_URL/api/version" 2>/dev/null | grep -o '"commit":"[^"]*"' | cut -d'"' -f4 || true)"
    if [ "$got" = "$SHA" ]; then ok=1; break; fi
    sleep 2
  done
  [ -n "$ok" ] || smoke_fail "$PUBLIC_URL did not serve $SHORT_SHA within 60s (saw: ${got:-no response})"
  echo "    ok: $PUBLIC_URL serves $SHORT_SHA"
else
  echo "    SKIPPED serving check — PUBLIC_URL not set in .env." >&2
  echo "    Add PUBLIC_URL=https://askesis.<your-tailnet>.ts.net to enable it." >&2
fi

# 2. There is no TCP listener. tailscaled (userspace) forwards ANY inbound
# tailnet port to 127.0.0.1 unchanged, so if :8000 answers, the socket branch
# did not take effect and the loopback TCP fallback is serving instead.
# Deliberately fails rather than skips when the IP cannot be read. A check that
# silently passes when it could not run is worse than no check — it reports
# "closed" whether or not the port is open, which is the exact failure this
# whole change exists to prevent.
TS_IP=""
for _ in $(seq 1 5); do
  TS_IP="$($DC exec -T tailscale tailscale ip -4 2>/dev/null | tr -d '\r' | head -n1 || true)"
  [ -n "$TS_IP" ] && break
  sleep 2
done
[ -n "$TS_IP" ] || smoke_fail "could not read the tailnet IP from the sidecar, so the port check could not run"

if curl -s --max-time 3 -o /dev/null "http://$TS_IP:8000/api/version" 2>/dev/null; then
  smoke_fail "http://$TS_IP:8000 is STILL REACHABLE — the app is listening on TCP, not the socket"
fi
echo "    ok: http://$TS_IP:8000 refused"

echo "==> Status"
$DC ps
echo
echo "Deployed $REF ($SHORT_SHA), app version $TARGET_VERSION."
echo "App is served on the tailnet by the Tailscale sidecar (hostname 'askesis')."
echo "Open:  https://askesis.<your-tailnet>.ts.net"
echo "Check: curl -s https://askesis.<your-tailnet>.ts.net/api/version"
echo "First run: check 'docker compose logs tailscale' to confirm it joined + got a cert."
