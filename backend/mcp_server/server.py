"""The MCP endpoint: registers the read tools and owns the request boundary.

Thin on purpose. Everything that decides *what* the tools return lives in
`tools.py` and `queries.py`, which have no MCP dependency; this module is the
layer that turns them into protocol handlers and enforces what has to be true
at the edge.

**The SDK owns the protocol pedantry**, which is the main reason it is used
rather than a hand-rolled JSON-RPC dispatcher: POST-only with 405s on GET and
DELETE, sessionless under revision 2026-07-28 (no `Mcp-Session-Id` is minted or
honoured), the `MCP-Protocol-Version` / `Mcp-Method` / `Mcp-Name` header
mirroring and its `-32020` HeaderMismatch, `=?base64?...?=` decoding, `404` +
`-32601` for unknown methods, `UnsupportedProtocolVersionError`, and JSON-Schema
generation from type hints. Hand-writing that is ~400 lines and a spec re-read
every revision.

**The SDK's auth middleware runs before dispatch**, so an unauthenticated
request is refused at the door: nothing is parsed and no tool body executes.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import anyio
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError as SDKToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from app.database import SessionLocal
from mcp_server import oauth
from mcp_server import tools as T
from mcp_server.config import MCPConfig

logger = logging.getLogger("askesis.mcp")


# ── The identity boundary ────────────────────────────────────────────────────


def _current_user_id() -> int:
    """The account this request is acting for. The ONLY source of identity.

    No tool takes a `user_id` argument, so there is nowhere else a caller could
    influence which rows it sees. Coerced to `int` here rather than trusted:
    a JWT `sub` is conventionally a string, and `owned()`'s type guard is meant
    to be a backstop, not the thing that catches it every time.
    """
    token = get_access_token()
    if token is None:
        # Unreachable while the SDK's auth middleware is installed; treated as
        # a failure rather than a default, because "no identity" must never
        # resolve to "some identity".
        raise PermissionError("No authenticated subject on this request.")
    try:
        return int(token.subject)
    except (TypeError, ValueError) as exc:
        raise PermissionError(f"Malformed subject: {token.subject!r}") from exc


# ── The request boundary ─────────────────────────────────────────────────────


def _register(
    mcp: MCPServer, fn: Callable[..., dict[str, Any]], description: str
) -> None:
    """Expose one `tools.py` function as an MCP tool.

    Owns three things the tool functions deliberately do not:

    1. **Identity.** Resolved here and passed in; never an argument.
    2. **The session.** One per call, always closed. These are sync SQLAlchemy
       calls, so they run in a worker thread — on the event loop a slow query
       would stall every other in-flight MCP request.
    3. **Error containment.** Only `ToolError` text crosses the wire. Anything
       else is logged in full and reported generically, because SQLAlchemy's
       exception messages embed the failing SELECT *and* its bound parameters:
       one out-of-range id is enough to hand a caller a table's entire column
       list. That is a schema disclosure to whoever holds a token.
    """

    async def handler(**kwargs: Any) -> dict[str, Any]:
        user_id = _current_user_id()

        def run() -> dict[str, Any]:
            db = SessionLocal()
            try:
                return fn(db, user_id, **kwargs)
            finally:
                db.close()

        try:
            result = await anyio.to_thread.run_sync(lambda: run())
        except T.ToolError as exc:
            # A caller error whose text is written to be read by a model
            # ("Range is 365 days; the maximum is 180"). The SDK's ToolError is
            # the one exception type whose message it forwards; everything else
            # it deliberately replaces with a generic string. So the boundary
            # between "tell the model" and "withhold" is this raise.
            raise SDKToolError(str(exc)) from None
        except PermissionError:
            raise
        except Exception:
            # Logged in full here for the audit trail, then re-raised so the SDK
            # wraps it as UnexpectedToolError and withholds the text. That
            # matters: SQLAlchemy embeds the failing SELECT and its bound
            # parameters in the message, so one bad id would otherwise hand the
            # caller a table's entire column list.
            logger.exception(
                "tool %s failed for subject %s (arg keys=%s)",
                fn.__name__,
                user_id,
                sorted(kwargs),  # keys only — values can be free text
            )
            raise
        logger.info("tool %s ok for subject %s", fn.__name__, user_id)
        return result

    handler.__name__ = fn.__name__
    handler.__doc__ = description
    # Signature drives the generated JSON Schema, minus the two the SDK must
    # never see.
    sig = inspect.signature(fn)
    handler.__signature__ = sig.replace(  # type: ignore[attr-defined]
        parameters=[p for n, p in sig.parameters.items() if n not in ("db", "user_id")]
    )
    handler.__annotations__ = {
        n: p.annotation
        for n, p in sig.parameters.items()
        if n not in ("db", "user_id") and p.annotation is not inspect.Parameter.empty
    }
    mcp.tool(name=fn.__name__)(handler)


#: One sentence per tool telling the model the unit rule, because a tool
#: description is the only place it will read it.
_UNITS = "All numbers are metric and every field names its unit (weight_kg, distance_km, waist_cm)."

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_profile": (
        "Who this account belongs to, their targets (calories, protein, weekly "
        "run/bike distance, planned disciplines), their display-unit preferences, "
        f"and what date ranges of data exist. Call this first to orient. {_UNITS}"
    ),
    "get_daily_summary": (
        "One row per day joining the daily log, nutrition, meal calories and an "
        "activity roll-up, over a date range (max 180 days). The main tool for "
        "trends and 'how was <period>' questions. Days with no data are returned "
        f"as explicit nulls rather than omitted. {_UNITS}"
    ),
    "get_weekly_review": (
        "A Monday-Sunday review: distance per discipline against the weekly "
        "targets, which planned disciplines were done and which missed, calories "
        "and protein against target, mean sleep and steps, and the weight change "
        f"over the week. Defaults to the current week. {_UNITS}"
    ),
    "list_activities": (
        "Workouts in a date range, each with a server-resolved discipline (run, "
        "bike, swim, hike, strength, calisthenics, stretch), duration, distance "
        f"and whether it came from a device or was entered by hand. {_UNITS}"
    ),
    "get_activity": (
        f"One workout in full, including its individual exercise sets. {_UNITS}"
    ),
    "get_measurements": (
        "Body measurements with the change since the previous entry. Pass "
        f"latest_only=true for just the most recent. {_UNITS}"
    ),
    "get_meals": (
        "Meals in a date range with their calories and constituent foods. "
        "Calories are the logged figure, or computed from the food items when "
        f"the meal has none. {_UNITS}"
    ),
    "get_training_plan": (
        "The active race training plan: race date and distance, planned versus "
        f"completed workouts per week, and the next 7 days. {_UNITS}"
    ),
}


def build_server(config: MCPConfig, verifier: TokenVerifier) -> MCPServer:
    """Assemble the MCP server with its tools and auth settings."""
    mcp = MCPServer(
        name="askesis",
        title="Askesis",
        description="Personal health and training history: daily logs, nutrition, activities, measurements and training plans. Read-only.",
        version="0.1.0",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(config.public_origin),
            resource_server_url=AnyHttpUrl(config.resource_url),
            required_scopes=[config.scope],
        ),
    )
    for name, fn in T.TOOLS.items():
        _register(mcp, fn, TOOL_DESCRIPTIONS[name])
    return mcp


def build_app(config: MCPConfig, verifier: TokenVerifier) -> Starlette:
    """The ASGI app to serve.

    The mounted sub-application's lifespan never runs, so the session manager
    has to be entered by the host app: without this the first request to /mcp
    dies with `RuntimeError: Task group is not initialized`.
    """
    mcp = build_server(config, verifier)

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=config.allowed_hosts,
        allowed_origins=config.allowed_origins,
    )

    inner = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        # Plain JSON rather than SSE: every tool here is a bounded, indexed read
        # that returns in milliseconds, so a stream buys nothing and costs a
        # connection held open through Funnel.
        json_response=True,
        transport_security=transport_security,
        # 4 MB default is far more than any request here needs; a tools/call
        # body is a few hundred bytes.
        max_request_body_size=64 * 1024,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    # Mount("/") matches everything, so every real route must be listed before
    # it. The protected-resource discovery document is served by the SDK from
    # AuthSettings and lives inside the mount.
    routes = [
        Route("/mcp", _reject_legacy, methods=["GET", "DELETE"]),
        Route("/healthz", oauth.healthz, methods=["GET"]),
        Route(
            "/.well-known/oauth-authorization-server",
            oauth.authorization_server_metadata(config),
            methods=["GET"],
        ),
        # An alias some clients probe before the RFC 8414 path.
        Route(
            "/.well-known/openid-configuration",
            oauth.authorization_server_metadata(config),
            methods=["GET"],
        ),
        Route("/register", oauth.register(config), methods=["POST"]),
        Route("/authorize", oauth.authorize(config), methods=["GET", "POST"]),
        Route("/token", oauth.token(config), methods=["POST"]),
        Route("/revoke", oauth.revoke(config), methods=["POST"]),
        Mount("/", app=inner),
    ]

    # The SDK's Host allowlist covers the mounted MCP app only; the OAuth routes
    # sit outside that mount, so the outer app needs its own. The main app has
    # neither today — fine while it is tailnet-only, not fine once this is
    # public.
    middleware = [
        Middleware(
            TrustedHostMiddleware,
            allowed_hosts=[*config.allowed_hosts, "testserver"],
        )
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)


async def _reject_legacy(request: Request) -> Response:
    """Refuse the deprecated GET stream and DELETE session-termination.

    Revision 2026-07-28 removed both: there is no GET stream and there are no
    protocol-level sessions. The SDK still serves the older revisions, so a GET
    with no `MCP-Protocol-Version` header is treated as a legacy client and
    **mints a session** — observed doing exactly that. For a publicly reachable
    endpoint that is deprecated surface nobody needs: Claude speaks the modern
    revision, which never issues either verb.

    The spec's own guidance for a server that supports only this revision is to
    answer both with 405, which is what this does.
    """
    return Response(
        status_code=405,
        headers={"Allow": "POST"},
        media_type="application/json",
        content='{"jsonrpc":"2.0","id":null,"error":{"code":-32601,'
        '"message":"This server implements MCP 2026-07-28 only: the GET stream '
        'and DELETE session termination were removed in that revision. Use POST."}}',
    )


class AskesisTokenVerifier(TokenVerifier):
    """Validates an access token against the signature, the audience, and the grant.

    Three checks, and the last two are the point:

    1. **JWT**: signature, issuer, audience and expiry (`decode_access_token`).
       Audience is RFC 8707 — a token minted for a different resource is refused
       even though we signed it.
    2. **Grant row**: the `gid` claim is looked up and must be live. This is one
       indexed read per request, and it is what makes revocation take effect
       *now* rather than whenever the hour runs out.
    3. **Password epoch**: the `pwd_at` claim is compared to the account's
       current `password_changed_at`. Changing your Askesis password therefore
       kills Claude's access exactly as it kills a browser session — no separate
       "disconnect" step to remember.
    """

    def __init__(self, config: MCPConfig) -> None:
        self._config = config

    async def verify_token(self, token: str) -> AccessToken | None:
        return await anyio.to_thread.run_sync(self._verify, token)

    def _verify(self, token: str) -> AccessToken | None:
        from app.models import MCPGrant, User
        from mcp_server.tokens import (
            PWD_EPOCH_CLAIM,
            decode_access_token,
            password_epoch,
        )

        claims = decode_access_token(
            token,
            secret=self._config.token_secret,
            issuer=self._config.public_origin,
            audience=self._config.resource_url,
        )
        if claims is None:
            return None

        db = SessionLocal()
        try:
            grant = (
                db.query(MCPGrant)
                .filter(MCPGrant.id == claims.get("gid"))
                .one_or_none()
            )
            if grant is None or grant.revoked_at is not None:
                logger.info(
                    "token refused: grant %s missing or revoked", claims.get("gid")
                )
                return None
            try:
                subject = int(claims["sub"])
            except (KeyError, TypeError, ValueError):
                return None
            if grant.user_id != subject:
                # The token says one account and the grant says another; treat
                # it as forged rather than reconciling.
                logger.warning(
                    "token subject %s != grant user %s", subject, grant.user_id
                )
                return None

            user = db.query(User).filter(User.id == subject).one_or_none()
            if user is None:
                return None
            current = password_epoch(user.password_changed_at)
            if current is not None:
                stamped = claims.get(PWD_EPOCH_CLAIM)
                if (
                    not isinstance(stamped, int)
                    or isinstance(stamped, bool)
                    or stamped < current
                ):
                    logger.info("token refused: predates the last password change")
                    return None

            grant.last_used_at = datetime.utcnow()
            db.commit()
            return AccessToken(
                token=token,
                client_id=grant.client_id,
                scopes=grant.scope.split(),
                expires_at=claims.get("exp"),
                resource=grant.resource,
                subject=str(subject),
                claims=claims,
            )
        finally:
            db.close()


class StaticTokenVerifier(TokenVerifier):
    """Stage-2 stand-in for OAuth: one hard-coded token mapped to one account.

    Exists so the wire contract can be exercised before the OAuth layer is
    built. It is never reachable in a deployed configuration — `main.py`
    refuses to install it unless MCP_DEV_TOKEN is explicitly set, which
    production never does.
    """

    def __init__(self, token: str, user_id: int, config: MCPConfig) -> None:
        self._token = token
        self._user_id = user_id
        self._config = config

    async def verify_token(self, token: str) -> AccessToken | None:
        import secrets

        if not secrets.compare_digest(token, self._token):
            return None
        return AccessToken(
            token=token,
            client_id="stage2-dev",
            scopes=[self._config.scope],
            expires_at=None,
            resource=self._config.resource_url,
            subject=str(self._user_id),
            claims={},
        )
