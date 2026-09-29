"""Who may do what, as pure functions.

This module exists to be **importable and therefore testable**. The scope gate
is the most security-critical line in the connector — it is the only thing
standing between a read-only token and a write tool — and it used to live
inside `server.py`, which imports the MCP SDK. CI never installs that SDK, so
nothing in the repo could execute the check: it was verified by reading it.

Nothing here imports the SDK, SQLAlchemy, or anything else. It takes what it is
given and answers.
"""

from __future__ import annotations

from collections.abc import Iterable


def may_write(scopes: Iterable[str] | None, write_scope: str) -> bool:
    """Does a token carrying `scopes` have permission to change data?

    Fails closed on every ambiguity, and the ambiguities are the point:

    * `scopes` is None or empty — a token the verifier could not describe.
    * `write_scope` is empty — a misconfiguration. Answering True here would
      turn a missing setting into "everyone may write", which is precisely the
      direction a security default must not fail in.

    Scope strings are compared exactly. OAuth scope tokens are case-sensitive
    (RFC 6749 §3.3), so `Askesis:Write` is a different scope, not a spelling of
    this one.
    """
    if not write_scope:
        return False
    return write_scope in set(scopes or ())
