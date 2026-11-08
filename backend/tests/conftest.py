"""Test configuration. The environment is set BEFORE `app` is imported.

`app.database` builds its engine from `get_settings()` at import time, and
`get_settings` is cached for the life of the process, so these must be in
`os.environ` before the first `import app.*` anywhere in the test run. pytest
imports this file first, which is the only reason that ordering holds.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="askesis-tests-")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ.update(
    {
        # DEV_MODE off: the ingest route must be guarded by its token even in
        # dev, and the only way to prove that is to run the honest path.
        "DEV_MODE": "false",
        "SECRET_KEY": "tests-only-not-a-real-secret",
        "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
        "MFP_INGEST_TOKEN": "tests-only-ingest-token",
        "MFP_INGEST_USER": "",
        "GARMIN_SYNC_ENABLED": "false",
    }
)

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401  -- registers every table on Base
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_schema():
    """Every test starts from empty tables."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db: Session) -> User:
    u = User(email="one@example.test", username="one", name="One")
    db.add(u)
    db.commit()
    return u


# A note for the tests that read after the app wrote: `app/database.py` makes
# SQLAlchemy issue BEGIN itself on SQLite, so a test session that has run a
# SELECT holds an open transaction and, in WAL mode, a frozen snapshot of the
# database. `db.expire_all()` re-queries inside that snapshot and sees nothing
# new; `db.rollback()` ends it, and the next query sees the app's commit.
