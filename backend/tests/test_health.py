"""The health endpoints tell the truth about the database, and the watchdog
counts a hung probe as a miss. The restart itself (os._exit) is not under
test; what is tested is everything that decides to call it."""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app import watchdog
from app.main import app


def test_health_is_200_when_the_database_answers():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "database": "reachable"}


def test_health_is_503_when_the_database_does_not(monkeypatch):
    monkeypatch.setattr(watchdog, "database_reachable", lambda *a, **k: False)
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "database": "unreachable"}


def test_probe_against_the_real_engine_is_true():
    assert watchdog.database_reachable() is True


def test_a_hung_probe_counts_as_unreachable(monkeypatch):
    """A connect that never returns must not stall the counter forever."""
    release = threading.Event()

    class Hung:
        def connect(self):
            release.wait()  # until the test lets go
            raise AssertionError("should not be reached before the deadline")

    import app.database as database

    monkeypatch.setattr(database, "engine", Hung())
    started = time.monotonic()
    try:
        assert watchdog.database_reachable(timeout=0.2) is False
        assert time.monotonic() - started < 2
    finally:
        release.set()


def test_watchdog_is_off_when_either_setting_is_zero():
    assert watchdog.start(0, 6) is None
    assert watchdog.start(30, 0) is None


def test_healthcheck_command_exit_code(monkeypatch, capsys):
    assert watchdog.main() == 0
    monkeypatch.setattr(watchdog, "database_reachable", lambda *a, **k: False)
    assert watchdog.main() == 1
    assert "unreachable" in capsys.readouterr().err
