"""Cryptographic primitives for the OAuth layer: hashing, PKCE, JWTs.

Kept separate from the endpoints so each piece can be tested without a request.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import secrets
from datetime import datetime, timedelta

import jwt

#: How long an access token lives. Short because revocation is checked per
#: request anyway (see the `gid` claim) — this is the ceiling on a token that
#: escapes, not the mechanism for withdrawing one.
ACCESS_TOKEN_TTL = timedelta(hours=1)

#: Refresh lifetime, slid forward on each rotation.
REFRESH_TOKEN_TTL = timedelta(days=30)

#: Authorization codes are redeemed within seconds of being issued. A minute is
#: generous and keeps the replay window closed.
AUTH_CODE_TTL = timedelta(seconds=60)

#: Mirrors `_PWD_EPOCH_CLAIM` in app/routers/auth.py. Same name on purpose: an
#: MCP token and an app session token encode the same fact the same way.
PWD_EPOCH_CLAIM = "pwd_at"


def new_secret() -> str:
    """A 256-bit URL-safe random string. Used for codes and refresh tokens."""
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    """SHA-256 hex of a high-entropy secret.

    Not bcrypt, and the distinction is deliberate. These are 256 random bits,
    so there is no dictionary to run and no work factor worth paying; bcrypt on
    the token path would just be a per-request CPU cost an attacker could
    trigger at will. Passwords keep going through `app.security.hash_password`.
    """
    return hashlib.sha256(value.encode()).hexdigest()


def verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    """RFC 7636 S256 only.

    `plain` is rejected outright rather than supported-but-discouraged: it
    offers no protection against a stolen authorization code, which is the one
    thing PKCE exists to prevent.
    """
    if method != "S256":
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, challenge)


def password_epoch(password_changed_at: datetime | None) -> int | None:
    """`users.password_changed_at` as whole UTC seconds.

    `calendar.timegm`, never `.timestamp()`: the column holds a naive UTC value
    and `.timestamp()` would interpret it as local time and shift it by the
    host's offset. Copied rather than imported because importing
    `app.routers.auth` would pull FastAPI into this image and break the
    dependency split — see mcp_server/__init__.py.
    """
    if password_changed_at is None:
        return None
    return calendar.timegm(password_changed_at.utctimetuple())


def mint_access_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    subject: int,
    client_id: str,
    scope: str,
    grant_id: int,
    pwd_at: int | None,
) -> tuple[str, datetime]:
    """Sign an access token. Returns the token and its expiry."""
    now = datetime.utcnow()
    expires = now + ACCESS_TOKEN_TTL
    claims: dict = {
        "iss": issuer,
        # RFC 8707: bound to the resource the user consented to, and checked on
        # every request. A token minted for a different audience is refused
        # even though the signature is ours.
        "aud": audience,
        "sub": str(subject),
        "cid": client_id,
        "scope": scope,
        # The grant row, so revocation takes effect on the next request rather
        # than at expiry.
        "gid": grant_id,
        "iat": calendar.timegm(now.utctimetuple()),
        "exp": calendar.timegm(expires.utctimetuple()),
        "jti": secrets.token_urlsafe(12),
    }
    if pwd_at is not None:
        # Changing the Askesis password already kills every app session; this
        # makes it kill Claude's access too, without any extra step.
        claims[PWD_EPOCH_CLAIM] = pwd_at
    return jwt.encode(claims, secret, algorithm="HS256"), expires


def decode_access_token(
    token: str, *, secret: str, issuer: str, audience: str
) -> dict | None:
    """Verify signature, issuer, audience and expiry. None if any fail."""
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],  # explicit: never trust the header's alg
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "gid"]},
        )
    except jwt.InvalidTokenError:
        return None
