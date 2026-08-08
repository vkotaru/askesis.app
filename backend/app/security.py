"""Password hashing helpers.

Uses the ``bcrypt`` package directly rather than ``passlib[bcrypt]``: passlib
1.7.4 is unmaintained and raises ``AttributeError: module 'bcrypt' has no
attribute '__about__'`` against bcrypt>=4.0, which would force a ``bcrypt<4``
pin. Its only real benefit over the raw library is the multi-scheme
``CryptContext``, and this app has exactly one scheme.
"""

import bcrypt

# bcrypt silently truncates the input at 72 *bytes* — a longer password would
# authenticate on its 72-byte prefix, so we reject instead of truncating.
# Note this is bytes, not characters: non-ASCII passwords hit the limit sooner
# (a 3-byte emoji costs 3 of the 72).
MAX_PASSWORD_BYTES = 72

MIN_PASSWORD_LENGTH = 8

# Verified against when the user lookup misses, so that a request for a
# nonexistent account costs the same as one for an existing account and the
# response timing doesn't leak which is which.
_DUMMY_HASH = bcrypt.hashpw(b"askesis-dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Raises ``ValueError`` if the password exceeds bcrypt's 72-byte limit.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            f"(got {len(encoded)}); non-ASCII characters cost more than one byte each"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    """Check a plaintext password against a stored hash.

    Returns ``False`` when ``hashed`` is ``None`` (an account that has never had
    a password set — e.g. one created via Google sign-in), but still burns a
    bcrypt round against the dummy hash so the timing matches the hit path.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        # Never let an over-long password authenticate on its 72-byte prefix.
        bcrypt.checkpw(b"", _DUMMY_HASH.encode())
        return False

    if not hashed:
        bcrypt.checkpw(encoded, _DUMMY_HASH.encode())
        return False

    try:
        return bcrypt.checkpw(encoded, hashed.encode())
    except ValueError:
        # Malformed / non-bcrypt hash in the column.
        return False
