#!/usr/bin/env bash
# The only thing the deploy SSH key may run. sshd calls this as a forced command
# (authorized_keys `command="…/scripts/deploy-gate.sh",restrict`), puts what the
# client asked for in SSH_ORIGINAL_COMMAND, and gives the key no shell, no pty
# and no forwarding. Anything not listed below is refused. Same pattern as the
# other apps on this box; the dev machine's ~/.ssh/config names the host
# `askesis-deploy` with its own key.
#
#   ssh askesis-deploy deploy             # latest vX.Y.Z tag (deploy.sh's default)
#   ssh askesis-deploy deploy v2.24.2     # a specific release, or `main`
#   ssh askesis-deploy status             # checkout, container states, health
#   ssh askesis-deploy logs [app|mcp|db|tailscale|tailscale-mcp] [lines]
#   ssh askesis-deploy health             # GET /health and /healthz from inside
#
# Install (once, on the server, from this checkout):
#   echo "command=\"$PWD/scripts/deploy-gate.sh\",restrict <public key>" >> ~/.ssh/authorized_keys
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# COMPOSE_PROFILES=mcp lives in .env, which compose reads from the project dir;
# --env-file makes that explicit for `ps`/`logs` so the mcp services show up.
DC="docker compose --env-file .env"

# Split on whitespace only; the words are matched against fixed patterns below
# and never handed to a shell.
read -r -a args <<<"${SSH_ORIGINAL_COMMAND:-}"

refuse() {
  echo "deploy-gate: refused: ${SSH_ORIGINAL_COMMAND:-<none>}" >&2
  echo "allowed: deploy [vX.Y.Z|main] | status | logs [service] [lines] | health" >&2
  exit 2
}

case "${args[0]:-}" in
  deploy)
    [ "${#args[@]}" -le 2 ] || refuse
    if [ "${#args[@]}" -eq 2 ]; then
      ref="${args[1]}"
      [[ "$ref" == main || "$ref" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || refuse
      exec ./deploy.sh "$ref"
    fi
    exec ./deploy.sh
    ;;
  status)
    [ "${#args[@]}" -eq 1 ] || refuse
    echo "checkout: $(git describe --tags --always) ($(git rev-parse --abbrev-ref HEAD))"
    $DC ps -a 2>/dev/null || echo "(docker compose ps failed)"
    ;;
  logs)
    svc="${args[1]:-app}"
    lines="${args[2]:-100}"
    [ "${#args[@]}" -le 3 ] || refuse
    [[ "$svc" =~ ^(app|mcp|db|tailscale|tailscale-mcp)$ ]] || refuse
    [[ "$lines" =~ ^[0-9]{1,4}$ ]] || refuse
    exec $DC logs --no-color --tail="$lines" "$svc" 2>/dev/null
    ;;
  health)
    # From inside the containers, over the Unix sockets -- no network path to
    # the app exists from the host, by design. Reports the status code only.
    [ "${#args[@]}" -eq 1 ] || refuse
    for pair in "app:/health" "mcp:/healthz"; do
      svc="${pair%%:*}"; path="${pair#*:}"
      code="$($DC exec -T "$svc" python -c "
import os, http.client, socket
class C(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX); self.sock.connect(os.environ.get('APP_SOCKET') or os.environ.get('MCP_SOCKET'))
c = C('localhost'); c.request('GET', '$path'); print(c.getresponse().status)" 2>/dev/null || echo "no answer")"
      echo "$svc $path -> $code"
    done
    ;;
  *)
    refuse
    ;;
esac
