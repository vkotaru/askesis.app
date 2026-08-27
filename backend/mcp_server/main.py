"""Entry point for the MCP service. `uvicorn mcp_server.main:app`.

Kept separate from `server.py` so that importing the server for a test does not
read the environment or install a verifier.
"""

from __future__ import annotations

import logging
import os

from mcp_server.config import load
from mcp_server.server import AskesisTokenVerifier, StaticTokenVerifier, build_app

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

config = load()

# OAuth is the normal path. MCP_DEV_TOKEN remains as a local testing escape
# hatch for exercising the tools without walking the whole flow — it bypasses
# OAuth entirely, so it is opt-in by an env var production never sets and it
# announces itself in the log every boot.
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
    verifier = AskesisTokenVerifier(config)

app = build_app(config, verifier)
