#!/usr/bin/env python3
"""Drive the MCP connector's OAuth flow as a *native CLI client* would.

    rm -f /tmp/oauthflow.db
    export DATABASE_URL="sqlite:////tmp/oauthflow.db"
    DEV_MODE=true SECRET_KEY=x python -m alembic upgrade head
    python scripts/check_oauth_flow.py

Needs `pyjwt`, which lives in requirements-mcp.txt rather than requirements.txt
-- the two dependency trees are deliberately separate. In CI this belongs in
the MCP isolation job, where that tree is already installed.

WHY THIS EXISTS. Everything the connector's authorization surface does was
verified by reading it, because `server.py` imports the MCP SDK and CI never
installs it. `oauth.py` does **not** import the SDK -- it is Starlette and
SQLAlchemy and nothing else -- so the entire flow a client actually performs
(discover, register, authorize, exchange, refresh) can be driven in-process
over an ASGI transport with no network, no container and no SDK. That is the
same argument that moved the scope gate into `authz.py`.

AND WHY IT IS SHAPED LIKE THIS. The client here is deliberately **not** Claude:
it registers a loopback redirect on a random port like any RFC 8252 native app,
it omits the `resource` parameter entirely (RFC 8707 is optional for clients),
and it calls itself something else. Every Claude-specific string left in this
server is in a comment; this asserts that the *behaviour* is not, so a Gemini
CLI or any other MCP client connects on the same terms.

Exits non-zero on the first failure, and prints what it expected.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# DEV_MODE must be FALSE here, and that is the point rather than an
# inconvenience: MCPConfig refuses to build under DEV_MODE at all, because
# DEV_MODE short-circuits authentication and this is the internet-facing
# service. So this check exercises the real authentication path -- a real bcrypt
# hash, a real password -- which is the only version worth verifying.
#
# With DEV_MODE false, `app.database` calls get_settings() at import and
# sys.exit(1)s on a placeholder SECRET_KEY, so one is supplied. Throwaway, and
# distinct from MCP_TOKEN_SECRET for the reason .env.example gives: sharing them
# would make a leaked MCP token forgeable into an app session cookie.
os.environ["DEV_MODE"] = "false"
os.environ.setdefault("SECRET_KEY", "check-oauth-flow-throwaway-" + "s" * 32)
# The values MCPConfig requires. This process never listens on a socket; the
# origin only has to be a well-formed https URL for the metadata documents.
os.environ.setdefault("MCP_PUBLIC_ORIGIN", "https://askesis-mcp.example.ts.net")
os.environ.setdefault("MCP_TOKEN_SECRET", "t" * 32)
os.environ.setdefault("MCP_APP_SECRET_KEY", "a" * 32)

import httpx  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from mcp_server import oauth  # noqa: E402
from mcp_server.config import MCPConfig  # noqa: E402
from mcp_server.tokens import decode_access_token  # noqa: E402

PASSWORD = "correct horse battery staple"  # noqa: S105 - a fixture, not a secret
CLIENT_NAME = "Some Other CLI"
#: An ephemeral loopback port, exactly as RFC 8252 §7.3 describes. Nothing in
#: this server may care which port it is.
REDIRECT = "http://localhost:41235/oauth/callback"

fails: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  OK   {label:<54} {got!r:>30.30}")
    else:
        fails.append(label)
        print(f"  FAIL {label:<54} got {got!r}  want {want!r}")


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


def build_app(config: MCPConfig) -> Starlette:
    """Only the OAuth routes. The SDK is not installed and is not needed."""
    return Starlette(
        routes=[
            Route(
                "/.well-known/oauth-protected-resource/mcp",
                oauth.protected_resource_metadata(config),
                methods=["GET"],
            ),
            Route(
                "/.well-known/oauth-authorization-server",
                oauth.authorization_server_metadata(config),
                methods=["GET"],
            ),
            Route("/register", oauth.register(config), methods=["POST"]),
            Route("/authorize", oauth.authorize(config), methods=["GET", "POST"]),
            Route("/token", oauth.token(config), methods=["POST"]),
        ]
    )


async def authorize(
    client: httpx.AsyncClient,
    *,
    client_id: str,
    challenge: str,
    scope: str | None,
    resource: str | None = None,
    password: str = PASSWORD,
) -> httpx.Response:
    """GET the consent page, then POST the password, as a browser would."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "opaque-state",
    }
    if scope is not None:
        params["scope"] = scope
    if resource is not None:
        params["resource"] = resource

    page = await client.get("/authorize", params=params)
    if page.status_code != 200:
        return page
    # The form has no `action`, so it posts back to the same URL -- query string
    # included. That is load-bearing: the granted scope is read from the query
    # only, so the page you saw and the permission you get cannot disagree.
    return await client.post(
        "/authorize",
        params=params,
        data={"username": "gemtest", "password": password},
        follow_redirects=False,
    )


