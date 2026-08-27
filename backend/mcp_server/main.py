"""Entry point for the MCP service. `uvicorn mcp_server.main:app`.

Kept separate from `server.py` so that importing the server for a test does not
read the environment or install a verifier.
"""

from __future__ import annotations

import logging
import os
import sys

from mcp_server.config import load
from mcp_server.server import StaticTokenVerifier, build_app

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

config = load()

# Stage 2 only. A static token stands in for OAuth so the wire contract can be
# exercised before the OAuth layer exists. Opt-in by an env var production never
# sets, and loud in the log — this must not survive quietly into stage 3.
_dev_token = os.environ.get("MCP_DEV_TOKEN", "").strip()
if _dev_token:
    _dev_user = int(os.environ.get("MCP_DEV_USER_ID", "1"))
    logging.getLogger("askesis.mcp").warning(
        "MCP_DEV_TOKEN is set: serving with a STATIC token for user id %s. "
        "This bypasses OAuth entirely and must never be set on a public deploy.",
        _dev_user,
    )
    verifier = StaticTokenVerifier(_dev_token, _dev_user, config)
else:
    print(
        "[MCP] No token verifier configured. Set MCP_DEV_TOKEN for local "
        "stage-2 testing; the OAuth verifier arrives in stage 3.",
        file=sys.stderr,
    )
    raise SystemExit(1)

app = build_app(config, verifier)
