"""OAuth 2.1 endpoints for the MCP connector.

Only what a client genuinely needs, hardened past the minimum:

- **PKCE S256 is mandatory**; `plain` is refused, not tolerated.
- **Redirect URIs are allowlisted at registration.** `/register` is
  unauthenticated by necessity — Claude registers a fresh client on every new
  connection — so this is what stops it being an open redirect factory. It also
  means a stolen authorization code has nowhere useful to go.
- **Public clients only.** No secret is issued, so there is none to leak.
- **Codes and refresh tokens are hashed at rest**, correcting the
  `report_tokens` precedent.
- **Refresh tokens rotate.** A stolen one is usable at most once.
- **Access tokens carry `gid`**, checked per request, so revoking a grant takes
  effect immediately rather than at expiry.
- **Tokens carry `pwd_at`**, so changing the Askesis password kills Claude's
  access exactly as it kills a web session.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse

from sqlalchemy import update
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.database import SessionLocal
from app.models import MCPAuthCode, MCPClient, MCPGrant, User
from app.security import verify_password
from mcp_server import ratelimit as rl
from mcp_server.config import MCPConfig
from mcp_server.templates import consent_page, message_page
from mcp_server.tokens import (
    AUTH_CODE_TTL,
    REFRESH_TOKEN_TTL,
    hash_secret,
    mint_access_token,
    new_secret,
    password_epoch,
    verify_pkce,
)

logger = logging.getLogger("askesis.mcp.oauth")

#: Where an authorization code may be sent. Anything outside this is refused at
#: registration, which is the single most valuable control on this surface: it
#: makes a stolen code unredirectable rather than merely hard to steal.
ALLOWED_REDIRECT_HOSTS = {"claude.ai", "claude.com"}
ALLOWED_REDIRECT_PATHS = {"/api/mcp/auth_callback"}

#: RFC 8252 §7.3 — a native client gets an ephemeral loopback port, so the port
#: is ignored when matching. Enabled for Claude Code / Desktop; the consent page
#: shows an explicit warning for these.
ALLOW_LOOPBACK_REDIRECTS = True

#: Registrations are cheap to create and this table has no natural bound.
MAX_CLIENTS = 50


def _redirect_allowed(uri: str) -> bool:
    try:
        p = urlparse(uri)
    except ValueError:
        return False
    if p.scheme == "https" and p.hostname in ALLOWED_REDIRECT_HOSTS:
        return p.path in ALLOWED_REDIRECT_PATHS
    if ALLOW_LOOPBACK_REDIRECTS and p.scheme == "http":
        return p.hostname in ("localhost", "127.0.0.1", "::1")
    return False


def _json(data: dict, status: int = 200) -> JSONResponse:
    # No-store is required for token responses and harmless on the rest.
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return _json({"error": error, "error_description": description}, status)


def _throttled(request: Request) -> Response | None:
    ip = rl.client_ip(request)
    allowed, retry = rl.oauth_requests.check(ip)
    if not allowed:
        logger.warning("oauth rate limit hit for %s", ip)
        return JSONResponse(
            {"error": "slow_down", "error_description": "Too many requests."},
            status_code=429,
            headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
        )
    rl.oauth_requests.record(ip)
    return None


# ── Discovery ────────────────────────────────────────────────────────────────


def authorization_server_metadata(config: MCPConfig):
    """RFC 8414. How a client learns where to send the user and the code."""

    async def handler(request: Request) -> Response:
        return _json(
            {
                "issuer": config.public_origin,
                # May sit on a different origin (the tailnet-only port) so the
                # login screen is never publicly reachable. RFC 8414 permits it.
                "authorization_endpoint": f"{config.authorize_origin}/authorize",
                "token_endpoint": f"{config.public_origin}/token",
                "registration_endpoint": f"{config.public_origin}/register",
                "revocation_endpoint": f"{config.public_origin}/revoke",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                # Advertising S256 is not optional: a client that cannot see it
                # here will not send a challenge, and /authorize refuses without
                # one.
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                # `offline_access` must appear or no refresh token is requested,
                # and the connector silently stops working after an hour.
                "scopes_supported": [config.scope, "offline_access"],
                "authorization_response_iss_parameter_supported": True,
            }
        )

    return handler


# ── Dynamic client registration (RFC 7591) ───────────────────────────────────


def register(config: MCPConfig):
    async def handler(request: Request) -> Response:
        if (limited := _throttled(request)) is not None:
            return limited
        try:
            body = await request.json()
        except Exception:
            return _oauth_error("invalid_request", "Body must be JSON.")

        uris = body.get("redirect_uris")
        if (
            not isinstance(uris, list)
            or not uris
            or not all(isinstance(u, str) for u in uris)
        ):
            return _oauth_error(
                "invalid_redirect_uri",
                "redirect_uris must be a non-empty array of strings.",
            )
        rejected = [u for u in uris if not _redirect_allowed(u)]
        if rejected:
            logger.warning("registration refused for redirect_uris=%s", rejected)
            return _oauth_error(
                "invalid_redirect_uri",
                f"Redirect URI not permitted: {rejected[0]}",
            )

        db = SessionLocal()
        try:
            # Bound the table. Evict the least recently used registration that
            # has no live grant behind it.
            if db.query(MCPClient).count() >= MAX_CLIENTS:
                live = {
                    g.client_id
                    for g in db.query(MCPGrant)
                    .filter(MCPGrant.revoked_at.is_(None))
                    .all()
                }
                victim = (
                    db.query(MCPClient)
                    .filter(MCPClient.client_id.notin_(live) if live else True)
                    .order_by(
                        MCPClient.last_used_at.is_(None).desc(),
                        MCPClient.last_used_at.asc(),
                    )
                    .first()
                )
                if victim is None:
                    return _oauth_error(
                        "invalid_request", "Client registry is full.", 503
                    )
                db.delete(victim)

            client_id = secrets.token_urlsafe(24)
            db.add(
                MCPClient(
                    client_id=client_id,
                    client_name=str(body.get("client_name") or "Unnamed client")[:255],
                    redirect_uris=json.dumps(uris),
                    scope=config.scope,
                )
            )
            db.commit()
            logger.info(
                "registered client %s (%s) for %s",
                client_id,
                body.get("client_name"),
                uris,
            )
            return _json(
                {
                    "client_id": client_id,
                    "client_id_issued_at": int(datetime.utcnow().timestamp()),
                    "redirect_uris": uris,
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    # Public client: no secret is issued, so none can leak.
                    "token_endpoint_auth_method": "none",
                    "scope": config.scope,
                },
                201,
            )
        finally:
            db.close()

    return handler


# ── Authorization ────────────────────────────────────────────────────────────


def _validate_authorize(
    db, config: MCPConfig, params
) -> tuple[MCPClient, str, dict] | Response:
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    client = db.query(MCPClient).filter(MCPClient.client_id == client_id).one_or_none()
    if client is None:
        return Response(
            message_page(
                "Unknown application",
                "That application is not registered with this server.",
            ),
            status_code=400,
            media_type="text/html",
        )
    # An unregistered redirect must never be redirected TO — that is what makes
    # the allowlist meaningful, so this error is rendered rather than bounced.
    if redirect_uri not in json.loads(client.redirect_uris):
        return Response(
            message_page(
                "Bad redirect",
                "That redirect address is not registered for this application.",
            ),
            status_code=400,
            media_type="text/html",
        )

    challenge = params.get("code_challenge", "")
    method = params.get("code_challenge_method", "")
    if not challenge or method != "S256":
        return _redirect_error(
            redirect_uri,
            params,
            "invalid_request",
            "PKCE with code_challenge_method=S256 is required.",
            config,
        )
    if params.get("response_type") != "code":
        return _redirect_error(
            redirect_uri,
            params,
            "unsupported_response_type",
            "Only response_type=code is supported.",
            config,
        )

    # RFC 8707: the token is minted for this resource and checked against it on
    # every call, so a mismatch has to fail here rather than produce a token
    # that mysteriously never works.
    resource = params.get("resource") or config.resource_url
    if resource != config.resource_url:
        return _redirect_error(
            redirect_uri,
            params,
            "invalid_target",
            f"This server only issues tokens for {config.resource_url}",
            config,
        )
    return (
        client,
        redirect_uri,
        {"challenge": challenge, "method": method, "resource": resource},
    )


def _redirect_error(
    redirect_uri: str, params, error: str, description: str, config: MCPConfig
) -> Response:
    q = {"error": error, "error_description": description, "iss": config.public_origin}
    if params.get("state"):
        q["state"] = params["state"]
    return RedirectResponse(f"{redirect_uri}?{urlencode(q)}", status_code=302)


def authorize(config: MCPConfig):
    async def handler(request: Request) -> Response:
        if (limited := _throttled(request)) is not None:
            return limited
        params = (
            dict(request.query_params)
            if request.method == "GET"
            else {**dict(request.query_params), **dict(await request.form())}
        )
        db = SessionLocal()
        try:
            validated = _validate_authorize(db, config, params)
            if isinstance(validated, Response):
                return validated
            client, redirect_uri, pkce = validated

            hidden = {
                k: params.get(k, "")
                for k in (
                    "client_id",
                    "redirect_uri",
                    "state",
                    "code_challenge",
                    "code_challenge_method",
                    "resource",
                    "scope",
                    "response_type",
                )
                if params.get(k)
            }
            if request.method == "GET":
                return Response(
                    consent_page(
                        client_name=client.client_name or "An application",
                        redirect_uri=redirect_uri,
                        account_label="your Askesis account",
                        hidden=hidden,
                    ),
                    media_type="text/html",
                )

            identifier = (params.get("username") or "").strip()
            password = params.get("password") or ""
            ip = rl.client_ip(request)
            key = f"{ip}|{identifier.lower()}"
            allowed, retry = rl.login_failures.check(key)
            if not allowed:
                return Response(
                    consent_page(
                        client_name=client.client_name or "An application",
                        redirect_uri=redirect_uri,
                        account_label="your Askesis account",
                        error=f"Too many attempts. Try again in {retry // 60 + 1} minutes.",
                        hidden=hidden,
                    ),
                    status_code=429,
                    media_type="text/html",
                )

            user = (
                db.query(User)
                .filter((User.username == identifier) | (User.email == identifier))
                .one_or_none()
            )
            # `verify_password` burns a bcrypt round against a dummy hash when
            # the lookup misses, so a wrong username costs the same as a wrong
            # password and the timing does not distinguish them.
            if user is None or not verify_password(password, user.password_hash):
                rl.login_failures.record(key)
                logger.warning("failed MCP login for %r from %s", identifier, ip)
                return Response(
                    consent_page(
                        client_name=client.client_name or "An application",
                        redirect_uri=redirect_uri,
                        account_label="your Askesis account",
                        error="Incorrect username or password.",
                        hidden=hidden,
                    ),
                    status_code=401,
                    media_type="text/html",
                )
            # An account with no password belongs to whoever claims it first.
            # The app tolerates that because it is tailnet-only; this endpoint
            # is not, so the claim flow is never offered here.
            if user.password_hash is None:
                return Response(
                    message_page(
                        "Account not set up",
                        "This account has no password yet. Set one in the Askesis app first.",
                    ),
                    status_code=403,
                    media_type="text/html",
                )

            rl.login_failures.reset(key)
            code = new_secret()
            db.add(
                MCPAuthCode(
                    code_hash=hash_secret(code),
                    client_id=client.client_id,
                    user_id=user.id,
                    redirect_uri=redirect_uri,
                    code_challenge=pkce["challenge"],
                    code_challenge_method=pkce["method"],
                    scope=config.scope,
                    resource=pkce["resource"],
                    expires_at=datetime.utcnow() + AUTH_CODE_TTL,
                )
            )
            client.last_used_at = datetime.utcnow()
            db.commit()
            logger.info(
                "issued auth code to client %s for user %s", client.client_id, user.id
            )

            q = {"code": code, "iss": config.public_origin}
            if params.get("state"):
                q["state"] = params["state"]
            return RedirectResponse(f"{redirect_uri}?{urlencode(q)}", status_code=302)
        finally:
            db.close()

    return handler


# ── Token ────────────────────────────────────────────────────────────────────


def _issue(db, config: MCPConfig, grant: MCPGrant, user: User) -> JSONResponse:
    """Mint an access token and a fresh refresh token for a grant."""
    refresh = new_secret()
    grant.refresh_token_hash = hash_secret(refresh)
    grant.refresh_expires_at = datetime.utcnow() + REFRESH_TOKEN_TTL
    grant.last_used_at = datetime.utcnow()
    db.commit()

    access, expires = mint_access_token(
        secret=config.token_secret,
        issuer=config.public_origin,
        audience=grant.resource,
        subject=user.id,
        client_id=grant.client_id,
        scope=grant.scope,
        grant_id=grant.id,
        pwd_at=password_epoch(user.password_changed_at),
    )
    return _json(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int((expires - datetime.utcnow()).total_seconds()),
            "refresh_token": refresh,
            "scope": grant.scope,
        }
    )


def token(config: MCPConfig):
    async def handler(request: Request) -> Response:
        if (limited := _throttled(request)) is not None:
            return limited
        # Form-encoded, per OAuth. JSON here is a client bug worth naming.
        try:
            form = dict(await request.form())
        except Exception:
            return _oauth_error(
                "invalid_request", "Body must be application/x-www-form-urlencoded."
            )

        grant_type = form.get("grant_type")
        db = SessionLocal()
        try:
            if grant_type == "authorization_code":
                return _authorization_code(db, config, form)
            if grant_type == "refresh_token":
                return _refresh(db, config, form)
            return _oauth_error(
                "unsupported_grant_type", f"Unsupported grant_type: {grant_type!r}"
            )
        finally:
            db.close()

    return handler


def _authorization_code(db, config: MCPConfig, form) -> Response:
    code = form.get("code") or ""
    verifier = form.get("code_verifier") or ""
    row = (
        db.query(MCPAuthCode)
        .filter(MCPAuthCode.code_hash == hash_secret(code))
        .one_or_none()
    )
    if row is None:
        return _oauth_error(
            "invalid_grant", "Unknown or already-used authorization code."
        )
    if row.consumed_at is not None:
        # Replay. The grant this code produced is not revoked here because the
        # legitimate holder may be using it; the code itself is simply dead.
        logger.warning("replayed auth code for client %s", row.client_id)
        return _oauth_error("invalid_grant", "Authorization code already used.")
    if row.expires_at < datetime.utcnow():
        return _oauth_error("invalid_grant", "Authorization code expired.")
    if row.client_id != (form.get("client_id") or ""):
        return _oauth_error("invalid_grant", "Code was issued to a different client.")
    if row.redirect_uri != (form.get("redirect_uri") or ""):
        return _oauth_error(
            "invalid_grant", "redirect_uri does not match the authorization request."
        )
    if not verify_pkce(verifier, row.code_challenge, row.code_challenge_method):
        return _oauth_error("invalid_grant", "PKCE verification failed.")

    # Single-use, enforced by the database rather than by the check above: the
    # UPDATE only matches while consumed_at IS NULL, so two simultaneous
    # redemptions cannot both win. Same pattern as set_initial_password.
    claimed = db.execute(
        update(MCPAuthCode)
        .where(MCPAuthCode.id == row.id, MCPAuthCode.consumed_at.is_(None))
        .values(consumed_at=datetime.utcnow())
    ).rowcount
    if not claimed:
        db.rollback()
        return _oauth_error("invalid_grant", "Authorization code already used.")

    user = db.query(User).filter(User.id == row.user_id).one_or_none()
    if user is None:
        db.rollback()
        return _oauth_error("invalid_grant", "Account no longer exists.")

    grant = MCPGrant(
        user_id=user.id, client_id=row.client_id, scope=row.scope, resource=row.resource
    )
    db.add(grant)
    db.commit()
    logger.info(
        "granted client %s access for user %s (grant %s)",
        row.client_id,
        user.id,
        grant.id,
    )
    return _issue(db, config, grant, user)


def _refresh(db, config: MCPConfig, form) -> Response:
    presented = form.get("refresh_token") or ""
    grant = (
        db.query(MCPGrant)
        .filter(MCPGrant.refresh_token_hash == hash_secret(presented))
        .one_or_none()
    )
    # `invalid_grant` specifically, not `invalid_request`: clients distinguish
    # them, and the wrong one turns "re-authorize me" into a hard failure.
    if grant is None:
        return _oauth_error("invalid_grant", "Unknown or rotated refresh token.")
    if grant.revoked_at is not None:
        return _oauth_error("invalid_grant", "This authorization was revoked.")
    if grant.refresh_expires_at and grant.refresh_expires_at < datetime.utcnow():
        return _oauth_error("invalid_grant", "Refresh token expired; re-authorize.")

    user = db.query(User).filter(User.id == grant.user_id).one_or_none()
    if user is None:
        return _oauth_error("invalid_grant", "Account no longer exists.")
    # Rotation: _issue overwrites refresh_token_hash, so the presented value
    # stops working the moment this returns.
    return _issue(db, config, grant, user)


# ── Revocation ───────────────────────────────────────────────────────────────


def revoke(config: MCPConfig):
    async def handler(request: Request) -> Response:
        if (limited := _throttled(request)) is not None:
            return limited
        try:
            form = dict(await request.form())
        except Exception:
            return _oauth_error("invalid_request", "Body must be form-encoded.")
        presented = form.get("token") or ""
        db = SessionLocal()
        try:
            grant = (
                db.query(MCPGrant)
                .filter(MCPGrant.refresh_token_hash == hash_secret(presented))
                .one_or_none()
            )
            if grant is not None and grant.revoked_at is None:
                grant.revoked_at = datetime.utcnow()
                grant.refresh_token_hash = None
                db.commit()
                logger.info("revoked grant %s", grant.id)
            # RFC 7009: always 200, even for an unknown token, so this cannot be
            # used to probe which tokens exist.
            return Response(status_code=200, headers={"Cache-Control": "no-store"})
        finally:
            db.close()

    return handler


def healthz(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


def cleanup_expired(db) -> int:
    """Drop consumed and expired authorization codes. Called opportunistically."""
    cutoff = datetime.utcnow() - timedelta(hours=1)
    n = db.query(MCPAuthCode).filter(MCPAuthCode.created_at < cutoff).delete()
    db.commit()
    return n