async def main() -> int:  # noqa: PLR0915 - a linear script; splitting it hides the order
    config = MCPConfig()
    app = build_app(config)
    # Async, and driven over an ASGI transport rather than a socket. httpx 0.26
    # (the app tree) has no sync ASGI transport at all, so this is also what
    # lets one script run under either dependency tree.
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )

    db = SessionLocal()
    if db.query(User).filter(User.username == "gemtest").one_or_none() is None:
        db.add(
            User(
                email="gem@example.invalid",
                username="gemtest",
                name="Gem",
                password_hash=hash_password(PASSWORD),
            )
        )
        db.commit()
    db.close()

    print("── discovery ──")
    meta = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
    check("protected resource names itself", meta["resource"], config.resource_url)
    asmeta = (await client.get("/.well-known/oauth-authorization-server")).json()
    check("PKCE S256 advertised", asmeta["code_challenge_methods_supported"], ["S256"])
    check(
        "public clients only", asmeta["token_endpoint_auth_methods_supported"], ["none"]
    )
    check(
        "both askesis scopes advertised",
        sorted(s for s in asmeta["scopes_supported"] if s.startswith("askesis:")),
        sorted(config.supported_scopes),
    )

    print()
    print("── registration (RFC 7591) ──")
    reg = await client.post(
        "/register", json={"client_name": CLIENT_NAME, "redirect_uris": [REDIRECT]}
    )
    check("a loopback redirect registers", reg.status_code, 201)
    body = reg.json()
    cid = body["client_id"]
    check("no client secret is issued", body["token_endpoint_auth_method"], "none")
    bad = await client.post(
        "/register",
        json={"client_name": "Elsewhere", "redirect_uris": ["https://evil.test/cb"]},
    )
    check("an off-site redirect is refused", bad.status_code, 400)
    check("  and says why", bad.json()["error"], "invalid_redirect_uri")

    print()
    print("── consent ──")
    verifier, challenge = pkce()
    page = await client.get(
        "/authorize",
        params={
            "client_id": cid,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    check("the page renders", page.status_code, 200)
    # The one thing that would actually read wrong for a non-Claude client.
    check("it names the registered client", CLIENT_NAME in page.text, True)
    check("  and not a hard-coded one", "Claude" in page.text, False)
    check("loopback carries its warning", "running on this machine" in page.text, True)
    check("default grant says read-only", "read-only" in page.text, True)

    print()
    print("── the flow, with no `resource` parameter at all ──")
    verifier, challenge = pkce()
    resp = await authorize(client, client_id=cid, challenge=challenge, scope=None)
    check("consent redirects", resp.status_code, 302)
    query = parse_qs(urlparse(resp.headers["location"]).query)
    check(
        "  back to the loopback port",
        resp.headers["location"].startswith(REDIRECT),
        True,
    )
    check("  with the state echoed", query["state"][0], "opaque-state")
    code = query["code"][0]

    tok = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    check("token issued", tok.status_code, 200)
    payload = tok.json()
    claims = decode_access_token(
        payload["access_token"],
        secret=config.token_secret,
        issuer=config.authorize_origin,
        audience=config.resource_url,
    )
    check("  and it verifies", claims is not None, True)
    # The default has to be the safe one: a client that asks for nothing must
    # not be handed the ability to change data.
    check("  read-only by default", claims["scope"], config.read_scope)
    check("  bound to this resource", claims["aud"], config.resource_url)

    print()
    print("── asking for write ──")
    verifier, challenge = pkce()
    both = f"{config.read_scope} {config.write_scope}"
    page = await client.get(
        "/authorize",
        params={
            "client_id": cid,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": both,
        },
    )
    check("the page says what changes", "also be able to change" in page.text, True)
    resp = await authorize(client, client_id=cid, challenge=challenge, scope=both)
    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    tok = (
        await client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT,
                "client_id": cid,
                "code_verifier": verifier,
            },
        )
    ).json()
    claims = decode_access_token(
        tok["access_token"],
        secret=config.token_secret,
        issuer=config.authorize_origin,
        audience=config.resource_url,
    )
    check(
        "the token carries write", sorted(claims["scope"].split()), sorted(both.split())
    )

    print()
    print("── a refresh cannot widen what was granted ──")
    refreshed = await client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": cid,
            "scope": both,
        },
    )
    check("refresh works", refreshed.status_code, 200)

    verifier, challenge = pkce()
    resp = await authorize(
        client, client_id=cid, challenge=challenge, scope=config.read_scope
    )
    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    ro = (
        await client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT,
                "client_id": cid,
                "code_verifier": verifier,
            },
        )
    ).json()
    widened = (
        await client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": ro["refresh_token"],
                "client_id": cid,
                "scope": both,
            },
        )
    ).json()
    claims = decode_access_token(
        widened["access_token"],
        secret=config.token_secret,
        issuer=config.authorize_origin,
        audience=config.resource_url,
    )
    check("a read-only grant stays read-only", claims["scope"], config.read_scope)

    print()
    print("── what must be refused ──")
    verifier, challenge = pkce()
    resp = await authorize(
        client,
        client_id=cid,
        challenge=challenge,
        scope=None,
        resource="https://somewhere-else.test/mcp",
    )
    # RFC 6749 §4.1.2.1: a failure the client can act on goes back to the client
    # as a redirect carrying `error`. So 302 is correct here; what must not be
    # there is a code.
    foreign = parse_qs(urlparse(resp.headers.get("location", "")).query)
    check("a foreign resource errors", foreign.get("error", [""])[0], "invalid_target")
    check("  and issues no code", "code" in foreign, False)

    no_pkce = await client.get(
        "/authorize",
        params={
            "client_id": cid,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "state": "s",
        },
        follow_redirects=False,
    )
    check("PKCE is mandatory", no_pkce.status_code, 302)
    check(
        "  and the error says so",
        "invalid_request" in no_pkce.headers.get("location", ""),
        True,
    )

    verifier, challenge = pkce()
    resp = await authorize(client, client_id=cid, challenge=challenge, scope=None)
    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    wrong = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": cid,
            "code_verifier": "not-the-verifier",
        },
    )
    check("a wrong PKCE verifier is refused", wrong.status_code, 400)
    replay = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    # A code offered with the wrong verifier is spent, not retryable: that is
    # what makes an intercepted code useless rather than merely awkward.
    check("  and the code is then spent", replay.status_code, 400)

    verifier, challenge = pkce()
    bad_pw = await authorize(
        client, client_id=cid, challenge=challenge, scope=None, password="wrong"
    )
    # 401 and the consent page again, NOT a redirect: a failed login is not
    # something to hand back to the client, it is something to retry here.
    check("a wrong password re-renders the form", bad_pw.status_code, 401)
    check("  and no code leaks into the page", "code=" in bad_pw.text, False)

    print()
    if fails:
        print(f"  {len(fails)} FAILURE(S): " + ", ".join(fails))
        return 1
    print("  ANY MCP CLIENT CAN COMPLETE THIS FLOW")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
