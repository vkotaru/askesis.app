#!/bin/bash
# npm for this repo, whether or not node is installed on the machine.
#
# Mirrors backend/db.sh: a per-half helper that hides one piece of setup. Native
# npm is used when it exists, so this is a no-op on a machine with node; on one
# without, the same command runs in a container instead of failing.
#
# The container is defined in ../docker-compose.dev.yml — this script only picks
# a service and forwards arguments, so there is one definition of the toolchain
# rather than two that drift. You can equally type the compose command yourself:
#
#   docker compose -f docker-compose.dev.yml run --rm npm run check
#
# Usage:  ./npm.sh install
#         ./npm.sh run check
#         ./npm.sh run build
#         ./npm.sh run dev
#
# Env:
#   ASKESIS_FORCE_DOCKER  use the container even when npm is installed, e.g. to
#                         reproduce a CI failure against node 20

set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$FRONTEND_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_DIR/docker-compose.dev.yml"

if [ -z "${ASKESIS_FORCE_DOCKER:-}" ] && command -v npm >/dev/null 2>&1; then
    cd "$FRONTEND_DIR"
    exec npm "$@"
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "npm.sh: neither npm nor docker is installed — install one of them." >&2
    exit 1
fi

# Compose cannot work out the calling uid on its own, and running as root would
# leave build/ and .svelte-kit/ unwritable by the next native build.
export DOCKER_UID="$(id -u)" DOCKER_GID="$(id -g)"

# `run dev` and `run preview` are long-running servers and need the host network
# for the API proxy to reach uvicorn; that is a separate service because
# network_mode cannot be overridden per invocation.
service=npm
case "${1:-}" in
    run)
        case "${2:-}" in
            dev | preview) service=vite ;;
        esac
        ;;
    dev | preview | start) service=vite ;;
esac

flags=()
if [ ! -t 0 ] || [ ! -t 1 ]; then
    # Without this, piping or running from a script fails with
    # "the input device is not a TTY".
    flags=(--no-TTY)
fi

if [ "$service" != vite ]; then
    exec docker compose -f "$COMPOSE_FILE" run --rm "${flags[@]}" "$service" "$@"
fi

# ── The dev server needs more care than `exec` ───────────────────────────────
#
# `docker compose run` does NOT stop its container when the client is killed —
# unlike `docker run`, which forwards the signal. run-dev.sh backgrounds this
# and kills it by PID on Ctrl-C, so without the trap below vite survives, keeps
# :5173, and the next ./run-dev.sh fails to bind. `--rm` does not save you:
# nothing ever asked the container to stop.
#
# So: a known name, and a trap that removes it however this script exits.
CONTAINER=askesis-vite

# No TTY regardless of whether one exists: run-dev.sh backgrounds this, and a
# backgrounded process holding a terminal is stopped by SIGTTIN the moment it
# reads stdin. Costs vite's keyboard shortcuts, which is the right trade for not
# wedging the dev loop.
flags=(--no-TTY)

# A container left behind by a hard kill (SIGKILL skips the trap) would other-
# wise collide on the name here rather than anywhere informative.
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# Backgrounded rather than exec'd, so the trap survives to run. The vite service
# already carries `command:`, but pass it through so `./npm.sh run preview` does
# what it says rather than silently running dev.
docker compose -f "$COMPOSE_FILE" run --rm --name "$CONTAINER" \
    "${flags[@]}" "$service" npm "$@" &
wait $!
