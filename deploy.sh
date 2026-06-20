#!/usr/bin/env bash
# Deploy / update Askesis on your home server.
# Pulls the latest code, rebuilds the image, and restarts the stack.
#
# First-time setup:
#   cp .env.example .env && $EDITOR .env     # fill in secrets + TS_AUTHKEY
#   ./deploy.sh
#   # → https://askesis.<your-tailnet>.ts.net  (the Tailscale sidecar serves HTTPS)
set -euo pipefail
cd "$(dirname "$0")"

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

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Stopping current containers"
$DC down

echo "==> Building & starting"
$DC up -d --build

echo "==> Status"
$DC ps
echo
echo "App is served on the tailnet by the Tailscale sidecar (hostname 'askesis')."
echo "Open:  https://askesis.<your-tailnet>.ts.net"
echo "First run: check 'docker compose logs tailscale' to confirm it joined + got a cert."
