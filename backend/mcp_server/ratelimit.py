"""In-process rate limiting for the public endpoints.

A brake, not an access control — the same framing `_enforce_throttle` in
`app/routers/auth.py` uses about itself. State is per-process and resets on
restart, which is acceptable for what this defends against and is worth being
honest about rather than dressing up.

**Keyed differently from the app's throttle, deliberately.** The app keys on the
submitted identifier alone, and its comment explains why: behind a Tailscale
sidecar every request shares one apparent IP, so an IP-keyed limiter would lock
out the whole household at once. That reasoning **inverts** here. This endpoint
is reachable from the open internet, the client IP is a real and meaningful
signal, and identifier-only keying would let anyone who learns a username lock
the real account out at will.

So the login limiter keys on `(client_ip, identifier)`: an attacker must burn
their own IP budget per account, and a legitimate user is never locked out by
someone else's attempts from elsewhere.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

#: Failed logins per (ip, identifier) before refusing, and the window.
LOGIN_MAX_FAILURES = 8
LOGIN_WINDOW_SECONDS = 15 * 60

#: Requests per IP for the unauthenticated OAuth endpoints.
OAUTH_MAX_REQUESTS = 30
OAUTH_WINDOW_SECONDS = 60

#: Ceiling on tracked keys, so a flood of distinct IPs cannot grow this without
#: bound. Oldest buckets are dropped first.
MAX_TRACKED_KEYS = 4096


class SlidingWindow:
    """Counts events per key inside a rolling window."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._events: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        for key in list(self._events):
            fresh = [t for t in self._events[key] if t > cutoff]
            if fresh:
                self._events[key] = fresh
            else:
                del self._events[key]
        if len(self._events) > MAX_TRACKED_KEYS:
            # Drop whichever keys have the oldest most-recent event.
            for key in sorted(self._events, key=lambda k: self._events[k][-1])[
                : len(self._events) - MAX_TRACKED_KEYS
            ]:
                del self._events[key]

    def check(self, key: str) -> tuple[bool, int]:
        """(allowed, seconds_until_retry). Does not record the event."""
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            hits = self._events.get(key, [])
            if len(hits) < self._limit:
                return True, 0
            return False, max(1, int(self._window - (now - hits[0])))

    def record(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._events[key].append(now)
            self._prune(now)

    def reset(self, key: str) -> None:
        """Clear a key — called on a successful login so one bad guess before a
        correct password does not count toward the next lockout."""
        with self._lock:
            self._events.pop(key, None)


login_failures = SlidingWindow(LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS)
oauth_requests = SlidingWindow(OAUTH_MAX_REQUESTS, OAUTH_WINDOW_SECONDS)


def client_ip(request) -> str:
    """The caller's address.

    `request.client.host` is the proxy when one is in front, so the forwarded
    header is preferred — but only its FIRST entry, and only because uvicorn is
    started with `--forwarded-allow-ips` naming the loopback proxy. Without
    that flag this would be attacker-controlled and worse than useless.

    NOTE: whether Tailscale Funnel forwards a real client address is unverified.
    If it does not, every request shares one key and this degrades to a single
    global bucket — which is why the login limiter also keys on the identifier.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
