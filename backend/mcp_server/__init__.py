"""The MCP connector service — a separate process from the Askesis app.

Runs from its own Dockerfile stage with its own dependency set
(``backend/requirements-mcp.txt``): no FastAPI, no Pillow, no Gemini SDK, no
Garmin client. It shares only the model layer (``app.models``, ``app.database``,
``app.units``, ``app.security``, ``app.provenance``) with the app.

This is the ONLY part of Askesis that faces the public internet. Nothing in
this package may import ``app.main`` or any module under ``app.routers`` —
doing so would pull FastAPI in and silently undo the dependency split that
keeps ``/auth/*`` and the SPA out of the internet-facing image.
"""
