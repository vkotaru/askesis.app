"""Exit the process when the database has been unreachable for too long.

A process that kills itself sounds wrong until you consider the alternative.
After the 2026-11-18 power cut the box, Docker and every container came back,
and for hours the app and the MCP connector answered every request that
needed Postgres with a 500 while every request that did not -- the SPA,
`/api/version`, OAuth discovery -- worked. Docker restarts a container that
EXITS. It does nothing about one that is merely useless, and a `healthcheck`
only changes what `docker compose ps` prints. So when the database has been
out of reach for a sustained stretch, the process logs why and exits non-zero,
and `restart: unless-stopped` brings it back: fresh network namespace, fresh
connection pool, `alembic upgrade head` failing fast until Postgres answers.

Three things this is careful about:

* **It checks the real path.** `SELECT 1` through the application's own
  engine, over the container's own network. Not a ping, not a port check.
* **A hung connect counts as a miss.** The probe runs in its own thread with a
  deadline; otherwise one TCP connect that never returns would stall the
  counter and the process would sit there, which is the failure this exists
  to end.
* **It is slow to pull the trigger.** Six misses thirty seconds apart by
  default: a Postgres restart or a WAL recovery passes under it. Both numbers
  are settings, and zero disables it (tests, local dev).

The same probe is the Docker `HEALTHCHECK` (`python -m app.watchdog`) and the
body of `GET /health`, so the three ways of asking "can this process serve?"
cannot disagree.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

from sqlalchemy import text

logger = logging.getLogger("askesis.watchdog")

#: Distinct from uvicorn's own exit codes so `docker compose ps -a` and the
#: logs read as "the watchdog did this", not "it crashed".
EXIT_CODE = 3

#: How long one probe may take before it is counted as a miss.
PROBE_TIMEOUT_SECONDS = 5.0


def database_reachable(timeout: float = PROBE_TIMEOUT_SECONDS) -> bool:
    """One round trip to the database, bounded by `timeout` seconds."""
    # Imported here, not at module top: `app.database` builds the engine from
    # settings at import time, and this module is imported by `app.main`
    # before anything else should have reached for the environment.
    from app.database import engine

    outcome: list[bool] = []

    def probe() -> None:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            outcome.append(True)
        except Exception as exc:  # any driver error is the same answer
            logger.warning("database probe failed: %s", exc)
            outcome.append(False)

    worker = threading.Thread(target=probe, name="db-probe", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        logger.warning("database probe did not return within %.0fs", timeout)
        return False
    return bool(outcome and outcome[0])


def start(interval_seconds: float, max_failures: int) -> threading.Thread | None:
    """Run the watchdog in a daemon thread. Returns it, or None when disabled."""
    if interval_seconds <= 0 or max_failures <= 0:
        logger.info("database watchdog disabled")
        return None

    def run() -> None:
        misses = 0
        while True:
            time.sleep(interval_seconds)
            if database_reachable():
                if misses:
                    logger.info(
                        "database reachable again after %d missed checks", misses
                    )
                misses = 0
                continue
            misses += 1
            logger.error("database unreachable (%d of %d)", misses, max_failures)
            if misses < max_failures:
                continue
            logger.critical(
                "database unreachable for %d checks (about %.0f s); exiting with "
                "code %d so the container restarts on a fresh network and pool",
                misses,
                misses * interval_seconds,
                EXIT_CODE,
            )
            logging.shutdown()
            # Not sys.exit: this is a daemon thread and SystemExit would only
            # end the thread. The point is to end the process.
            import os

            os._exit(EXIT_CODE)

    thread = threading.Thread(target=run, name="db-watchdog", daemon=True)
    thread.start()
    logger.info(
        "database watchdog: exit after %d misses at %.0fs intervals",
        max_failures,
        interval_seconds,
    )
    return thread


def start_from_settings() -> threading.Thread | None:
    """Start with the two DB_WATCHDOG_* settings. Both services call this."""
    from app.config import get_settings

    s = get_settings()
    return start(s.db_watchdog_interval_seconds, s.db_watchdog_max_failures)


def main() -> int:
    """`python -m app.watchdog`: the Docker HEALTHCHECK. 0 if reachable."""
    if database_reachable():
        print("database reachable")
        return 0
    print("database unreachable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
