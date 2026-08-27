"""Configuration and the guards that must hold before this process serves anything.

Every check here fails closed at import time. This is the only Askesis process
that will face the public internet, so a misconfiguration must stop the
container rather than quietly serve with a weaker posture than intended.
"""

from __future__ import annotations

import os
import sys

from app.config import get_settings


class MCPConfigError(RuntimeError):
    """A configuration state this process must not start in."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MCPConfigError(f"{name} is required.")
    return value


class MCPConfig:
    """Resolved settings, validated once at import."""

    def __init__(self) -> None:
        app_settings = get_settings()

        # ── Guard 1: DEV_MODE is a total auth bypass ────────────────────────
        # In the app it short-circuits get_current_user and returns a synthetic
        # dev@askesis.local user. On a publicly reachable endpoint that is a
        # full data breach requiring no attacker skill, so it is not a setting
        # here — it is a refusal to start.
        if app_settings.dev_mode:
            raise MCPConfigError(
                "DEV_MODE is true. The MCP service is internet-facing and "
                "DEV_MODE disables authentication entirely; refusing to start."
            )

        # ── Guard 2: token secret must not be the app's cookie key ──────────
        # SECRET_KEY signs the app's session cookies. If this process signed
        # MCP tokens with it, a token leaked from Anthropic's side — or minted
        # by a compromised MCP container — would be forgeable into an app
        # session. They must be different keys with different blast radii.
        #
        # Note this process needs SECRET_KEY set to *something* regardless:
        # app/database.py calls get_settings() at module scope and sys.exit(1)s
        # on the placeholder. Give the container its own throwaway value.
        self.token_secret = _require("MCP_TOKEN_SECRET")
        if self.token_secret == app_settings.secret_key:
            raise MCPConfigError(
                "MCP_TOKEN_SECRET must differ from SECRET_KEY. Sharing them "
                "would make an MCP token forgeable into an app session cookie."
            )
        if len(self.token_secret) < 32:
            raise MCPConfigError(
                "MCP_TOKEN_SECRET is too short; use `openssl rand -hex 32`."
            )

        # ── Public identity ────────────────────────────────────────────────
        # The canonical URI a client is told to use. RFC 8707 audience checks
        # compare against this exactly, and Claude requires the protected-
        # resource `resource` to match the URL typed into the connector dialog
        # character for character — a trailing slash breaks it, and the symptom
        # is a generic connection error with nothing useful in any log.
        self.public_origin = _require("MCP_PUBLIC_ORIGIN").rstrip("/")
        if not self.public_origin.startswith("https://"):
            raise MCPConfigError(
                f"MCP_PUBLIC_ORIGIN must be https://, got {self.public_origin!r}"
            )
        self.resource_url = f"{self.public_origin}/mcp"

        # Where the login/consent screen lives. Defaults to the public origin so
        # the flow can be proven end-to-end first; moving it to the tailnet-only
        # listener is one env var. See the plan's staging section.
        self.authorize_origin = (
            os.environ.get("MCP_AUTHORIZE_ORIGIN", "").strip().rstrip("/")
            or self.public_origin
        )

        # Hosts this server answers on, and origins allowed to reach it. The
        # SDK's default arms rebinding protection against localhost only, so an
        # unconfigured deploy rejects everything with a bare 421 — plain text,
        # not JSON-RPC, so the client shows a generic transport error and the
        # real hostname appears only in our log.
        host = self.public_origin.removeprefix("https://")
        self.allowed_hosts = [host, f"{host}:443"]
        self.allowed_origins = ["https://claude.ai", "https://claude.com"]

        self.scope = "askesis:read"


def load() -> MCPConfig:
    """Build the config, or exit non-zero with a readable reason."""
    try:
        return MCPConfig()
    except MCPConfigError as exc:
        print(f"[MCP CONFIG ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
